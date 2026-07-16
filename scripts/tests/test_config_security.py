"""Regression tests for configuration security boundaries."""

import json
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


class ConfigSecurityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
