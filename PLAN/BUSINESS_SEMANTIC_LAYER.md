# 业务语义层设计 — 参考 Anthropic 方法论

## 核心理念

> Anthropic: "Agents are structurally required to use the semantic layer first."
> 不靠向量匹配，靠**结构化指标定义 + 技能路由 + 模板填空**。

## 一、三层架构

```
用户问题 "一般公共预算收入同比增长了多少"
  │
  ├─ L1: 技能路由层 (skills/)
  │     └─ 判断问题类型 → 收入/支出/同比/排名/趋势/预算执行
  │     └─ 路由到正确的业务指标文件
  │
  ├─ L2: 业务指标层 (business_metrics/)
  │     └─ metrics/income/general_public_budget.json
  │        { "收入完成情况": {
  │            "table": "RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC",
  │            "columns": ["RG_NAME","YEAR_MONTH","XM_NAME","BYS_JE","BYS_TBB"],
  │            "filters": {"XM_NAME": "合计"},
  │            "sql_template": "SELECT {columns} FROM {table} WHERE {filters}"
  │          }}
  │
  └─ L3: 数据执行层 (现有工具)
        └─ run_sql 用模板参数执行
```

## 二、业务指标目录结构

```
business_metrics/
├── index.json                    # 总路由表: 业务术语→指标文件
├── income/                       # 收入类指标
│   ├── general_public.json       # 一般公共预算收入
│   ├── social_insurance.json     # 社保基金收入
│   ├── state_capital.json        # 国有资本经营收入
│   └── gov_fund.json             # 政府性基金收入
├── expenditure/                  # 支出类指标
│   ├── general_public.json
│   ├── social_insurance.json
│   ├── state_capital.json
│   └── gov_fund.json
├── comparison/                   # 对比类指标
│   ├── yoy.json                  # 同比对比
│   └── budget_vs_actual.json     # 预算vs实际
├── ranking/                      # 排名类
│   └── city_ranking.json
├── trend/                        # 趋势类
│   └── monthly_trend.json
└── progress/                     # 进度类
    └── budget_progress.json
```

## 三、业务指标格式

每个指标文件是结构化的 JSON，LLM 直接当模板填空：

```json
{
  "metric_id": "ybggys_income_completion",
  "business_name": "一般公共预算收入完成情况",
  "aliases": ["一般公共预算收入", "公共预算收入", "YBGGYS收入"],
  "table": "RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC",
  "columns": {
    "required": ["RG_NAME", "YEAR_MONTH", "BYS_JE"],
    "optional": ["XM_NAME", "BYS_SNTYS", "BYS_TBB", "BYS_TBE", "YSS", "BYLJS_JE"]
  },
  "default_filters": {
    "XM_NAME": {"op": "LIKE", "value": "%合计%"}
  },
  "variants": {
    "同比": {
      "columns_add": ["BYS_SNTYS", "BYS_TBB", "BYS_TBE"]
    },
    "排名": {
      "order_by": "BYS_JE DESC",
      "group_by": "RG_NAME"
    },
    "累计": {
      "columns_use": ["BYLJS_JE"]
    }
  },
  "sql_template": "SELECT {columns} FROM {table} WHERE {filters}",
  "supported_dimensions": ["地区", "时间", "科目"],
  "examples": [
    {"question": "河北省一般公共预算收入", "sql": "SELECT RG_NAME,YEAR_MONTH,BYS_JE FROM RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC WHERE RG_NAME='河北省' AND XM_NAME LIKE '%合计%'"},
    {"question": "各市一般公共预算收入排名", "sql": "SELECT RG_NAME,SUM(BYS_JE) FROM ... GROUP BY RG_NAME ORDER BY SUM(BYS_JE) DESC"}
  ]
}
```

## 四、技能路由文件

`memory/skills/business_router.md`：

```markdown
# 业务路由技能

## 路由规则（按顺序匹配）

### 1. 识别预算类型
- "一般公共预算/一般预算" → business_metrics/income/general_public.json
- "社保/社保基金" → business_metrics/income/social_insurance.json
- "国有资本/国资" → business_metrics/income/state_capital.json
- "政府性基金" → business_metrics/income/gov_fund.json

### 2. 识别查询意图
- "收入/完成/执行" → income 指标
- "支出" → expenditure 指标
- "比去年/同比/增长/下降" → comparison/yoy 变体
- "排名/最高/最低/前N" → ranking 变体
- "趋势/各月/变化" → trend 变体
- "进度/完成率" → progress 变体

### 3. 模板填空
加载指标JSON后，LLM只需：
1. 选 columns（根据意图变体）
2. 填 filters（地区、时间）
3. 套 sql_template
不需要自己探索表和列。
```

## 五、与现有系统的关系

| 现有 | 增强后 |
|------|--------|
| search_schema 模糊搜索表名 | 业务路由直接定位表 → 跳过搜索 |
| LLM 自己猜列名 | 指标JSON明确列出 required + optional 列 |
| SQL 从零手写 | sql_template 填空 |
| 探索 3-5 轮 | 直接执行 1-2 轮 |

## 六、新增原子工具

| 工具 | 功能 |
|------|------|
| `load_business_metric` | 根据预算类型+查询意图加载指标JSON，返回表名/列名/SQL模板 |
| `list_metrics` | 列出所有可用的业务指标（供Agent了解能力边界） |

## 七、实施计划

### Phase 1: 核心收入指标（4个JSON文件）
- 一般公共预算收入 / 社保基金收入 / 国有资本收入 / 政府性基金收入

### Phase 2: 变体扩展
- 同比/排名/累计/趋势 变体

### Phase 3: 支出指标
- 四个预算类型的支出指标

### Phase 4: 技能路由
- business_router.md 替代当前零散的引导文本
