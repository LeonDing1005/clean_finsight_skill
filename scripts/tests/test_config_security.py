"""Regression tests for configuration security boundaries."""

import json
import argparse
import sys
import tempfile
import types
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# Load Config without the optional runtime dependencies used by src.utils.
utils_stub = types.ModuleType("src.utils")
utils_stub.__path__ = [str(SCRIPTS_DIR / "src" / "utils")]
utils_stub.AsyncLLM = type("AsyncLLM", (), {"__init__": lambda self, **kwargs: None})
sys.modules.setdefault("src.utils", utils_stub)

from src.config.config import Config
from src.utils.url_validation import validate_public_http_url
import run


class ConfigSecurityTests(unittest.TestCase):
    def build_args(self, **overrides):
        args = {
            "config": "missing.yaml",
            "env_file": None,
            "target_name": None,
            "stock_code": None,
            "market": None,
            "target_type": None,
            "language": None,
            "output_dir": None,
            "model": None,
            "vlm_model": None,
            "embedding_model": None,
            "depth": "medium",
            "max_concurrent": 3,
            "no_charts": False,
            "allow_generated_code": False,
            "resume": False,
            "no_resume": False,
        }
        args.update(overrides)
        return argparse.Namespace(**args)

    def build_config(self, output_dir, **overrides):
        config = {
            "output_dir": str(output_dir),
            "target_name": "Example Corp",
            "market": "HK",
            "stock_code": "00020",
            "llm_config_list": [],
        }
        config.update(overrides)
        return Config(config_dict=config)

    def test_config_file_redacts_api_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.build_config(
                temp_dir,
                llm_config_list=[{
                    "model_name": "test-model",
                    "api_key": "secret-value",
                    "base_url": "https://example.invalid/v1",
                }],
            )
            saved = json.loads((Path(config.working_dir) / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["llm_config_list"][0]["api_key"], "***REDACTED***")
            self.assertNotIn("secret-value", json.dumps(saved))

    def test_target_name_stays_inside_output_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.build_config(temp_dir, target_name="../../outside")
            output_dir = Path(temp_dir).resolve()
            working_dir = Path(config.working_dir).resolve()
            self.assertEqual(working_dir.parent, output_dir)

    def test_rejects_invalid_a_share_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "six-digit"):
                self.build_config(temp_dir, market="A", stock_code="00020")

    def test_rejects_unknown_market(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "market must"):
                self.build_config(temp_dir, market="EU", stock_code="ABC")

    def test_market_is_inferred_from_stock_code(self):
        self.assertEqual(run.build_config(self.build_args(stock_code="AAPL"))["market"], "US")
        self.assertEqual(run.build_config(self.build_args(stock_code="600519"))["market"], "A")
        self.assertEqual(run.build_config(self.build_args(stock_code="00020"))["market"], "HK")

    def test_market_flag_overrides_inference(self):
        config = run.build_config(self.build_args(stock_code="00020", market="US"))
        self.assertEqual(config["market"], "US")

    def test_config_file_cannot_enable_generated_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("enable_generated_code: true\n", encoding="utf-8")
            config = run.build_config(self.build_args(config=str(config_path)))
            self.assertFalse(config["enable_generated_code"])
            config = run.build_config(self.build_args(config=str(config_path), allow_generated_code=True))
            self.assertTrue(config["enable_generated_code"])

    def test_redacts_common_secret_key_variants(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self.build_config(
                temp_dir,
                service={"access_token": "token-value", "client_secret": "secret-value"},
            )
            saved = json.loads((Path(config.working_dir) / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["service"]["access_token"], "***REDACTED***")
            self.assertEqual(saved["service"]["client_secret"], "***REDACTED***")

    def test_rejects_local_and_non_http_urls(self):
        self.assertIsNone(validate_public_http_url("https://example.com/report"))
        self.assertIsNotNone(validate_public_http_url("file:///etc/passwd"))
        self.assertIsNotNone(validate_public_http_url("http://127.0.0.1:8000"))
        self.assertIsNotNone(validate_public_http_url("http://10.0.0.8/private"))
        self.assertIsNotNone(validate_public_http_url("https://localhost/admin"))


if __name__ == "__main__":
    unittest.main()
