---
name: finsight-research
description: >-
  Multi-agent financial deep research system for generating publication-ready
  DOCX/PDF reports with automated data collection, chart generation
  (VLM-reviewed), and structured analysis. Supports US (yfinance/FRED), China
  A-share (akshare), Hong Kong, and general web-based research. Use when user
  needs: (1) in-depth financial research report on a company, industry, or macro
  topic, (2) automated data gathering + analysis + report pipeline, (3) "deep
  research" on stocks or financial subjects, (4) 行业研究报告, 个股深度分析, 深度研报,
  financial due diligence.
---

# FinSight Research Skill

Multi-agent financial deep research pipeline. From a ticker symbol to a publication-ready report in one command.

---

##  GATE 0: Task Detection — RUN THIS FIRST

> **CRITICAL: This is an absolute gate. You MUST complete this check before reading any other section of this file. Do NOT check Python, pip, pandoc, or .env. Do NOT run any commands. The ONLY thing you do right now is answer one question: did the user specify a research target?**

### How to Detect a Target

Read the user's message carefully. A target is **PRESENT** only if the message explicitly contains at least one of:

| Category | Examples (must be IN the user's message, not imagined) |
|----------|--------------------------------------------------------|
| Ticker symbol | `AAPL`, `600519`, `00020.HK`, `300750`, `NVDA` |
| Company name | "Apple", "贵州茅台", "Tesla", "宁德时代" |
| Industry keyword + research intent | "新能源汽车 分析", "半导体 研究" |
| Explicit research command | "帮我研究...", "分析一下...", "research...", "深度分析..." |

**If the user's message is empty, contains only the skill name with no arguments, or contains only non-research text → NO target detected.**

###  BRANCH A: NO Target Detected

**IMMEDIATE ACTION — do not pass go, do not collect $200:**

1. Output the introduction below EXACTLY as written.
2. **STOP.** Do NOT proceed to any other section. Do NOT read further. Do NOT run any commands.

> ## FinSight Research — 多智能体金融深度研究系统
>
> FinSight 是一个**全自动化金融深度研报生成系统**，从数据采集到最终报告一气呵成。
>
> ### 核心能力
> | 阶段 | 做什么 |
> |------|--------|
> | Phase 1 · 数据采集 | 自动收集行情、财报、新闻、政策、机构持仓等多维度数据 |
> | Phase 2 · 数据分析 | LLM 生成 Python 分析代码并执行，产出图表和量化结论 |
> | Phase 3 · 报告生成 | 大纲→分节撰写→润色→图表插入→封面→参考文献 |
>
> ### 支持的市场
> -  美股 (yfinance + FRED)
> -  A股 (akshare)
> -  港股 (akshare)
> -  行业/宏观研究 (搜索引擎)
>
> ### 研究深度
> | 深度 | 耗时 |
> |------|------|
> | `low` | 1-2 小时 |
> | `medium` | 3-4 小时 |
> | `high` | 5-6 小时 |
>
> ### 输出格式
> DOCX / PDF / Markdown，含图表和专业排版
>
> ### 使用方式
> ```
> /finsight-research <标的> [--depth low|medium|high] [--target-type company|industry|macro|general]
> ```
> **示例**：
> - `/finsight-research AAPL --target-type company` — 公司深度研究（支持美股/A股/港股）
> - `/finsight-research "新能源汽车" --target-type industry` — 行业产业链研究
> - `/finsight-research "美联储加息周期" --target-type macro` — 宏观政策研究
> - `/finsight-research "比特币与黄金的避险属性对比" --target-type general` — 通用主题研究
>
> **请告诉我你想研究什么？**

###  BRANCH B: Target DETECTED

**Before doing anything else, you MUST declare the target explicitly in your response:**

> ```
>  检测到研究目标:
>    标的名称: <extracted name>
>    股票代码: <extracted ticker, or "N/A">
>    研究深度: <depth from user, or "待确认">
> ```

Only AFTER making this declaration may you proceed to **Target Type & Task Customization** below.

**If you are unsure whether the user specified a target, default to BRANCH A.**

---

##  Target Type & Task Customization (BRANCH B Only)

> **This section runs immediately after GATE 0 BRANCH B, BEFORE Session Initialization.**

### Step 1: Confirm Target Type

**If the user already specified `--target-type` in their message → skip to Step 2.**

Otherwise, use `AskUserQuestion` to confirm the `target_type`. Choose the recommended option based on context:

| Scenario | Recommended |
|----------|-------------|
| User provided a ticker (e.g. `AAPL`, `600519`) | `company` |
| User provided an industry keyword (e.g. "新能源", "半导体") | `industry` |
| User provided a macro topic (e.g. "通胀", "利率") | `macro` |
| Cannot determine | `general` |

The options to present:

| Label | Value | Description |
|-------|-------|-------------|
| 公司研究 `company` | company | 个股深度研究 — 财报、估值、竞争力、风险分析 |
| 行业研究 `industry` | industry | 产业链研究 — 竞争格局、政策环境、发展趋势 |
| 宏观研究 `macro` | macro | 宏观分析 — 经济指标、货币政策、周期研判 |
| 通用研究 `general` | general | 综合研究 — 不限类型，LLM 自主决定分析框架 |

### Step 2: Confirm Remaining Parameters

Check if the following parameters were specified by the user. For each missing one, ask:

- `market`: Infer from ticker if possible (`A` / `US` / `HK`), otherwise ask
- `language`: Infer from target name (Chinese name → `zh`, English → `en`), otherwise ask
- `depth`: **MUST ask if not specified** — `low` / `medium` / `high`. Do NOT default.
- `enable_chart`: Default `true` if not specified

### Step 3: LLM Generates Suggested Tasks

> ** CRITICAL: Do NOT proceed past this step until the user explicitly confirms "开始执行" or equivalent.**

Once all parameters (target_type, market, language, depth) are confirmed, use the LLM (the model configured via `DS_MODEL_NAME`) to generate suggested research tasks.

**How to generate tasks:**

Construct a prompt for the LLM that includes:
- The research target (name, ticker, type, market)
- The research depth
- Instructions to generate two lists in Chinese (or the selected language):
  - `custom_collect_tasks`: 5-15 data collection tasks (depending on depth)
  - `custom_analysis_tasks`: 5-15 analysis tasks (depending on depth)

**Task count by depth:**

| Depth | Collect Tasks | Analysis Tasks |
|-------|---------------|----------------|
| `low` | 5-6 | 5-6 |
| `medium` | 8-10 | 8-10 |
| `high` | 12-15 | 12-15 |

**LLM prompt template (use in your own generation, send via the chat model you are running on):**

```
你是一个金融研究分析师。请为以下研究目标生成数据采集任务和分析任务列表。

研究目标: {target_name}
股票代码: {stock_code}
研究类型: {target_type}
市场: {market}
研究深度: {depth}
语言: {language}

请生成两个列表：

## 数据采集任务 (custom_collect_tasks)
- 根据研究深度 {depth}，生成 {task_count_collect} 个数据采集任务
- 每个任务用一句话描述需要采集什么数据
- 覆盖：行情数据、财务报表、新闻舆情、机构持仓、行业对比、宏观指标等（根据研究类型调整）

## 分析任务 (custom_analysis_tasks)
- 根据研究深度 {depth}，生成 {task_count_analyze} 个分析任务
- 每个任务用一句话描述需要分析什么
- 覆盖：趋势分析、估值分析、竞争力分析、风险分析、情景推演等（根据研究类型调整）

请直接输出两个列表，格式如下：
custom_collect_tasks:
  - "任务描述1"
  - "任务描述2"
custom_analysis_tasks:
  - "任务描述1"
  - "任务描述2"
```

### Step 4: Present Tasks to User & Await Confirmation

Display the generated tasks to the user in a clean format:

```
 研究配置确认
   标的: {target_name} ({stock_code})
   类型: {target_type}
   市场: {market}
   深度: {depth}
   语言: {language}

 数据采集任务 ({N} 项):
   1. 收集目标公司的最新财务数据和市场表现
   2. 收集行业趋势、竞争格局和关键新闻

 分析任务 ({N} 项):
   1. 分析收入、利润、现金流和估值水平
   2. 分析风险因素、增长驱动和投资结论

---
请确认以上任务是否合适：
  - 回复 "开始执行" 或 "确认" → 立即开始研究
  - 回复修改意见（如 "增加XXX分析"、"删除第3项采集任务"、"把估值分析改成DCF估值"）→ 我将根据你的意见调整任务并重新展示
```

### Step 5: Handle User Feedback (Loop)

- **User confirms** ("开始执行", "确认", "OK", "没问题", "可以") → **exit the loop** and proceed to **Session Initialization**
- **User requests modifications** → update the task lists based on their feedback:
  - Parse the modification request
  - Add/remove/modify the affected tasks
  - Regenerate or manually adjust the list
  - **Go back to Step 4** and present the updated tasks again
- **Repeat** this loop until the user explicitly confirms to start

>  **Important**: Do NOT proceed to Session Initialization, .env setup, or any environment checks until the user has explicitly confirmed the tasks. The loop must keep going until confirmation is received.

### After Confirmation

1. Store the finalized `target_type`, market, language, depth
2. Store the finalized `custom_collect_tasks` and `custom_analysis_tasks` lists
3. Proceed to **Session Initialization** (below)

---

## Prerequisites

- Python 3.10+
- [Pandoc](https://pandoc.org/installing.html) (for DOCX/PDF export; optional, falls back to Markdown)

### Install Dependencies

```bash
# Core (always needed — US market, analysis, charts)
pip install -r scripts/requirements-core.txt

# Optional: Chinese A-share + HK market data
pip install -r scripts/requirements-optional.txt

# Optional: Playwright browser automation
playwright install chromium
```

### API Keys Setup

Create a `.env` file (in working directory or `~/.env`) with:

| Variable | Required | Purpose |
|----------|----------|---------|
| `DS_MODEL_NAME` | **Yes** | Main LLM model (e.g. `deepseek-chat`, `gpt-4o`) |
| `DS_API_KEY` | **Yes** | LLM API key |
| `DS_BASE_URL` | **Yes** | LLM API base URL |
| `VLM_MODEL_NAME` | No | Vision model for chart critique |
| `VLM_API_KEY` | No | VLM API key |
| `VLM_BASE_URL` | No | VLM API base URL |
| `EMBEDDING_MODEL_NAME` | No | Embedding model for semantic search |
| `EMBEDDING_API_KEY` | No | Embedding API key |
| `EMBEDDING_BASE_URL` | No | Embedding API base URL |
| `SERPER_API_KEY` | No | Google Search via Serper |

If VLM/Embedding vars are missing, chart critique and semantic search degrade gracefully.

Never store API keys in research output, reports, or committed configuration files. The runtime writes a redacted `config.json` only.

---

## Session Initialization: Config Persistence

**This section runs after task detection confirms a research target, BEFORE environment checks.**

> `{SKILL_DIR}` below refers to the directory containing this SKILL.md file.

###  GATE 1: Target Verification (Secondary Check)

**Before proceeding with .env or config, verify that you actually detected a target in GATE 0.**

Ask yourself:
1. Did the user's message literally contain a ticker, company name, or research keyword?
2. Or did I imagine/fabricate/hallucinate one?

**If you cannot quote the exact target text from the user's message → STOP immediately and go back to GATE 0 BRANCH A (show the introduction).**

**If you fabricated a target that the user never provided → STOP immediately and go back to GATE 0 BRANCH A.**

### Part A: `.env` Check

Check if `{SKILL_DIR}/.env` file exists.

**If `.env` exists:**
1. Read the file and parse key=value pairs
2. Verify required variables are set: `DS_MODEL_NAME`, `DS_API_KEY`, `DS_BASE_URL`
3. If any required vars are missing → ask user only for the missing values, append to `.env`
4. Optional vars (`VLM_*`, `EMBEDDING_*`, `SERPER_API_KEY`) missing → no action needed, they degrade gracefully

**If `.env` does NOT exist:**
1. Ask the user:
   - Which LLM provider? (e.g. DeepSeek, OpenAI-compatible)
   - What's the API key?
   - What's the base URL? (e.g. `https://api.deepseek.com/v1`)
2. Create `{SKILL_DIR}/.env` with the provided values:
   ```
   DS_MODEL_NAME=<user-provided>
   DS_API_KEY=<user-provided>
   DS_BASE_URL=<user-provided>
   ```
3. Optional vars can be skipped — user can add them later if needed

### Part B: Research Task Config

**All parameters have been gathered and confirmed in the Target Type & Task Customization step above:**
- `target_name`: Company/industry name (from GATE 0)
- `stock_code`: Ticker symbol (from GATE 0, or "N/A")
- `target_type`: Confirmed by user (company / industry / macro / general)
- `market`: Confirmed by user (A / US / HK)
- `language`: Confirmed by user (zh / en)
- `depth`: Confirmed by user (low / medium / high)
- `enable_chart`: Confirmed by user (true / false)
- `custom_collect_tasks`: Finalized list confirmed by user
- `custom_analysis_tasks`: Finalized list confirmed by user

**Generate the YAML config file:**
1. Create `{SKILL_DIR}/config_{STOCK_CODE}.yaml`
2. If a config file with the same name already exists → ask: "Found existing config for {STOCK_CODE}. Use it (1), regenerate (2), or edit (3)?"
3. Save the config with ALL parameters including the finalized task lists
4. Use `${DS_MODEL_NAME}` style env var references in `llm_config_list` — NEVER hardcode API keys

**Config file template:**
```yaml
target_name: "{TARGET_NAME}"
stock_code: "{STOCK_CODE}"
target_type: company
market: A
language: zh
depth: medium
output_dir: "./outputs"
enable_chart: true
use_collect_data_cache: true
use_analysis_cache: true
use_report_outline_cache: true
use_full_report_cache: true
rate_limits:
  search_engines: 1.0
  financial_apis: 0.5
  yfinance: 0.2
custom_collect_tasks:
  - "Task description 1"
  - "Task description 2"
custom_analysis_tasks:
  - "Task description 1"
  - "Task description 2"
llm_config_list:
  - model_name: "${DS_MODEL_NAME}"
    api_key: "${DS_API_KEY}"
    base_url: "${DS_BASE_URL}"
    generation_params:
      temperature: 0.7
      max_tokens: 32768
```

After this section, proceed to **Environment Setup (Auto)**.

---

## Environment Setup (Auto)

**When this skill is invoked, you MUST run through the following environment check first. Do NOT skip to the research pipeline before confirming the environment is ready.**

### Step 1: Check Python Version

```bash
python --version 2>&1
```

-  **Python 3.10+** → proceed to Step 2
-  **Not installed or < 3.10** → stop and tell the user: *"FinSight 需要 Python 3.10+，请先安装：https://www.python.org/downloads/"*

### Step 2: Check & Auto-Install Pandoc

First, check if pandoc is installed:

```bash
pandoc --version 2>&1
```

-  **Installed** → proceed to Step 3
-  **Not installed** → attempt auto-install via winget:

```bash
winget install --id JohnMacFarlane.Pandoc --silent --accept-package-agreements --accept-source-agreements 2>&1
```

After winget completes, verify installation:

```bash
pandoc --version 2>&1
```

-  **winget install succeeded + pandoc works** → proceed to Step 3
-  **winget not available or install failed** → warn user: *" Pandoc 自动安装失败。报告将只能输出 Markdown，无法生成 DOCX/PDF。可手动安装：https://pandoc.org/installing.html"*，继续 Step 3（不阻断）

### Step 3: Check & Install Core Pip Packages

> `{SKILL_DIR}` below refers to the directory containing this SKILL.md file.

```bash
pip install -r {SKILL_DIR}/scripts/requirements-core.txt 2>&1
```

- This will install all 19 core packages. If some are already installed, pip skips them.
- After installation, verify the critical import works:

```bash
python -c "import yfinance, pandas, matplotlib; print('Core OK')" 2>&1
```

-  **"Core OK"** → proceed to Step 4

### Step 4: Offer Optional Packages

Check if the user needs China A-share / HK market data:

- If the user's research target involves **A股/港股**，install optional deps:

```bash
pip install -r {SKILL_DIR}/scripts/requirements-optional.txt 2>&1
```

- Then verify:

```bash
python -c "import akshare; print('A-Share OK')" 2>&1
```

-  如果 akshare 导入失败或遇到 DNS 问题，提醒用户参考 `dns_patch.py`（东方财富 DNS 劫持修复）。

### Step 5: Summary

After all checks pass, show the user a summary:

```
 FinSight 环境就绪
   Python:  <version>
   Pandoc:  <installed / auto-installed via winget / not installed (Markdown only)>
   核心包:  已安装 (yfinance, pandas, matplotlib, ...)
   A股支持: <已安装 / 未安装>
   LLM:     {DS_MODEL_NAME} @ {DS_BASE_URL}
```

Then proceed to the research pipeline.

---

## Pipeline Launch: Background + Live Progress Reporting

** CRITICAL: The pipeline takes 1-6 hours, far exceeding the Bash timeout (10 min). It MUST run in background, BUT the agent MUST actively report progress to the user in near real-time.**

### Step 1: Launch in Background

```bash
python {SKILL_DIR}/scripts/run.py --config {SKILL_DIR}/config_{STOCK_CODE}.yaml 2>&1
```

Use `run_in_background: true`. The pipeline writes detailed logs to `{output_dir}/{target_name}/logs/`.

### Step 2: Report Progress Live

After launching, tell the user the pipeline has started, then immediately begin the progress-reporting loop:

**What to do every cycle (60-90 second intervals):**

1. Read the latest log file in `{output_dir}/{target_name}/logs/` (or the pipeline's background task output file)
2. Extract and summarize key progress markers:
   - Phase transitions: "Phase 1: Data Collection", "Phase 2: Data Analysis", "Phase 3: Report Generation"
   - Task completions: "", "completed", "done", "生成完成", "分析完成"
   - Errors: any line matching error patterns (see next section)
3. **Report a concise status line to the user** — NOT the raw log. Just a one-liner summary:
   ```
    进度: Phase 2/3 · 数据分析中 (3/5 tasks done) · 已运行 12min · 无报错
   ```
4. Use `ScheduleWakeup` with `delaySeconds: 90` to schedule the next check, so you return to the user each cycle with an update.

### Step 3: On Completion

When the pipeline finishes:
1. Report final status (success/failure)
2. If success: show output file paths
3. If failure: summarize errors and attempted fixes

### Key Rules

- **Do NOT just launch and go silent.** The user expects to see progress.
- **Do NOT dump raw logs.** Summarize into one line per check cycle.
- **Do NOT poll faster than 60s.** LLM calls take time; rapid polling wastes context.
- **If errors detected**, apply the auto-fix decision tree in the next section.

---

## Runtime Monitoring & Auto-Fix

**The agent MUST periodically monitor logs during the pipeline run and auto-fix errors.**

### Monitoring Cadence

After launching the pipeline with `run_in_background: true`:
1. Read the background task output every **60-90 seconds** using `TaskOutput` (non-blocking) or the `.output` file
2. Report a concise one-line status to the user each cycle (see Pipeline Launch section)
3. Do NOT poll more frequently — LLM calls take time and rapid polling wastes context

### Error Detection Patterns

Scan log output for these error signatures:

| Pattern | Meaning | Severity |
|---------|---------|----------|
| `Error code: 401` | API key invalid | **Fatal** — stop, ask user for new key |
| `Error code: 429` | Rate limited | Non-fatal — pipeline auto-retries |
| `Error code: 5xx` | Server error | Non-fatal — pipeline auto-retries |
| `Connection error` | Network issue | Non-fatal — pipeline auto-retries |
| `Code execution: failed` | Agent generated bad code | Non-fatal but may need prompt/code fix |
| `ModuleNotFoundError: No module named 'X'` | Missing dependency | Fix: pip install X |
| `AttributeError: 'list' object has no attribute 'X'` | LLM generated wrong type assumption | May need code fix |
| `ExecutionTimeout: code execution exceeded 120s` | Tool call too slow | Non-fatal — agent auto-retries |
| `ValueError` / `TypeError` | LLM generated bad code | May need prompt/code fix |

### Auto-Fix Decision Tree

On detecting an error:

1. **Read the error context** — what file, what line, what was the agent trying to do
2. **Classify the error**:
   - **API/Network** → let the pipeline auto-retry; no fix needed unless 5 retries all fail
   - **Missing dependency** → install the missing package, then rerun the pipeline (use `--resume` only for trusted local checkpoints)
   - **Code generation error (repeated)** → the LLM's prompt may need improvement; read the agent's system prompt file and fix the instruction
   - **Framework bug** (e.g. `'list' object has no attribute 'columns'`) → read the relevant source file and fix the bug
3. **Apply the fix** — edit the source file directly
4. **Record the fix** — append to `{SKILL_DIR}/fix-log.md`

### Fix Log Format

Every fix MUST be recorded in `{SKILL_DIR}/fix-log.md` using this template:

```markdown
## 修复 #N: 简短标题 (HH:MM)

**问题**: <what broke, paste the exact error>
**根因**: <why it happened>
**修复**: <what was changed>
**文件**: `path/to/file.py`

---
```

### After Pipeline Completes

1. Report to user: success or failure
2. If success: show output file paths and sizes
3. If failure: summarize the error and what was attempted
4. Update fix-log.md with a final tally: `**累计修复**: N 个 Bug`

---

---

## Quick Start

### With a YAML config file (recommended)

```bash
python scripts/run.py --config my_config.yaml
```

### With CLI arguments only (no config file needed)

```bash
# US stock
python scripts/run.py \
  --target-name "Apple Inc." \
  --stock-code AAPL \
  --market US \
  --target-type company \
  --language en

# Chinese A-share
python scripts/run.py \
  --target-name "贵州茅台" \
  --stock-code 600519 \
  --market A \
  --target-type company \
  --language zh

# Industry research (no stock code needed)
python scripts/run.py \
  --target-name "New Energy Vehicles" \
  --target-type industry \
  --language en
```

## Configuration Reference

### YAML Config File (`my_config.yaml`)

```yaml
# === Target ===
target_name: "Apple Inc."        # Research target name
stock_code: "AAPL"               # Ticker symbol
target_type: company             # company | industry | macro | general
market: US                       # US | A | HK
language: en                     # en | zh
output_dir: "./outputs"          # Output directory

# === Tasks (optional — LLM auto-generates if omitted) ===
custom_collect_tasks:
  - "Financial statements (balance sheet, income, cash flow)"
  - "Stock price history and trading volume"

custom_analysis_tasks:
  - "Analyze revenue trends and growth drivers"
  - "Evaluate profitability metrics (ROE, margins)"

# === Charts ===
enable_chart: true               # Generate charts with VLM critique

# === Cache/Resume ===
use_collect_data_cache: true
use_analysis_cache: true
use_report_outline_cache: true
use_full_report_cache: true

# === Rate Limits (seconds between calls) ===
rate_limits:
  search_engines: 1.0
  financial_apis: 0.5
  yfinance: 0.2

# === Models ===
llm_config_list:
  - model_name: "${DS_MODEL_NAME}"
    api_key: "${DS_API_KEY}"
    base_url: "${DS_BASE_URL}"
    generation_params:
      temperature: 0.7
      max_tokens: 32768
```

### CLI Arguments

| Flag | Description | Default |
|------|-------------|---------|
| `--config PATH` | YAML config file path | `my_config.yaml` |
| `--env-file PATH` | .env file path | CWD/.env → ~/.env |
| `--target-name NAME` | Research target | From config or `"Unknown"` |
| `--stock-code CODE` | Ticker symbol | From config |
| `--market A\|HK\|US` | Research market; inferred from ticker when omitted | Inferred |
| `--target-type TYPE` | company/industry/macro/general | `general` |
| `--language en\|zh` | Output language | `en` |
| `--output-dir DIR` | Output directory | `./outputs` |
| `--model MODEL` | Override LLM model name | From env |
| `--vlm-model MODEL` | Override VLM model name | From env |
| `--embedding-model MODEL` | Override embedding model | From env |
| `--max-concurrent N` | Max concurrent agents | `3` |
| `--depth low\|medium\|high` | Research depth: low=fast, medium=balanced, high=thorough | `medium` |
| `--no-charts` | Disable chart generation | Enabled only with `--allow-generated-code` |
| `--allow-generated-code` | Enable LLM-generated Python for trusted inputs only | Disabled |
| `--resume` | Resume from trusted local checkpoints only | Disabled |

### Depth Presets

| Level | Collect | Analyze | Report | Est. LLM Calls | Est. Time |
|-------|---------|---------|--------|----------------|-----------|
| `low` | 3 iters | 2 iters | 2 iters | ~30-50 | 1-2 hours |
| `medium` | 5 iters | 3 iters | 3 iters | ~50-80 | 3-4 hours |
| `high` | 8 iters | 5 iters | 5 iters | ~80-120+ | 5-6 hours |

## Pipeline Flow

### Phase 1: Data Collection
The **DataCollector** agent gathers data using registered tools:
- US market: yfinance (quotes, financials), FRED (macro indicators)
- China/HK market: akshare (quotes, financials, macro)
- Web search: Serper/Bing/DuckDuckGo for unstructured data

### Phase 2: Data Analysis
The **DataAnalyzer** agent performs code-first analysis:
1. LLM generates Python analysis code
2. Code executes in sandbox with access to collected data
3. Charts generated with professional color palettes
4. VLM reviews and critiques chart quality (optional, iterative refinement)

### Phase 3: Report Generation
The **ReportGenerator** agent composes the final report:
1. Generate outline → write sections → polish text
2. Replace chart placeholders with actual images
3. Add cover page, abstract, references
4. Render to DOCX (requires pandoc) and/or PDF

## Supported Markets & Data Sources

| Market | Data Source | Dependency |
|--------|-------------|------------|
| US Equities | yfinance | Core |
| US Macro | FRED (fredapi) | Core |
| China A-Share | akshare | Optional |
| Hong Kong | akshare | Optional |
| Web Search | Serper / Bing / DuckDuckGo | Core (Bing/DDG free) |

## Output

Reports are saved to `output_dir/target_name/`:
- `final_report.docx` — Publication-ready Word document
- `final_report.pdf` — PDF version (if docx2pdf available)
- `final_report.md` — Markdown source
- `memory/` — Checkpoint files (for resume)
- `logs/` — Agent execution logs

## Limitations

- **LLM cost**: Each report requires 50-100+ LLM calls. Use a cost-effective model like DeepSeek for production.
- **akshare instability**: Chinese market APIs change frequently. Update akshare regularly: `pip install akshare --upgrade`
- **Generated code**: Disabled by default. `--allow-generated-code` is only appropriate for trusted inputs in an OS-isolated environment; the bundled executor is not a security boundary.
- **Checkpoint trust**: Resume is disabled by default because legacy checkpoints use Python serialization. Only use `--resume` for checkpoints created locally in a trusted output directory.
- **pandoc required for DOCX**: Without pandoc, only Markdown output is available.
- **VLM optional**: Chart critique is skipped if VLM is not configured. Charts still generate but without quality review.
- **Report quality depends on LLM**: Best results with top-tier models (GPT-4o, DeepSeek-V3, Claude).

## Advanced

### Custom Analysis Tasks

Define `custom_collect_tasks` and `custom_analysis_tasks` in your YAML config to control what the agents focus on. If omitted, the LLM auto-generates appropriate tasks based on the target type.

### Resume from Checkpoint

The pipeline starts fresh by default. Use `--resume` only for checkpoints created locally in a trusted output directory. Checkpoints are stored in `output_dir/target_name/memory/`.

### Concurrency

The pipeline runs data collection tasks in parallel, then analysis tasks in parallel, then report generation. Use `--max-concurrent N` to limit parallelism (default: 3).

### Architecture

See [references/architecture.md](references/architecture.md) for the full architecture documentation including agent details, tool library, memory system, and prompt system.
