import json
import logging
import os
import re
import yaml
from src.utils import AsyncLLM

logger = logging.getLogger(__name__)

_SENSITIVE_CONFIG_KEYS = frozenset({
    "api_key", "apikey", "authorization", "password", "secret", "token",
})
_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _redact_sensitive_values(value):
    """Return a serializable config copy without credentials."""
    if isinstance(value, dict):
        return {
            key: ("***REDACTED***" if _is_sensitive_key(key)
                  else _redact_sensitive_values(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    return value


def _is_sensitive_key(key):
    normalized = str(key).lower().replace("-", "_")
    return (
        normalized in _SENSITIVE_CONFIG_KEYS
        or normalized.endswith(("_api_key", "_token", "_secret", "_password", "_credential"))
        or normalized.startswith(("api_key_", "token_", "secret_", "password_", "credential_"))
        or normalized in {"access_token", "client_secret", "private_key"}
    )


def _safe_path_component(value, fallback="unknown"):
    """Normalize a user-facing label so it cannot alter the output path."""
    component = _INVALID_PATH_CHARS.sub("_", str(value or "")).replace("..", "_")
    component = component.strip(" ._")[:50]
    return component or fallback

class Config:
    def __init__(self, config_file_path=None, config_dict=None):
        # load default config
        current_path = os.path.dirname(os.path.realpath(__file__))
        default_file_path = os.path.join(current_path, "default_config.yaml")
        self.config = self._load_config(default_file_path)

        # load from file
        self.config_file_path = config_file_path
        if config_file_path is not None:
            file_config = self._load_config(config_file_path)
            self.config.update(file_config)
        
        # load from dict
        self.config.update(config_dict or {})
        
        self._set_dirs()
        self._set_llms()
        self._set_rate_limiter()

    
    def _load_config(self, config_file_path):
        def build_yaml_loader():
            loader = yaml.SafeLoader
            loader.add_implicit_resolver(
                "tag:yaml.org,2002:float",
                re.compile(
                    """^(?:
                [-+]?(?:[0-9][0-9_]*)\\.[0-9_]*(?:[eE][-+]?[0-9]+)?
                |[-+]?(?:[0-9][0-9_]*)(?:[eE][-+]?[0-9]+)
                |\\.[0-9_]+(?:[eE][-+][0-9]+)?
                |[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\\.[0-9_]*
                |[-+]?\\.(?:inf|Inf|INF)
                |\\.(?:nan|NaN|NAN))$""",
                    re.X,
                ),
                list("-+0123456789."),
            )
            return loader
    
        def replace_env_vars(obj):
            """Recursively replace ${VAR_NAME} with environment variables"""
            if isinstance(obj, dict):
                return {key: replace_env_vars(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [replace_env_vars(item) for item in obj]
            elif isinstance(obj, str):
                # Match ${VAR_NAME} pattern
                pattern = r'\$\{([^}]+)\}'
                matches = re.findall(pattern, obj)
                if matches:
                    result = obj
                    for var_name in matches:
                        env_value = os.getenv(var_name)
                        if env_value is None:
                            logger.warning(f"Environment variable '{var_name}' is not set, keeping placeholder")
                            continue
                        result = result.replace(f"${{{var_name}}}", env_value)
                    return result
                return obj
            else:
                return obj
    
        yaml_loader = build_yaml_loader()
        file_config = dict()
        if os.path.exists(config_file_path):
            if config_file_path.endswith('.yaml'):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    file_config.update(yaml.load(f.read(), Loader=yaml_loader))
            elif config_file_path.endswith('.json'):
                with open(config_file_path, 'r') as f:
                    file_config.update(json.load(f))
            else:
                raise ValueError(f"Unsupported file type: {config_file_path}")
        else:
            raise ValueError(f"Config file not found: {config_file_path}")
        
        # Replace environment variables in the loaded config
        file_config = replace_env_vars(file_config)
        return file_config
    
    
    
    def _set_dirs(self):
        # convert output dir to absolute path
        output_dir = os.path.abspath(self.config.get('output_dir', './outputs'))
        self.config['output_dir'] = output_dir
        target = _safe_path_component(self.config.get('target_name', 'unknown'))
        save_note = self.config.get('save_note', None)
        if save_note:
            target = _safe_path_component(f"{save_note}_{target}")
        self.working_dir = os.path.abspath(os.path.join(output_dir, target))
        if os.path.commonpath([output_dir, self.working_dir]) != output_dir:
            raise ValueError("Configured output path escapes output_dir")
        self.config['working_dir'] = self.working_dir
        self._validate_market_code()
        os.makedirs(self.working_dir, exist_ok=True)
        with open(os.path.join(self.working_dir, 'config.json'), 'w', encoding='utf-8') as f:
            json.dump(_redact_sensitive_values(self.config), f, indent=4, ensure_ascii=False)

    def _validate_market_code(self):
        """Reject obvious stock-code and market combinations before collection starts."""
        stock_code = str(self.config.get('stock_code', '')).strip()
        if not stock_code:
            return
        market = str(self.config.get('market', 'US')).upper()
        self.config['market'] = market
        if market not in {'A', 'HK', 'US'}:
            raise ValueError("market must be one of: A, HK, US")
        if market == 'A' and not re.fullmatch(r'\d{6}', stock_code):
            raise ValueError("A-share stock_code must be a six-digit code")
        if market == 'HK' and not re.fullmatch(r'\d{1,5}', stock_code):
            raise ValueError("HK stock_code must contain one to five digits")
        
    
    def _set_llms(self):
        llm_config_list = self.config.get('llm_config_list', [])
        llm_dict = {}
        for llm_config in llm_config_list:
            model_name = llm_config['model_name']
            # Skip entries whose env vars were not resolved (e.g. optional VLM/Embedding)
            if model_name.startswith('${'):
                logger.warning(f"Skipping llm_config with unresolved env var: {model_name}")
                continue
            llm = AsyncLLM(
                base_url=llm_config['base_url'],
                api_key=llm_config['api_key'],
                model_name=model_name,
                generation_params=llm_config.get('generation_params', {})
            )
            llm_dict[model_name] = llm
        self.llm_dict = llm_dict
            
    def _set_rate_limiter(self):
        """Initialize the global rate limiter from config."""
        from src.utils.rate_limiter import RateLimiter
        rate_limits = self.config.get('rate_limits', {})
        self.rate_limiter = RateLimiter(rate_limits)

    def __str__(self):
        return str(self.config)
