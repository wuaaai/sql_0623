# Phase 4: 业务指标完善 + 代码健康度 — 详细工程计划

## 一、现状诊断（Phase 3 完成后）

| 指标 | 数值 | 问题 |
|------|------|------|
| 业务指标覆盖 | 仅一般公共预算 | 社保/国资/政府基金无指标模板 |
| server.py | 647行 | 含 ServerHandler 定义（应在handler.py） |
| handler.py | 517行 | 缺少 ServerHandler |
| trace 日志 | 1条 | 用于验证查询链，正常 |

**Phase 3 验收通过项**：17工具、\_inject\_guidance、business\_rules.json、system\_prompt 48行 ✅

## 二、目标

1. **业务指标全覆盖**: 4个预算类型都有指标模板
2. **代码归属纠正**: ServerHandler 移到 handler.py
3. **server.py 瘦身**: 647→<600行

---

## 三、任务清单

### 任务1: 补充社保/国资/政府基金指标 JSON

创建3个文件，与 `general_public.json` 格式一致：

#### `social_insurance.json`
```json
{
  "metrics": [
    {
      "id": "shbxjj_income", "name": "社保基金收入", "intent": "完成情况",
      "table": "RDYS_LD_YSZX_SHBXJJYSSRWC",
      "columns": ["RG_NAME","YEAR_MONTH","XM_NAME","YSS","BY_JE","LJ_JE"],
      "amount_col": "BY_JE",
      "default_filters": ["XM_NAME LIKE '%合%计%'"],
      "sql_template": "SELECT {columns} FROM {table} WHERE {filters}",
      "variants": {
        "排名": {"group_by":"RG_NAME","aggregate":"SUM({amount_col})","order":"DESC","limit":20},
        "趋势": {"group_by":"YEAR_MONTH","aggregate":"SUM({amount_col})","order":"ASC"},
        "同比": {"columns_add":["BY_SNTYS","BY_TBE","BY_TBBFS"]}
      }
    },
    {
      "id": "shbxjj_expenditure", "name": "社保基金支出", "intent": "完成情况",
      "table": "RDYS_LD_YSZX_SHBXJJYSZCWC",
      "columns": ["RG_NAME","YEAR_MONTH","XM_NAME","YSS","BY_JE","LJ_JE"],
      "amount_col": "BY_JE",
      "default_filters": ["XM_NAME LIKE '%合%计%'"],
      "sql_template": "SELECT {columns} FROM {table} WHERE {filters}"
    }
  ]
}
```

#### `state_capital.json`
```json
{
  "metrics": [
    {
      "id": "gyzbjy_income", "name": "国有资本经营收入", "intent": "完成情况",
      "table": "RDYS_LD_YSZX_GYZBJYYYSRWC",
      "columns": ["RG_NAME","YEAR_MONTH","XM_NAME","YSS","BY_JE","LJ_JE"],
      "amount_col": "BY_JE",
      "default_filters": ["XM_NAME LIKE '%合%计%'"],
      "sql_template": "SELECT {columns} FROM {table} WHERE {filters}",
      "variants": {
        "排名": {"group_by":"RG_NAME","aggregate":"SUM({amount_col})","order":"DESC","limit":20},
        "趋势": {"group_by":"YEAR_MONTH","aggregate":"SUM({amount_col})","order":"ASC"}
      }
    },
    {
      "id": "gyzbjy_expenditure", "name": "国有资本经营支出", "intent": "完成情况",
      "table": "RDYS_LD_YSZX_GYZBJYYYZCWC",
      "columns": ["RG_NAME","YEAR_MONTH","XM_NAME","YSS","BY_JE","LJ_JE"],
      "amount_col": "BY_JE",
      "default_filters": ["XM_NAME LIKE '%合%计%'"],
      "sql_template": "SELECT {columns} FROM {table} WHERE {filters}"
    }
  ]
}
```

#### `gov_fund.json`
```json
{
  "metrics": [
    {
      "id": "zfxjj_income", "name": "政府性基金收入", "intent": "完成情况",
      "table": "RDYS_LD_YSZX_ZFXJJ_QSSRWCQK",
      "columns": ["RG_NAME","YEAR_MONTH","XM_NAME","YSW","BYS_JE","BYLJS_JE"],
      "amount_col": "BYS_JE",
      "default_filters": ["XM_NAME LIKE '%合%计%'"],
      "sql_template": "SELECT {columns} FROM {table} WHERE {filters}",
      "variants": {
        "排名": {"group_by":"RG_NAME","aggregate":"SUM({amount_col})","order":"DESC","limit":20},
        "趋势": {"group_by":"YEAR_MONTH","aggregate":"SUM({amount_col})","order":"ASC"}
      }
    }
  ]
}
```

**验收**: 4个指标文件 + `load_business_metric("社会保险","排名")` matched>0

---

### 任务2: ServerHandler 移到 handler.py

**问题**: `class ServerHandler` 定义在 server.py (第175行)，本质是 handler 的扩展，应该和 TextToSQLHandler 放一起。

**操作**:
1. 从 server.py 复制 `class ServerHandler` (约20行) → handler.py 末尾
2. server.py 导入: `from handler import TextToSQLHandler, StepOutcome, ServerHandler`
3. server.py 删除 `class ServerHandler` 定义

**验收**: `grep "class ServerHandler" server.py` 无结果，`grep "class ServerHandler" handler.py` 有结果

---

### 任务3: server.py 移除无用 import

清理 server.py 顶部的冗余 import:
- `import uuid` 如果在 chat_service 中没用 → 移到需要的地方
- `from datetime import datetime` → 检查是否还在用
- 合并重复的 import 行

**验收**: server.py import 块从当前的 10 个 import 减少

---

## 四、改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `memory/business_metrics/social_insurance.json` | **新建** | 社保基金指标 |
| `memory/business_metrics/state_capital.json` | **新建** | 国有资本指标 |
| `memory/business_metrics/gov_fund.json` | **新建** | 政府性基金指标 |
| `handler.py` | **修改** | +ServerHandler 类 (尾部) |
| `server.py` | **修改** | -ServerHandler + import from handler |

**总计**: 3个新JSON + 2个文件修改

---

## 五、验收清单

| # | 检查项 | 验证方式 |
|---|--------|---------|
| 1 | 4个预算类型都有指标JSON | `ls memory/business_metrics/*.json` 含 general_public/social_insurance/state_capital/gov_fund |
| 2 | 社保匹配成功 | `load_business_metric("社会保险","排名")` matched>0 |
| 3 | 国资匹配成功 | `load_business_metric("国有资本","完成情况")` matched>0 |
| 4 | ServerHandler在handler.py | `grep "class ServerHandler" handler.py` 有结果 |
| 5 | server.py不含ServerHandler | `grep "class ServerHandler" server.py` 无结果 |
| 6 | 17工具可用 | `len(TOOLS_SCHEMA)==17` |
| 7 | 服务启动正常 | `uv run python server.py` |
