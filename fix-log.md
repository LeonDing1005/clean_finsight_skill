# FinSight Fix Log

Record skill maintenance fixes here when making changes during use.

## Template

**Date**: YYYY-MM-DD

**File**: `path/to/file.py`

**Issue**: What broke, including the exact error when available.

**Root Cause**: Why it happened.

**Fix**: What changed.

## 修复 #1: DataCollector/ReportGenerator enable_code=False 时空指针 (18:46)

**问题**: `AttributeError: 'DataCollector' object has no attribute 'code_executor'`
**根因**: `_prepare_executor()` 无条件访问 `self.code_executor`，但当 `enable_code=False` 时 `BaseAgent.__init__` 不创建该属性。DataAnalyzer 已有 guard (`if not self.enable_code: return`)，但 DataCollector 和 ReportGenerator 遗漏了。
**修复**: 在 DataCollector 和 ReportGenerator 的 `_prepare_executor()` 开头添加 `if not self.enable_code: return`
**文件**: `scripts/src/agents/data_collector/data_collector.py`, `scripts/src/agents/report_generator/report_generator.py`

**累计修复**: 1 个 Bug
