# 业务规则汇总文档

## 一、预算类型 → 表名映射

**文件**: `memory/business_rules.json` → `budget_types`

| 用户口语 | 英文前缀 | 收入表 | 支出表 | 别名 |
|---------|---------|--------|--------|------|
| 一般公共预算 | YBGGYS | RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC | RDYS_LD_YSSC_YSZX_QSYBGGYSZCWC | 一般预算/公共预算/YB |
| 社会保险 | SHBXJJ | RDYS_LD_YSZX_SHBXJJYSSRWC | RDYS_LD_YSZX_SHBXJJYSZCWC | 社保/社保基金/保险 |
| 国有资本 | GYZBJY | RDYS_LD_YSZX_GYZBJYYYSRWC | RDYS_LD_YSZX_GYZBJYYYZCWC | 国资/国资预算/国有资本经营 |
| 政府性基金 | ZFXJJ | RDYS_LD_YSZX_ZFXJJ_QSSRWCQK | RDYS_LD_YSZX_ZFXJJ_SBJZCWCQK | 政府基金/基金预算 |

---

## 二、查询意图 → 列名模式

**文件**: `memory/business_rules.json` → `column_patterns`

| 意图 | 触发关键词 | 应选列 |
|------|-----------|--------|
| 完成情况 | 完成/收入/支出/执行 | RG_NAME, YEAR_MONTH, XM_NAME, YSS, BYS_JE/BY_JE, BYLJS_JE |
| 同比对比 | 同比/增长/下降/去年/增减 | BYS_SNTYS/BY_SNTYS, BYS_TBE/BY_TBE, BYS_TBB/BY_TBBFS |
| 排名 | 排名/最高/最低/前/TOP | RG_NAME, YEAR_MONTH, XM_NAME, BYS_JE/BY_JE |
| 预算执行 | 预算执行/进度/完成率 | RG_NAME, YSS, BYS_JE/BY_JE, BYLJS_JE |

---

## 三、常用筛选条件

**文件**: `memory/business_rules.json` → `common_filters`

| 用户说 | SQL WHERE |
|--------|-----------|
| 合计 | `XM_NAME LIKE '%合%计%'` |
| 税收收入 | `XM_NAME LIKE '%税收%'` |
| 非税收入 | `XM_NAME LIKE '%非税%'` |
| 省本级 | `RG_NAME LIKE '%本级%'` |
| 各地市（排除本级） | `RG_NAME NOT LIKE '%本级%'` |

---

## 四、地区编码

**文件**: `memory/business_rules.json` → `region_codes`

```
130000000 河北省
├── 130100000 石家庄市
├── 130200000 唐山市
├── 130300000 秦皇岛市
├── 130400000 邯郸市
├── 130500000 邢台市
├── 130600000 保定市
├── 130700000 张家口市
├── 130800000 承德市
├── 130900000 沧州市
├── 131000000 廊坊市
└── 131100000 衡水市
```

**权限继承**: 设置130000000(河北省) → `WHERE RG_CODE LIKE '13%'`（覆盖全省）

---

## 五、业务指标模板

**文件**: `memory/business_metrics/`

### 指标索引 (`index.json`)

```
用户问题
  → _detect_budget_type → 一般公共预算 → general_public.json
  → _detect_intent → 排名 → 匹配 general_public.json 中 intent="完成情况" 且 variants 含"排名"
  → 返回: table + columns + sql_template + variant(排名)
```

### 4个预算类型的指标模板

| 文件 | 覆盖 |
|------|------|
| `general_public.json` | 一般公共预算: 收入/支出/同比 (3个指标) |
| `social_insurance.json` | 社保基金: 收入/支出 (2个指标) |
| `state_capital.json` | 国有资本: 收入/支出 (2个指标) |
| `gov_fund.json` | 政府性基金: 收入 (1个指标) |

每个指标支持的变体:
- **排名**: GROUP BY RG_NAME + SUM + ORDER BY DESC
- **趋势**: GROUP BY YEAR_MONTH + ORDER BY ASC
- **同比**: +BYS_SNTYS, BYS_TBB 列
- **累计**: 用 BYLJS_JE 列

### 通用SQL模板 (`templates.json`)

```sql
排名: SELECT * FROM (SELECT columns, aggregate as total FROM table WHERE filters GROUP BY group_by ORDER BY total order) WHERE ROWNUM <= limit
趋势: SELECT group_by, aggregate as total FROM table WHERE filters GROUP BY group_by ORDER BY group_by order
明细: SELECT columns FROM table WHERE filters AND ROWNUM <= limit
汇总: SELECT aggregate as total FROM table WHERE filters
```

---

## 六、技能路由

**文件**: `memory/skills_index.json`

### 第1层注入（priority=1，每次匹配都注入）

| 技能文件 | 触发词 |
|---------|--------|
| `aggregation.md` | 排名/各市/各月/平均/汇总/趋势/GROUP BY |
| `yoy_analysis.md` | 同比/增长/下降/去年/同期/增减 |
| `advanced_analysis.md` | 占比/子查询/异常/超过平均/环比 |

### 第2层注入（priority=2，匹配时注入）

| 技能文件 | 触发词 |
|---------|--------|
| `cross_table_analysis.md` | 对比/合并/UNION/关联/跨表 |
| `sql_generation.md` | SQL/达梦/ROWNUM/JOIN/WHERE |
| `schema_exploration.md` | 有哪些表/表结构/搜索表/查找表 |
| `budget_progress.md` | 进度/完成率/执行率/预算执行 |

### 第3层（priority=3，代码内部引用，不自动注入）

| 技能文件 | 说明 |
|---------|------|
| `query_efficiency.md` | 高效查询策略 |
| `interaction_patterns.md` | 交互对话模式 |
| `error_recovery.md` | 错误恢复（error_handler引用） |
| `clarification_strategy.md` | 追问策略 |
| `pattern_reuse.md` | 查询模式复用 |
| `session_memory.md` | 会话记忆 |

---

## 七、执行流程

```
server.py
  │
  ├─ _detect_budget_type(question)
  │   └─ business_rules.json → budget_types → 遍历匹配
  │
  ├─ _detect_intent(question)  
  │   └─ business_rules.json → column_patterns → 遍历关键词
  │
  └─ 有结果? → load_business_metric(budget, intent)
  │   └─ business_metrics/index.json → 定位指标文件 → 加载模板
  │   └─ system_prompt 注入 [强制执行-业务指标匹配]
  │
  └─ 无结果? → _inject_skills(question)
      └─ skills_index.json → 遍历触发词 → 注入匹配的技能文件内容
```

---

## 八、如何扩充

### 加一种新的预算类型

只需加1个JSON文件:

```bash
# 1. business_rules.json 的 budget_types 加一条
"新预算类型": {"prefix": "XXX", "aliases": ["别名"]}

# 2. business_metrics/ 下新建 new_budget.json

# 3. business_metrics/index.json 加映射
"budget_type_mapping": {"新预算类型": "new_budget.json"}
```

### 加一种新的查询意图

只需改1个JSON文件:

```json
// business_rules.json → column_patterns 加一条
"新意图": {"keywords": ["关键词1","关键词2"], "columns": ["列名1","列名2"]}
```

### 加一个新的业务指标

只需改对应的指标JSON:

```json
// business_metrics/general_public.json → metrics 数组加一条
{"id": "new_metric", "name": "新指标名", "intent": "完成情况",
 "table": "表名", "columns": ["..."], "sql_template": "..."}
```

### 加一个新的技能文件

只需改2个文件:

```bash
# 1. memory/skills/ 下新建 .md 文件
# 2. memory/skills_index.json 加一条
{"file": "new_skill.md", "triggers": ["关键词"], "priority": 1}
```

**不需要改任何 Python 代码。**
