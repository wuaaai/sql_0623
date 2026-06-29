# Phase 2: 业务规则收敛 + 技能路由 — 详细工程计划

## 一、解决的问题

| # | 问题 | 当前状态 | Phase 2 后 |
|---|------|---------|-----------|
| 1 | 预算类型映射重复 | db_schema.py / global_mem.txt / system_prompt.txt 三处维护 | `business_rules.json` 一处，代码引用 JSON |
| 2 | 列名模式重复 | 同上三处 | 同上 |
| 3 | system_prompt 臃肿 | 123行，混入大量可提取的规则 | <60行，只保留核心 |
| 4 | 技能文件被动 | LLM 自己决定读不读 | 按关键词匹配强制注入 system_prompt |
| 5 | 新增业务规则 | 改3个文件，容易漏 | 改1个 JSON 文件 |

---

## 二、任务清单

### 任务1: 创建 `memory/business_rules.json`

**单一事实来源**，包含两类规则：

```json
{
  "budget_types": {
    "一般公共预算": {
      "prefix": "YBGGYS",
      "aliases": ["一般预算", "公共预算", "YB"],
      "income_tables": ["RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC"],
      "expenditure_tables": ["RDYS_LD_YSSC_YSZX_QSYBGGYSZCWC"],
      "description": "一般公共预算收入/支出执行数据"
    },
    "社会保险": {
      "prefix": "SHBXJJ",
      "aliases": ["社保", "社保基金", "保险"],
      "income_tables": ["RDYS_LD_YSZX_SHBXJJYSSRWC"],
      "expenditure_tables": ["RDYS_LD_YSZX_SHBXJJYSZCWC"],
      "description": "社会保险基金收入/支出执行数据"
    },
    "国有资本": {
      "prefix": "GYZBJY",
      "aliases": ["国资", "国资预算", "国有资本经营"],
      "income_tables": ["RDYS_LD_YSZX_GYZBJYYYSRWC"],
      "expenditure_tables": ["RDYS_LD_YSZX_GYZBJYYYZCWC"],
      "description": "国有资本经营预算收入/支出执行数据"
    },
    "政府性基金": {
      "prefix": "ZFXJJ",
      "aliases": ["政府基金", "基金预算"],
      "income_tables": ["RDYS_LD_YSZX_ZFXJJ_QSSRWCQK"],
      "expenditure_tables": ["RDYS_LD_YSZX_ZFXJJ_SBJZCWCQK"],
      "description": "政府性基金预算收入/支出执行数据"
    }
  },
  "column_patterns": {
    "完成情况": {
      "keywords": ["完成", "收入", "支出", "执行"],
      "columns": ["RG_NAME", "YEAR_MONTH", "XM_NAME", "YSS", "BYS_JE", "BY_JE", "BYLJS_JE"],
      "note": "查看本月金额和累计金额"
    },
    "同比对比": {
      "keywords": ["同比", "增长", "下降", "去年", "增减"],
      "columns": ["RG_NAME", "YEAR_MONTH", "XM_NAME", "BYS_JE", "BY_JE", "BYS_SNTYS", "BY_SNTYS", "BYS_TBE", "BY_TBE", "BYS_TBB", "BY_TBBFS"],
      "note": "包含上年同期和同比增减额/率"
    },
    "排名": {
      "keywords": ["排名", "最高", "最低", "前", "TOP"],
      "columns": ["RG_NAME", "YEAR_MONTH", "XM_NAME", "BYS_JE", "BY_JE"],
      "note": "按金额列排序，ROWNUM限制行数"
    },
    "预算执行": {
      "keywords": ["预算执行", "进度", "完成率"],
      "columns": ["RG_NAME", "YSS", "BYS_JE", "BY_JE", "BYLJS_JE"],
      "note": "对比预算数和实际完成数"
    }
  },
  "region_codes": {
    "130000000": "河北省",
    "130100000": "石家庄市",
    "130200000": "唐山市",
    "130300000": "秦皇岛市",
    "130400000": "邯郸市",
    "130500000": "邢台市",
    "130600000": "保定市",
    "130700000": "张家口市",
    "130800000": "承德市",
    "130900000": "沧州市",
    "131000000": "廊坊市",
    "131100000": "衡水市"
  },
  "common_filters": {
    "合计": "XM_NAME LIKE '%合%计%'",
    "税收": "XM_NAME LIKE '%税收%'",
    "非税": "XM_NAME LIKE '%非税%'",
    "省本级": "RG_NAME LIKE '%本级%'",
    "各地市": "RG_NAME NOT LIKE '%本级%'"
  }
}
```

**改动文件**: 
- `tools/db_schema.py`: `BUDGET_TYPE_MAP` → `_load_rules()["budget_types"]`
- `prompts/system_prompt.txt`: 删除硬编码的预算类型表 → 改为引用 `business_rules.json`
- `memory/global_mem.txt`: 删除重复的预算类型和列名表

**验收**: `grep -r "YBGGYS\|SHBXJJ\|GYZBJY\|ZFXJJ" tools/db_schema.py prompts/system_prompt.txt memory/global_mem.txt` 只在 business_rules.json 中有映射定义

---

### 任务2: system_prompt 从 123 行瘦身到 <60 行

**删除内容**（已存在于 skills/ 或 business_rules.json）:
- 智能列选择表（~10行）→ business_rules.json
- 跨表查询规则（~10行）→ cross_table_analysis.md
- 深度分析规则（~8行）→ advanced_analysis.md
- 排名查询模板（~8行）→ aggregation.md + sql_generation.md
- 追问次数限制详解（~8行）→ clarification_strategy.md
- 能力参考列表（~10行）→ 保留简版

**保留内容**（LLM 每次必须看到的核心）:
- 角色定义（1行）
- 工具选择规则表（6行）
- 最重要规则（4条）
- 查询工作流（4行）
- 回答要求（4行）
- 可用工具列表

**精简后的 system_prompt.txt**:
```
你是财政预算助手。两种能力: 查数据库(Text-to-SQL) + 搜知识库(RAG)。

## 工具选择
| 用户问 | 用 |
|--------|-----|
| 收入/支出/金额/排名/累计/完成/同比 | run_sql / run_aggregation |
| 政策/解读/要求/规定/编制/管理/改革 | rag_search |
| 两者都涉及 | 先 rag_search 理解背景，再 run_sql 查数据 |

## 核心规则
1. 必须调用工具获取真实数据，禁止编造
2. 一般公共预算→YBGGYS, 社保→SHBXJJ, 国资→GYZBJY, 政府基金→ZFXJJ
3. 达梦: ROWNUM(非LIMIT), ||(非CONCAT)
4. 无时间→resolve_time("") 自动取最新

## 查询流程
resolve_time → search_schema/rag_search → describe_table → run_sql/run_aggregation
写SQL前先判断: 明细(直接SELECT) vs 统计(GROUP BY+聚合)

## 工具
resolve_time / search_schema / describe_table / suggest_columns / rag_search
run_sql / run_aggregation / list_tables / search_patterns / search_memory
```

**验收**: `wc -l prompts/system_prompt.txt` < 60

---

### 任务3: 创建 `memory/skills_index.json`

**技能路由索引**，server.py 根据用户问题自动注入相关技能：

```json
{
  "skills": [
    {
      "file": "aggregation.md",
      "triggers": ["排名", "各市", "各月", "平均", "汇总", "趋势", "GROUP BY"],
      "priority": 1
    },
    {
      "file": "yoy_analysis.md",
      "triggers": ["同比", "增长", "下降", "去年", "同期", "增减"],
      "priority": 1
    },
    {
      "file": "advanced_analysis.md",
      "triggers": ["占比", "子查询", "异常", "超过平均", "环比"],
      "priority": 1
    },
    {
      "file": "cross_table_analysis.md",
      "triggers": ["对比", "合并", "UNION", "关联", "跨表"],
      "priority": 2
    },
    {
      "file": "sql_generation.md",
      "triggers": ["SQL", "达梦", "ROWNUM", "JOIN", "WHERE"],
      "priority": 2
    },
    {
      "file": "schema_exploration.md",
      "triggers": ["有哪些表", "表结构", "搜索表", "查找表"],
      "priority": 2
    },
    {
      "file": "budget_progress.md",
      "triggers": ["进度", "完成率", "执行率", "预算执行"],
      "priority": 2
    },
    {
      "file": "error_recovery.md",
      "triggers": [],
      "priority": 3,
      "note": "不按关键词触发，由 error_handler 内部引用"
    }
  ]
}
```

**server.py 注入逻辑**:
```python
def _inject_skills(system_prompt: str, question: str) -> str:
    """根据用户问题关键词匹配技能文件，注入到 system_prompt"""
    with open("memory/skills_index.json") as f:
        index = json.load(f)
    
    matched = []
    for skill in index["skills"]:
        if skill["priority"] > 2:  # 仅注入 priority 1-2
            continue
        for trigger in skill["triggers"]:
            if trigger in question:
                matched.append(skill)
                break
    
    if matched:
        system_prompt += "\n\n## 相关技能\n"
        for s in sorted(matched, key=lambda x: x["priority"]):
            skill_path = f"memory/skills/{s['file']}"
            if os.path.exists(skill_path):
                with open(skill_path, encoding="utf-8") as f:
                    # 只注入前600字符（技能文件的关键部分）
                    content = f.read()[:600]
                    system_prompt += f"\n### {s['file']}\n{content}\n"
    
    return system_prompt
```

**效果对比**:
| 用户问题 | 注入的技能 |
|---------|-----------|
| "各市一般公共预算收入排名" | aggregation.md + yoy_analysis.md |
| "2026年预算编制新政策" | 无（RAG类问题，不注入SQL技能） |
| "收入超过全省平均的地市" | advanced_analysis.md |
| "一般公共预算和社保对比" | cross_table_analysis.md |

**验收**: 同一个问题生成的 system_prompt 包含匹配的技能内容

---

### 任务4: 清理 `memory/global_mem.txt`

删除与 `business_rules.json` 重复的内容：
- 删除"四大预算类型→表名前缀映射"表
- 删除"预算表通用字段"表（列名模式已在 business_rules.json）
- 保留：达梦语法要点、地区编码、窗口函数语法、市县数据查 XM_NAME 注意事项

---

## 三、改动文件清单

| 文件 | 操作 | 预计行数 |
|------|------|---------|
| `memory/business_rules.json` | **新建** | ~80行 |
| `memory/skills_index.json` | **新建** | ~50行 |
| `prompts/system_prompt.txt` | **重写** | 123→<60行 |
| `memory/global_mem.txt` | **删减** | 删除~20行重复内容 |
| `tools/db_schema.py` | **修改** | BUDGET_TYPE_MAP→读JSON |
| `server.py` | **修改** | +_inject_skills 函数 ~30行 |

**总计**: 2个新文件 + 4个文件修改

---

## 四、验收清单

| # | 检查项 | 验证方式 |
|---|--------|---------|
| 1 | 预算类型映射唯一 | `grep "YBGGYS" tools/db_schema.py prompts/ memory/global_mem.txt` 结果全是引用 business_rules.json |
| 2 | system_prompt <60行 | `wc -l prompts/system_prompt.txt` |
| 3 | 技能按需注入 | 问"收入排名" → 日志显示 injection: aggregation.md |
| 4 | 配置中心仍在用 | config 导入无报错 |
| 5 | 16个工具全部可用 | `from tools.schema import TOOLS_SCHEMA; len(TOOLS_SCHEMA) == 16` |
| 6 | 服务正常启动 | `uv run python server.py` |
| 7 | 查询功能正常 | 前端发送查询返回结果 |
