# FinSight Architecture Overview

## Multi-Agent Pipeline

FinSight is a multi-stage, memory-centric pipeline for financial deep research:

```
Data Collection → Data Analysis (+ VLM chart critique) → Report Generation → DOCX/PDF
```

Each agent runs in a shared `Memory` space with resumable checkpoints (dill/pickle).

## Agent Roster

| Agent | Purpose | Key Inputs | Outputs |
|-------|---------|------------|---------|
| **Data Collector** | Route and gather structured/unstructured data | Task, ticker/market, custom tasks | Normalized datasets in Memory |
| **Deep Search Agent** | Multi-hop web search + content fetch with source validation | Task, query | Search snippets + crawled pages with citations |
| **Data Analyzer** | Code-first analysis, charting, VLM critique | Task, analysis task, collected data | Analysis report, charts + captions |
| **Report Generator** | Outline → sections → polish → cover/reference → DOCX/PDF | Task, outlines, analysis/memory | Publication-ready report (MD/DOCX/PDF) |

## Tool Library

### Financial Tools
- Stock profile (A/HK)
- Shareholding structure
- Equity valuation metrics (PE/PB/ROE)
- Stock candlestick data (OHLCV)
- Balance sheet / Income statement / Cash-flow statement

### Market Index
- CSI 300 / HSI / SSE / Nasdaq

### Macro Tools (China)
- GDP / CPI / PPI YoY
- LPR benchmark rates
- Unemployment statistics
- Money supply / RRR / FX reserves
- Economic Policy Uncertainty index

### Macro Tools (US)
- CPI YoY (FRED)
- GDP, unemployment, interest rates (FRED)

### Industry Tools
- Manufacturing PMI / Caixin Services PMI
- Industrial value-added growth
- Consumer confidence index
- Retail sales statistics

### Web Search Tools
- Google Search (Serper API)
- Bing Search (requests/Playwright)
- DuckDuckGo / Sogou Search
- Bocha Search (Chinese-focused)
- Web page content fetcher (HTML/PDF → markdown)

## Memory System

The `Memory` class provides:
- **Shared variable space**: All agents read/write to the same memory
- **Semantic search**: `retrieve_relevant_data()` with embedding-based retrieval
- **Task scheduling**: `generate_collect_tasks()` / `generate_analyze_tasks()` auto-generates tasks via LLM
- **Checkpoint/resume**: Full state serialization via dill/pickle

## Checkpoint System

Checkpoints are stored at:
```
outputs/<target_name>/
├── memory/memory.pkl                 # Global memory state
├── agent_working/
│   ├── agent_data_collector_<agent_id>/
│   │   └── .cache/latest.pkl
│   ├── agent_data_analyzer_<agent_id>/
│   │   ├── .cache/latest.pkl
│   │   ├── .cache/charts.pkl
│   │   └── images/
│   └── agent_report_generator_<agent_id>/
│       └── .cache/
│           ├── outline_latest.pkl
│           ├── section_0.pkl
│           └── report_latest.pkl
```

Use `--no-resume` to start fresh; use default to resume from last checkpoint.

## Prompt System

Prompts are organized by agent and report type in YAML files:
```
src/agents/<agent_name>/prompts/
├── general_prompts.yaml       # For general research
├── financial_prompts.yaml     # For financial reports
├── financial_company_prompts.yaml
├── financial_industry_prompts.yaml
└── financial_macro_prompts.yaml
```

The `PromptLoader` selects prompts based on `target_type` in config. Key template variables: `{current_time}`, `{user_query}`, `{data_info}`, `{api_descriptions}`, `{target_language}`.

## Tool Auto-Registration

Tools placed in `src/tools/<category>/` are auto-discovered on import. Each tool extends `Tool` base class and gets registered in the global `_REGISTERED_TOOLS` dict. Categories: financial, macro, industry, web.

## Code Execution Sandbox

The `AsyncCodeExecutor` provides:
- Restricted globals (no `__import__`, no `open` for write, no `os.system`)
- Configurable timeout (default: 30s)
- Variable persistence between executions
- State save/load for checkpointing
