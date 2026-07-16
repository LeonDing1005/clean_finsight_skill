#!/usr/bin/env python3
"""
FinSight Research Pipeline — CLI Entry Point

Multi-agent financial deep research:
  Data Collection → Data Analysis (+ VLM chart critique) → Report Generation → DOCX/PDF

Usage:
  python scripts/run.py --config my_config.yaml
  python scripts/run.py --target-name "Apple Inc." --stock-code AAPL --target-type company --language en
"""

import sys
import os
import asyncio
import argparse
import logging
import traceback
from pathlib import Path
from collections import defaultdict

# ── Path setup: ensure scripts/ is on sys.path so `from src.xxx import yyy` works ──
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from dotenv import load_dotenv

# Optional dependency guards
_AKSHARE_AVAILABLE = True
try:
    import akshare  # noqa: F401
except ImportError:
    _AKSHARE_AVAILABLE = False

_PANDOC_AVAILABLE = True
try:
    import pypandoc  # noqa: F401
except ImportError:
    _PANDOC_AVAILABLE = False

# ── Depth presets: controls max_iterations per agent ──
DEPTH_PRESETS = {
    "low": {
        "label": "快速 (Low)",
        "collect_iterations": 3,
        "analysis_iterations": 2,
        "report_iterations": 2,
        "estimated_llm_calls": "~30-50",
        "estimated_time": "1-2 小时",
    },
    "medium": {
        "label": "标准 (Medium)",
        "collect_iterations": 5,
        "analysis_iterations": 3,
        "report_iterations": 3,
        "estimated_llm_calls": "~50-80",
        "estimated_time": "3-4 小时",
    },
    "high": {
        "label": "深度 (High)",
        "collect_iterations": 8,
        "analysis_iterations": 5,
        "report_iterations": 5,
        "estimated_llm_calls": "~80-120+",
        "estimated_time": "5-6 小时",
    },
}


def infer_market(stock_code: str | None) -> str:
    """Infer the most likely market when the user did not provide one."""
    code = str(stock_code or "").strip().upper()
    if code.isdigit() and len(code) == 6:
        return "A"
    if code.isdigit() and 1 <= len(code) <= 5:
        return "HK"
    return "US"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(
        description="FinSight: Multi-agent financial deep research system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run.py --config my_config.yaml
  python scripts/run.py --target-name "Apple Inc." --stock-code AAPL --target-type company --language en
  python scripts/run.py --target-name "New Energy" --target-type industry --language en --no-charts
        """,
    )

    # Config files
    p.add_argument("--config", default="my_config.yaml",
                   help="YAML config file path (default: my_config.yaml)")
    p.add_argument("--env-file", default=None,
                   help=".env file path (default: CWD/.env → ~/.env)")

    # Target overrides
    p.add_argument("--target-name", default=None, help="Research target name")
    p.add_argument("--stock-code", default=None, help="Ticker symbol")
    p.add_argument("--market", default=None, choices=["A", "HK", "US"],
                   help="Market: A (China A-share), HK, or US. Inferred from stock code when omitted.")
    p.add_argument("--target-type", default=None,
                   choices=["company", "industry", "macro", "general"],
                   help="Research type")
    p.add_argument("--language", default=None, choices=["en", "zh"],
                   help="Output language")
    p.add_argument("--output-dir", default=None, help="Output directory")

    # Model overrides
    p.add_argument("--model", default=None, help="Override LLM model name")
    p.add_argument("--vlm-model", default=None, help="Override VLM model name")
    p.add_argument("--embedding-model", default=None, help="Override embedding model name")

    # Execution controls
    p.add_argument("--depth", default="medium", choices=["low", "medium", "high"],
                   help="Research depth: low (fast, ~1-3min), medium (balanced, ~3-8min), "
                        "high (thorough, ~5-15min). Default: medium")
    p.add_argument("--max-concurrent", type=int, default=3,
                   help="Max concurrent agents (default: 3, 0=unlimited)")
    p.add_argument("--no-charts", action="store_true", help="Disable chart generation")
    p.add_argument("--allow-generated-code", action="store_true",
                   help="Allow LLM-generated Python. Only use with trusted inputs in an isolated environment.")
    p.add_argument("--resume", action="store_true",
                   help="Resume from trusted local checkpoints. Never use checkpoints from untrusted directories.")
    p.add_argument("--no-resume", action="store_true", help=argparse.SUPPRESS)

    return p.parse_args()


def load_env(args: argparse.Namespace) -> None:
    """Discover and load .env file from explicit path, CWD, or home directory."""
    loaded = False
    if args.env_file:
        if os.path.exists(args.env_file):
            load_dotenv(args.env_file)
            loaded = True
        else:
            print(f"WARNING: --env-file '{args.env_file}' not found, falling back...")

    if not loaded:
        loaded = load_dotenv()  # CWD

    if not loaded:
        home_env = Path.home() / ".env"
        if home_env.exists():
            load_dotenv(str(home_env))
            loaded = True

    if not loaded:
        print("NOTE: No .env file found. Using existing environment variables.")

    # Validate required env vars
    required = {
        "DS_MODEL_NAME": os.getenv("DS_MODEL_NAME"),
        "DS_API_KEY": os.getenv("DS_API_KEY"),
        "DS_BASE_URL": os.getenv("DS_BASE_URL"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Set them in a .env file or in your environment.")
        print("See SKILL.md for configuration details.")
        sys.exit(1)

    # Warn about optional but recommended vars
    optional_warn = {
        "VLM_MODEL_NAME": os.getenv("VLM_MODEL_NAME"),
        "VLM_API_KEY": os.getenv("VLM_API_KEY"),
        "VLM_BASE_URL": os.getenv("VLM_BASE_URL"),
    }
    missing_opt = [k for k, v in optional_warn.items() if not v]
    if missing_opt:
        print(f"NOTE: VLM not fully configured (missing: {', '.join(missing_opt)}). "
              "Chart critique will be skipped.")


def build_config(args: argparse.Namespace) -> dict:
    """Build merged config: built-in defaults → YAML file → CLI args."""
    # Built-in defaults
    config = {
        "target_name": "Unknown",
        "target_type": "general",
        "language": "en",
        "output_dir": "./outputs",
        "custom_collect_tasks": [],
        "custom_analysis_tasks": [],
        "enable_chart": True,
        "enable_generated_code": False,
        "save_note": None,
        "rate_limits": {
            "search_engines": 1.0,
            "financial_apis": 0.5,
            "fred_api": 0.5,
            "yfinance": 0.2,
        },
        "use_collect_data_cache": True,
        "use_analysis_cache": True,
        "use_report_outline_cache": True,
        "use_full_report_cache": True,
        "use_post_process_cache": True,
    }

    # Layer 1: YAML config file
    config_path = args.config
    if os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f) or {}
            config.update(yaml_config)
            print(f"Loaded config from: {config_path}")
        except Exception as e:
            print(f"WARNING: Failed to load config '{config_path}': {e}")
    else:
        if args.config != "my_config.yaml":
            print(f"WARNING: Config file '{args.config}' not found, using defaults.")
        else:
            print("No my_config.yaml found, using CLI args / defaults.")

    # Layer 2: CLI overrides (only if explicitly provided)
    if args.target_name is not None:
        config["target_name"] = args.target_name
    if args.stock_code is not None:
        config["stock_code"] = args.stock_code
    if args.market is not None:
        config["market"] = args.market
    if args.target_type is not None:
        config["target_type"] = args.target_type
    if args.language is not None:
        config["language"] = args.language
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.no_charts:
        config["enable_chart"] = False
    # A config file must not be able to enable in-process code execution.
    config["enable_generated_code"] = bool(args.allow_generated_code)
    config["allow_unsafe_resume"] = args.resume and not args.no_resume
    if not config.get("market"):
        config["market"] = infer_market(config.get("stock_code"))

    # Build llm_config_list from env vars (with optional overrides)
    llm_config_list = []

    # LLM
    llm_entry = {
        "model_name": args.model or os.getenv("DS_MODEL_NAME", "deepseek-chat"),
        "api_key": os.getenv("DS_API_KEY", ""),
        "base_url": os.getenv("DS_BASE_URL", "https://api.deepseek.com/v1"),
        "generation_params": {
            "temperature": 0.7,
            "max_tokens": 32768,
            "top_p": 0.95,
        },
    }
    llm_config_list.append(llm_entry)

    # Embedding (optional)
    emb_name = args.embedding_model or os.getenv("EMBEDDING_MODEL_NAME")
    if emb_name:
        llm_config_list.append({
            "model_name": emb_name,
            "api_key": os.getenv("EMBEDDING_API_KEY", ""),
            "base_url": os.getenv("EMBEDDING_BASE_URL", ""),
        })

    # VLM (optional)
    vlm_name = args.vlm_model or os.getenv("VLM_MODEL_NAME")
    if vlm_name:
        llm_config_list.append({
            "model_name": vlm_name,
            "api_key": os.getenv("VLM_API_KEY", ""),
            "base_url": os.getenv("VLM_BASE_URL", ""),
        })

    config["llm_config_list"] = llm_config_list

    return config


async def run_pipeline(config_dict: dict, args: argparse.Namespace) -> None:
    """Execute the full research pipeline: collect → analyze → report."""
    from src.config import Config
    from src.agents import DataCollector, DataAnalyzer, ReportGenerator
    from src.memory import Memory
    from src.utils import setup_logger, get_logger

    get_logger().set_agent_context("runner", "main")

    resume = args.resume and not args.no_resume
    max_concurrent = args.max_concurrent if args.max_concurrent > 0 else None
    depth = args.depth if args.depth != "medium" else config_dict.get("depth", "medium")
    depth_cfg = DEPTH_PRESETS[depth]

    use_llm_name = config_dict["llm_config_list"][0]["model_name"]
    use_vlm_name = args.vlm_model or os.getenv("VLM_MODEL_NAME")
    use_embedding_name = args.embedding_model or os.getenv("EMBEDDING_MODEL_NAME")
    enable_generated_code = config_dict.get("enable_generated_code", False)
    enable_chart = config_dict.get("enable_chart", True) and enable_generated_code

    # Initialize config
    config = Config(config_dict=config_dict)

    # Pre-flight checks
    print(f"\n{'='*60}")
    print(f"  FinSight Research Pipeline")
    print(f"  Target: {config_dict['target_name']}")
    print(f"  Type:   {config_dict['target_type']}")
    print(f"  Depth:  {depth_cfg['label']} ({depth_cfg['estimated_time']})")
    print(f"  LLM:    {use_llm_name}")
    if use_vlm_name:
        print(f"  VLM:    {use_vlm_name}")
    if use_embedding_name:
        print(f"  Embed:  {use_embedding_name}")
    print(f"  Market: {config_dict.get('market', 'US')}")
    print(f"  Output: {config.working_dir}")
    print(f"  Resume: {resume}")
    print(f"  Generated code: {enable_generated_code}")
    if not _AKSHARE_AVAILABLE:
        print(f"  NOTE:   akshare not installed — China/HK market unavailable")
    if not _PANDOC_AVAILABLE:
        print(f"  NOTE:   pypandoc not installed — DOCX output unavailable (Markdown only)")
    print(f"{'='*60}\n")

    collect_tasks = config_dict.get("custom_collect_tasks", [])
    analysis_tasks = config_dict.get("custom_analysis_tasks", [])

    # Initialize memory
    memory = Memory(config=config)

    # Initialize logger
    log_dir = os.path.join(config.working_dir, "logs")
    logger = setup_logger(log_dir=log_dir, log_level=logging.INFO)
    if config_dict.get("enable_chart", True) and not enable_generated_code:
        logger.info("Chart generation disabled because generated code is not explicitly enabled")

    if resume:
        memory.load()
        logger.info("Memory state loaded")

    # Generate tasks
    research_query = (
        f"Research target: {config_dict['target_name']} "
        f"(ticker: {config_dict.get('stock_code', 'N/A')}), "
        f"target type: {config_dict.get('target_type', 'company')}"
    )

    if not memory.generated_collect_tasks:
        logger.info("Generating collect tasks via LLM...")
        generated_collect = await memory.generate_collect_tasks(
            query=research_query,
            use_llm_name=use_llm_name,
            max_num=depth_cfg["collect_iterations"],
            existing_tasks=collect_tasks,
        )
        logger.info(f"Generated {len(generated_collect)} collect tasks")
    else:
        generated_collect = memory.generated_collect_tasks
        logger.info(f"Using {len(generated_collect)} cached collect tasks")

    if not memory.generated_analysis_tasks:
        logger.info("Generating analysis tasks via LLM...")
        generated_analysis = await memory.generate_analyze_tasks(
            query=research_query,
            use_llm_name=use_llm_name,
            max_num=depth_cfg["analysis_iterations"],
            existing_tasks=analysis_tasks,
        )
        logger.info(f"Generated {len(generated_analysis)} analysis tasks")
    else:
        generated_analysis = memory.generated_analysis_tasks
        logger.info(f"Using {len(generated_analysis)} cached analysis tasks")

    # Merge tasks
    all_collect = list(collect_tasks) + [t for t in generated_collect if t not in collect_tasks]
    all_analysis = list(analysis_tasks) + [t for t in generated_analysis if t not in analysis_tasks]

    logger.info(f"Total: {len(all_collect)} collect + {len(all_analysis)} analysis tasks")

    # Build task queue with priorities
    tasks_to_run = []

    for task in all_collect:
        tasks_to_run.append({
            "agent_class": DataCollector,
            "task_input": {
                "input_data": {
                    "task": (f"Research target: {config_dict['target_name']} "
                             f"(ticker: {config_dict.get('stock_code', 'N/A')}), "
                             f"task: {task}"),
                },
                "echo": True,
                "max_iterations": depth_cfg["collect_iterations"],
                "resume": resume,
            },
            "agent_kwargs": {"use_llm_name": use_llm_name, "enable_code": enable_generated_code},
            "priority": 1,
        })

    for task in all_analysis:
        tasks_to_run.append({
            "agent_class": DataAnalyzer,
            "task_input": {
                "input_data": {
                    "task": f"Research target: {config_dict['target_name']} "
                            f"(ticker: {config_dict.get('stock_code', 'N/A')})",
                    "analysis_task": task,
                },
                "echo": True,
                "max_iterations": depth_cfg["analysis_iterations"],
                "resume": resume,
                "enable_chart": enable_chart,
            },
            "agent_kwargs": {
                "use_llm_name": use_llm_name,
                "use_vlm_name": use_vlm_name,
                "use_embedding_name": use_embedding_name,
                "enable_code": enable_generated_code,
            },
            "priority": 2,
        })

    # Report generation
    tasks_to_run.append({
        "agent_class": ReportGenerator,
        "task_input": {
            "input_data": {
                "task": f"Research target: {config_dict['target_name']} "
                        f"(ticker: {config_dict.get('stock_code', 'N/A')})",
                "task_type": config_dict.get("target_type", "company"),
            },
            "echo": True,
            "max_iterations": depth_cfg["report_iterations"],
            "resume": resume,
            "enable_chart": enable_chart,
        },
        "agent_kwargs": {
            "use_llm_name": use_llm_name,
            "use_embedding_name": use_embedding_name,
            "enable_code": enable_generated_code,
        },
        "priority": 3,
    })

    # Obtain or create agents
    agents_info = []
    for task_info in tasks_to_run:
        agent = await memory.get_or_create_agent(
            agent_class=task_info["agent_class"],
            task_input=task_info["task_input"],
            resume=resume,
            priority=task_info["priority"],
            **task_info["agent_kwargs"],
        )
        agents_info.append({
            "agent": agent,
            "task_input": task_info["task_input"],
            "priority": task_info["priority"],
        })

    memory.save()

    # Execute by priority tier
    priority_groups = defaultdict(list)
    for ai in agents_info:
        priority_groups[ai["priority"]].append(ai)

    for priority in sorted(priority_groups.keys()):
        group = priority_groups[priority]
        n_tasks = len(group)
        logger.info(f"\n{'='*40}")
        logger.info(f"Priority {priority}: {n_tasks} task(s)")
        logger.info(f"{'='*40}")

        # Skip completed tasks on resume
        active = []
        for ai in group:
            agent = ai["agent"]
            if resume and memory.is_agent_finished(agent.id):
                logger.info(f"  Agent {agent.id} already completed — skip")
                continue
            active.append(ai)

        if not active:
            logger.info(f"  All priority {priority} tasks complete")
            continue

        semaphore = asyncio.Semaphore(max_concurrent) if max_concurrent else None

        async def _run_one(ai):
            agent = ai["agent"]
            if semaphore:
                async with semaphore:
                    logger.info(f"  Starting agent {agent.id}")
                    return await agent.async_run(**ai["task_input"])
            else:
                logger.info(f"  Starting agent {agent.id}")
                return await agent.async_run(**ai["task_input"])

        coros = [asyncio.create_task(_run_one(ai)) for ai in active]
        results = await asyncio.gather(*coros, return_exceptions=True)

        for ai, result in zip(active, results):
            agent = ai["agent"]
            if isinstance(result, Exception):
                tb = "".join(traceback.format_exception(
                    type(result), result, result.__traceback__
                ))
                logger.error(f"  FAILED: Agent {agent.id}\n{tb}")
            else:
                logger.info(f"  Done: Agent {agent.id}")

        logger.info(f"Priority {priority} group complete\n")

    memory.save()
    logger.info("All tasks completed")

    # Print output summary
    working_dir = config.working_dir
    print(f"\n{'='*60}")
    print(f"  Pipeline Complete!")
    print(f"  Output directory: {working_dir}")
    for fname in ["final_report.docx", "final_report.md", "final_report.pdf"]:
        fpath = os.path.join(working_dir, fname)
        if os.path.exists(fpath):
            print(f"     {fname}")
    print(f"{'='*60}\n")


def main() -> None:
    args = parse_args()
    load_env(args)
    config_dict = build_config(args)
    asyncio.run(run_pipeline(config_dict, args))


if __name__ == "__main__":
    main()
