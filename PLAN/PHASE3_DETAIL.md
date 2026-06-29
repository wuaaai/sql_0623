# Phase 3: 业务指标体系 + 路由强制执行 — 详细工程计划

## 一、现状分析（Phase 2 完成后）

| 能力 | 状态 | 缺口 |
|------|------|------|
| 业务规则 JSON | `business_rules.json` 含预算类型+列名模式 | 缺少指标模板（SQL模板+变体） |
| 技能路由 | `skills_index.json` + `_inject_skills` | 注入的是技能文档，不是可执行的指标模板 |
| 工具列表 | 16个工具 | 缺少 `load_business_metric` 工具 |
| system_prompt | 48行 | 无强制路由指令 |

**核心问题**: 技能路由目前是"参考文档"级别——LLM 看到 `aggregation.md` 的内容，但仍需自己决定用哪张表、选哪些列。需要升级为"指令"级别——直接告诉 LLM 用哪张表、哪几列、SQL怎么写。

## 二、目标

```
用户问 "一般公共预算收入排名"
  │
  ├─ skills_index.json 匹配: aggregation.md + yoy_analysis.md
  ├─ business_rules.json 匹配: budget_type=一般公共预算, intent=排名
  ├─ business_metrics/income.json 返回: {table, columns, template, filters}
  │
  └─ system_prompt 注入:
      "[强制执行] 匹配到指标: 一般公共预算收入排名
       表: RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC
       列: RG_NAME, BYS_JE
       SQL模板: SELECT RG_NAME, SUM({amount_col}) FROM {table} WHERE {filters} GROUP BY RG_NAME ORDER BY SUM({amount_col}) DESC
       你只需替换地区和时间参数，禁止调用 search_schema 和 describe_table"
```

## 三、任务清单

### 任务1: 创建业务指标模板文件

建立 `memory/business_metrics/` 目录，每个预算类型一个 JSON 文件:

```
memory/business_metrics/
├── index.json              # 总索引: metric_id → 文件路径
├── general_public.json     # 一般公共预算
├── social_insurance.json   # 社保基金
├── state_capital.json      # 国有资本
├── gov_fund.json           # 政府性基金
└── templates.json          # 通用SQL模板
```

#### 1.1 指标文件格式 (`general_public.json`)

```json
{
  "metrics": [
    {
      "id": "ybggys_income_completion",
      "name": "一般公共预算收入完成情况",
      "intent": "完成情况",
      "table": "RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC",
      "columns": ["RG_NAME","YEAR_MONTH","XM_NAME","YSS","BYS_JE","BYLJS_JE"],
      "amount_col": "BYS_JE",
      "default_filters": ["XM_NAME LIKE '%合%计%'"],
      "sql_template": "SELECT {columns} FROM {table} WHERE {filters}",
      "variants": {
        "ranking": {
          "group_by": "RG_NAME",
          "aggregate": "SUM({amount_col})",
          "order": "DESC",
          "limit": 20
        },
        "trend": {
          "group_by": "YEAR_MONTH",
          "aggregate": "SUM({amount_col})",
          "order": "ASC"
        },
        "yoy": {
          "columns_add": ["BYS_SNTYS","BYS_TBE","BYS_TBB"]
        },
        "cumulative": {
          "columns_use": ["BYLJS_JE"],
          "amount_col": "BYLJS_JE"
        }
      }
    },
    {
      "id": "ybggys_income_yoy",
      "name": "一般公共预算收入同比",
      "intent": "同比对比",
      "table": "RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC",
      "columns": ["RG_NAME","YEAR_MONTH","XM_NAME","BYS_JE","BYS_SNTYS","BYS_TBE","BYS_TBB"],
      "amount_col": "BYS_TBB",
      "default_filters": ["XM_NAME LIKE '%合%计%'"],
      "sql_template": "SELECT {columns} FROM {table} WHERE {filters} ORDER BY BYS_TBB DESC"
    }
  ]
}
```

#### 1.2 通用SQL模板 (`templates.json`)

```json
{
  "templates": {
    "ranking": "SELECT * FROM (SELECT {columns}, {aggregate} as total FROM {table} WHERE {filters} GROUP BY {group_by} ORDER BY total {order}) WHERE ROWNUM <= {limit}",
    "trend": "SELECT {group_by}, {aggregate} as total FROM {table} WHERE {filters} GROUP BY {group_by} ORDER BY {group_by} {order}",
    "detail": "SELECT {columns} FROM {table} WHERE {filters} AND ROWNUM <= {limit}",
    "summary": "SELECT {aggregate} as total FROM {table} WHERE {filters}"
  }
}
```

#### 1.3 索引文件 (`index.json`)

```json
{
  "budget_type_mapping": {
    "一般公共预算": "general_public.json",
    "社会保险": "social_insurance.json",
    "国有资本": "state_capital.json",
    "政府性基金": "gov_fund.json"
  },
  "intent_mapping": {
    "完成情况": ["general_public.json", "social_insurance.json", "state_capital.json", "gov_fund.json"],
    "同比对比": ["general_public.json", "social_insurance.json", "state_capital.json", "gov_fund.json"],
    "排名": ["general_public.json", "social_insurance.json", "state_capital.json", "gov_fund.json"],
    "预算执行": ["general_public.json", "social_insurance.json", "state_capital.json", "gov_fund.json"]
  }
}
```

---

### 任务2: 新增原子工具 `load_business_metric`

#### 2.1 创建 `tools/business_loader.py`

```python
"""
业务指标加载器 — 根据用户问题匹配业务指标，返回表名/列名/SQL模板
"""

import json, os, re

_METRICS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "business_metrics")


def _load_json(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_business_metric(budget_type: str = "", intent: str = "") -> dict:
    """
    根据预算类型和查询意图，返回匹配的业务指标。
    
    Args:
        budget_type: 预算类型（"一般公共预算"/"社会保险"/"国有资本"/"政府性基金"）
        intent: 查询意图（"完成情况"/"同比对比"/"排名"/"预算执行"）
    
    Returns:
        {"status": "ok", "metrics": [...], "templates": {...}}
    """
    index = _load_json(os.path.join(_METRICS_DIR, "index.json"))
    templates = _load_json(os.path.join(_METRICS_DIR, "templates.json"))
    
    # 确定要加载哪些指标文件
    files_to_load = []
    if budget_type:
        f = index.get("budget_type_mapping", {}).get(budget_type)
        if f: files_to_load.append(f)
    if intent:
        files = index.get("intent_mapping", {}).get(intent, [])
        files_to_load.extend(files)
    files_to_load = list(set(files_to_load))  # 去重
    
    # 加载指标
    matched_metrics = []
    for fname in files_to_load:
        data = _load_json(os.path.join(_METRICS_DIR, fname))
        for m in data.get("metrics", []):
            if (not budget_type or m.get("table", "").startswith(
                _resolve_prefix(budget_type)
            )) and (not intent or m.get("intent") == intent):
                matched_metrics.append(m)
    
    return {
        "status": "ok",
        "budget_type": budget_type,
        "intent": intent,
        "matched": len(matched_metrics),
        "metrics": matched_metrics[:3],
        "templates": templates.get("templates", {})
    }


def _resolve_prefix(budget_type: str) -> str:
    mapping = {"一般公共预算": "YBGGYS", "社会保险": "SHBXJJ", "国有资本": "GYZBJY", "政府性基金": "ZFXJJ"}
    return mapping.get(budget_type, "")
```

#### 2.2 注册工具

在 `tools/schema.py` 中注册为第17个工具：

```json
{
  "name": "load_business_metric",
  "description": "加载业务指标模板。返回匹配的表名、列名、SQL模板。当用户问题匹配已知业务场景时优先使用此工具，避免重复探索表结构。",
  "parameters": {
    "budget_type": {"type": "string", "description": "预算类型"},
    "intent": {"type": "string", "description": "查询意图: 完成情况/同比对比/排名/预算执行"}
  }
}
```

#### 2.3 添加 Handler

在 `handler.py` 中添加 `do_load_business_metric` 方法。

---

### 任务3: 路由强制执行 — 从"参考"升级为"指令"

#### 3.1 修改 `_inject_skills` 为 `_inject_guidance`

当前 `_inject_skills` 注入技能文件内容供 LLM 参考。升级为：
1. 先匹配 business_metrics（精确匹配 → 强制执行）
2. 再匹配 skills（模糊匹配 → 参考提示）

```python
def _inject_guidance(system_prompt: str, question: str) -> str:
    """注入业务指引（指标模板优先，技能文件参考）"""
    
    # Step 1: 尝试匹配业务指标
    budget = _detect_budget_type(question)
    intent = _detect_intent(question)
    
    if budget and intent:
        metric = load_business_metric(budget, intent)
        if metric["matched"] > 0:
            m = metric["metrics"][0]
            system_prompt += (
                f"\n\n[强制执行-业务指标匹配]\n"
                f"指标: {m['name']}\n"
                f"表名: {m['table']}\n"
                f"列名: {', '.join(m['columns'][:8])}\n"
                f"SQL模板: {m['sql_template']}\n"
                f"筛选条件: {', '.join(m.get('default_filters',[]))}\n"
                f"【禁止调用 search_schema 和 describe_table。直接用上表名和列名写SQL。】\n"
            )
            return system_prompt
    
    # Step 2: 无指标匹配时，注入技能文件参考
    return _inject_skills(system_prompt, question)


def _detect_budget_type(question: str) -> str:
    with open("memory/business_rules.json", encoding="utf-8") as f:
        rules = json.load(f)
    for name, info in rules["budget_types"].items():
        if name in question:
            return name
        for alias in info.get("aliases", []):
            if alias in question:
                return name
    return ""


def _detect_intent(question: str) -> str:
    with open("memory/business_rules.json", encoding="utf-8") as f:
        rules = json.load(f)
    for name, info in rules.get("column_patterns", {}).items():
        for kw in info.get("keywords", []):
            if kw in question:
                return name
    return ""
```

#### 3.2 注入效果对比

| 用户问题 | Phase 2（现状） | Phase 3（升级后） |
|---------|---------------|-----------------|
| "各市一般公共预算收入排名" | 注入 aggregation.md 技能文档（LLM自己理解） | **[强制执行] 表:RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC, 列:RG_NAME,BYS_JE, SQL模板:SELECT ... GROUP BY ... ORDER BY** |
| "社保基金同比增长" | 注入 yoy_analysis.md | **[强制执行] 表:RDYS_LD_YSZX_SHBXJJYSSRWC, 列:...BYS_TBB** |
| "2026年预算编制新政策" | 无匹配（正确走RAG） | 无匹配（正确走RAG） |

---

### 任务4: 更新 promp t指导 LLM 使用新工具

在 system_prompt.txt 中增加一条规则：

```
## 业务指标优先
遇到收入/支出/排名/同比问题时，先用 load_business_metric 获取表名+列名+SQL模板，
再用 run_sql 填参数执行。不要从 search_schema 开始探索。
```

---

## 四、改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `memory/business_metrics/index.json` | **新建** | 指标索引 |
| `memory/business_metrics/templates.json` | **新建** | 通用SQL模板 |
| `memory/business_metrics/general_public.json` | **新建** | 一般公共预算指标 |
| `tools/business_loader.py` | **新建** | load_business_metric 工具 |
| `tools/schema.py` | **修改** | 注册第17个工具 |
| `handler.py` | **修改** | do_load_business_metric |
| `server.py` | **修改** | _inject_skills → _inject_guidance |
| `prompts/system_prompt.txt` | **修改** | 增加业务指标优先规则 |

---

## 五、验收清单

| # | 检查项 | 验证方式 |
|---|--------|---------|
| 1 | 4个业务指标JSON存在 | `ls memory/business_metrics/` |
| 2 | load_business_metric 返回正确结果 | `load_business_metric("一般公共预算收入","排名")` 返回 matched>=1 |
| 3 | _inject_guidance 强制执行 | "各市一般公共预算收入排名" → system_prompt含"[强制执行-业务指标匹配]" |
| 4 | 17个工具全部可导入 | `len(TOOLS_SCHEMA)==17` |
| 5 | 无业务匹配时正常降级 | "2026年政策" → 不注入强制指令 |
| 6 | 服务正常启动 | `uv run python server.py` |
