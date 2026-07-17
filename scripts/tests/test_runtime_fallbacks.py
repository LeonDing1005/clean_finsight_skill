"""Regression tests for safe collection and no-embedding report fallbacks."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from src.agents.data_collector.data_collector import DataCollector  # noqa: E402
from src.agents.data_analyzer.data_analyzer import DataAnalyzer  # noqa: E402
from src.agents.report_generator.report_class import Report  # noqa: E402
from src.agents.report_generator.report_generator import (  # noqa: E402
    ReportGenerator,
    _append_images_once,
    _lexical_search,
)
from src.tools import Tool, ToolResult  # noqa: E402


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _Memory:
    def __init__(self, data=None):
        self.data = list(data or [])
        self.log = []

    def add_data(self, item):
        self.data.append(item)

    def add_log(self, *args, **kwargs):
        self.log.append((args, kwargs))

    def get_collect_data(self):
        return list(self.data)

    def get_url_title(self, _url):
        return ""


class _RevenueTool(Tool):
    def __init__(self):
        super().__init__(
            name="revenue_tool",
            description="Return audited revenue",
            parameters=[{"name": "year", "type": "integer", "description": "Fiscal year"}],
        )
        self.calls = []

    async def api_function(self, **kwargs):
        self.calls.append(kwargs)
        return [
            ToolResult(
                name="Audited revenue",
                description="Revenue by fiscal year",
                data={"year": kwargs["year"], "revenue": 100},
                source="Annual report\nhttps://example.com/report",
            )
        ]


class RuntimeFallbackTests(unittest.TestCase):
    def test_structured_tool_call_works_without_generated_code(self):
        tool = _RevenueTool()
        collector = DataCollector.__new__(DataCollector)
        collector.tools = [tool]
        collector.enable_code = False
        collector.collected_data_list = []
        collector.memory = _Memory([object()])
        collector.config = SimpleNamespace(rate_limiter=None)
        collector.current_task_data = {"task": "Collect audited revenue"}
        collector.id = "collector"
        collector.logger = _Logger()

        action_type, action_content = collector._parse_llm_response(
            "<tool_call>"
            + json.dumps({"tool_name": "revenue_tool", "arguments": {"year": 2025}})
            + "</tool_call>"
        )
        result = asyncio.run(collector._execute_action(action_type, action_content))
        asyncio.run(
            collector._handle_tool_call_action(
                json.dumps({"tool_name": "revenue_tool", "arguments": {"year": 2024}})
            )
        )

        self.assertTrue(result["continue"])
        self.assertEqual(tool.calls, [{"year": 2025}, {"year": 2024}])
        self.assertEqual(len(collector.collected_data_list), 2)
        self.assertEqual(len(collector.memory.data), 3)
        self.assertIn("saved automatically", result["result"])

    def test_data_collector_prompt_formats_with_json_example(self):
        prompt_path = (
            SCRIPTS_DIR / "src" / "agents" / "data_collector" / "prompts" / "prompts.yaml"
        )
        template = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))["data_collect"]
        rendered = template.format(
            current_time="2026-07-17",
            target_language="English",
            research_target="Example Inc.",
            code_execution_guidance="Generated Python is disabled.",
            api_descriptions="One test tool",
            task="Collect revenue",
        )
        self.assertIn('<tool_call>{"tool_name":"deepsearch agent"', rendered)

    def test_lexical_search_and_image_append_preserve_all_images(self):
        ranked = _lexical_search(
            "revenue growth",
            ["Cash-flow profile", "Revenue growth accelerated in 2025"],
            top_k=1,
        )
        self.assertEqual(ranked[0]["id"], 1)
        self.assertEqual(_lexical_search("unrelated source", ["audited revenue"], top_k=1), [])

        report = SimpleNamespace(
            sections=[SimpleNamespace(_content=[]), SimpleNamespace(_content=[])]
        )
        images = [(1, "Revenue", "revenue.png"), (2, "Margin", "margin.png")]
        self.assertEqual(_append_images_once(report, images), 2)
        self.assertEqual(report.sections[0]._content, [])
        self.assertEqual(len(report.sections[1]._content), 2)
        self.assertIn("revenue.png", report.sections[1]._content[0])
        self.assertIn("margin.png", report.sections[1]._content[1])

    def test_references_use_lexical_fallback_without_embedding(self):
        source = ToolResult(
            name="Audited revenue filing",
            description="Annual revenue data",
            data={"revenue": 100},
            source="Annual report\nhttps://example.com/report",
        )
        generator = ReportGenerator.__new__(ReportGenerator)
        generator.memory = _Memory([source])
        generator.use_embedding_name = None
        generator.logger = _Logger()

        report = Report("# Example\n\n## Performance")
        report.sections[0].set_content(
            "Revenue increased in 2025 [Source: Audited revenue filing]. "
            "利润保持稳定 [Source： Audited revenue filing]."
        )
        result = asyncio.run(generator._add_reference(report))

        self.assertIn("[1]", result.sections[0].content)
        self.assertNotIn("Source", result.sections[0].content)
        self.assertEqual(result.sections[-1].title, "Reference Data Sources")
        self.assertIn("[Annual report](https://example.com/report)", result.sections[-1].content)

        unmatched_report = Report("# Example\n\n## Risk")
        unmatched_report.sections[0].set_content(
            "A separate claim [Source: Completely unrelated source]."
        )
        unmatched_result = asyncio.run(generator._add_reference(unmatched_report))
        self.assertIn("[Source: Completely unrelated source]", unmatched_result.sections[0].content)
        self.assertEqual(len(unmatched_result.sections), 1)

    def test_analyzer_exposes_full_data_when_code_is_disabled(self):
        analyzer = DataAnalyzer.__new__(DataAnalyzer)
        analyzer.enable_code = False
        item = ToolResult(
            name="Revenue detail",
            description="Audited revenue components",
            data={"segment_revenue": 123456789, "regional_revenue": 987654321},
            source="Annual report",
        )
        formatted = asyncio.run(analyzer._format_collect_data("Analyze revenue", [item]))
        self.assertIn("segment_revenue", formatted)
        self.assertIn("123456789", formatted)

        large_items = [
            ToolResult(
                name=f"Unrelated dataset {index}",
                description="Other metrics",
                data={"payload": "x" * 15000},
                source="Other source",
            )
            for index in range(5)
        ]
        large_items.append(
            ToolResult(
                name="Critical revenue dataset",
                description="Revenue evidence for the requested analysis",
                data={"critical_revenue_value": 42},
                source="Audited filing",
            )
        )
        prioritized = asyncio.run(
            analyzer._format_collect_data("Analyze critical revenue", large_items)
        )
        self.assertIn("critical_revenue_value", prioritized)
        self.assertIn("Unrelated dataset 4", prioritized)


if __name__ == "__main__":
    unittest.main()
