# 项目架构重构 + 业务语义层 — 开发计划

## 一、现状诊断

### 1.1 架构痛点

| 问题 | 具体表现 | 影响 |
|------|---------|------|
| **单体文件膨胀** | server.py 600行, handler.py 470行, system_prompt.txt 100行 | 改一处影响全局，难以定位 |
| **业务逻辑散落** | 预算类型映射在3个地方(global_mem/schema/prompt)，列名模式在2个地方 | 修改业务规则需要同步多处 |
| **配置硬编码** | os.environ.get 散落各处，默认值不一致 | 环境切换容易出错 |
| **技能文件被动** | 15个Markdown文件，LLM可能读也可能不读 | 无强制执行机制 |
| **无日志追踪** | 查询链路不可追溯，出问题不知道哪一步错了 | 生产环境排查困难 |
| **无测试框架** | test文件只是问题列表，没有自动化验证 | 改动后无法快速回归 |

### 1.2 可维护性评分

| 维度 | 当前评分 | 目标评分 |
|------|---------|---------|
| 模块化 | ★★☆☆☆ | ★★★★☆ |
| 可追溯性 | ★★☆☆☆ | ★★★★☆ |
| 可配置性 | ★★☆☆☆ | ★★★★★ |
| 可测试性 | ★☆☆☆☆ | ★★★★☆ |
| 业务语义清晰度 | ★★☆☆☆ | ★★★★★ |

---

## 二、目标架构

```
src/
├── core/                    # 核心引擎（稳定层，极少变动）
│   ├── agent_loop.py        # Agent执行循环
│   ├── llm_client.py        # LLM客户端封装
│   └── config.py            # 统一配置中心（从.env读取，唯一入口）
│
├── tools/                   # 原子工具（稳定层）
│   ├── registry.py          # 工具注册表（从schema.py重构）
│   ├── database/            # 数据库类工具
│   │   ├── connect.py
│   │   ├── schema.py
│   │   ├── query.py
│   │   └── aggregation.py
│   ├── rag/                 # RAG类工具
│   │   ├── search.py
│   │   └── ingest.py
│   └── analysis/            # 分析类工具
│       ├── subquery.py
│       ├── ratio.py
│       └── anomaly.py
│
├── business/                # 业务语义层（变动层，按需修改）
│   ├── metrics/             # 业务指标体系
│   │   ├── index.json       # 总索引
│   │   ├── income/          # 收入指标
│   │   ├── expenditure/     # 支出指标
│   │   └── comparison/      # 对比指标
│   ├── rules/               # 业务规则
│   │   ├── budget_type.py   # 预算类型映射（唯一来源）
│   │   ├── column_patterns.py # 列名模式（唯一来源）
│   │   └── region_codes.py  # 地区编码（唯一来源）
│   └── templates/           # SQL模板
│       ├── query_templates.json
│       └── formula_templates.json
│
├── skills/                  # 技能路由层（强制执行）
│   ├── router.py            # 技能路由器（根据问题加载对应技能）
│   └── skills/              # 技能定义（结构化JSON，非Markdown）
│       ├── income_query.json
│       ├── yoy_comparison.json
│       └── ...
│
├── services/                # 服务层
│   ├── chat_service.py      # 聊天服务（从server.py抽离）
│   ├── admin_service.py     # 管理服务（从server.py抽离）
│   └── session_service.py   # 会话服务
│
├── middleware/              # 中间件
│   ├── tracing.py           # 链路追踪日志
│   ├── permission.py        # 权限检查
│   └── error_handler.py     # 错误处理
│
└── server.py                # 入口（极简，只做路由注册）
```

### 2.2 分阶段实施

---

## Phase 1: 基建重构 — 可维护性打底

**目标**: 建立统一配置中心 + 日志追踪 + server拆分

### 1.1 统一配置中心 `src/core/config.py`

```python
# 全局唯一配置入口，所有模块从这里读配置
class Config:
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str
    OPENAI_MODEL: str
    DB_TYPE: str
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_SCHEMA: str
    RAG_EMBEDDING_URL: str
    RAG_RERANK_URL: str
    RAG_DB_CONNECTION: str
    RAG_COLLECTION: str
    
    @classmethod
    def load(cls):  # 从.env一次性加载，全局单例
```

**验收**: 项目中不再出现 `os.environ.get("XXX", "default")` 硬编码

### 1.2 链路追踪日志 `src/middleware/tracing.py`

```python
# 每次查询自动记录:
# [TRACE] 2026-06-24 10:30:01 | query_id=xxx | step=search_schema | table=RDYS_LD_
# [TRACE] 2026-06-24 10:30:03 | query_id=xxx | step=run_sql | sql=SELECT... | rows=15
# [TRACE] 2026-06-24 10:30:05 | query_id=xxx | step=done | turns=3 | duration=4.2s
```

**验收**: 每条查询的完整链路可追溯，出问题能定位到具体步骤

### 1.3 服务层拆分

- `server.py` → 只保留路由注册（<100行）
- 聊天逻辑 → `services/chat_service.py`
- 管理逻辑 → `services/admin_service.py`
- 会话逻辑 → `services/session_service.py`

**验收**: server.py < 100行，业务逻辑在services中

---

## Phase 2: 业务规则收敛 — 单一事实来源

**目标**: 消除散落在各处的重复业务规则

### 2.1 业务规则唯一化

| 规则 | 当前位置 | 目标位置 |
|------|---------|---------|
| 预算类型→表名前缀映射 | global_mem.txt + db_schema.py + prompt | `business/rules/budget_type.py` |
| 列名模式(完成情况/同比/排名) | prompt + db_schema.py | `business/rules/column_patterns.py` |
| 地区编码树 | region_tree.json | `business/rules/region_codes.py` |
| SQL模板(排名/趋势/汇总) | prompt + aggregation.md | `business/templates/query_templates.json` |

### 2.2 技能文件结构化

将15个Markdown技能文件改为结构化JSON：

```json
{
  "skill_id": "income_query",
  "trigger_keywords": ["收入", "完成", "执行"],
  "budget_types": ["一般公共预算", "社会保险", "国有资本", "政府性基金"],
  "required_tools": ["search_schema", "describe_table", "run_sql"],
  "table_pattern": "{budget_prefix}_SR", 
  "column_pattern": "completion",
  "sql_template": "SELECT {columns} FROM {table} WHERE RG_NAME='{region}' AND YEAR_MONTH='{time}'"
}
```

**验收**: 所有业务规则有唯一来源，修改一处全局生效

---

## Phase 3: 业务指标体系 — Anthropic风格的语义层

**目标**: 建立结构化的业务指标目录，实现模板填空式查询

### 3.1 收入指标文件

`business/metrics/income/general_public.json`:
```json
{
  "metric_id": "ybggys_income",
  "business_name": "一般公共预算收入",
  "aliases": ["一般公共预算收入", "公共预算收入"],
  "table": "RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC",
  "columns": {
    "base": ["RG_NAME","YEAR_MONTH","BYS_JE"],
    "yoy": ["BYS_SNTYS","BYS_TBB","BYS_TBE"],
    "cumulative": ["BYLJS_JE"],
    "budget": ["YSS"]
  },
  "default_filters": {"XM_NAME": "LIKE %合计%"},
  "variants": {
    "ranking": {"group_by": "RG_NAME", "order": "DESC"},
    "trend": {"group_by": "YEAR_MONTH", "order": "ASC"},
    "yoy": {"columns_use": ["base","yoy"]}
  }
}
```

### 3.2 新工具 `load_business_metric`

```
load_business_metric("一般公共预算收入", "排名")
→ 返回: {table, columns, sql_template, filters}
→ LLM只需填参数(地区/时间)，不自己探索
```

**验收**: "一般公共预算收入排名" → 工具返回完整模板 → 1轮执行

---

## Phase 4: 技能路由强制执行

**目标**: LLM必须经过业务路由，不允许跳过语义层

### 4.1 router.py

```python
def route_query(question: str) -> Skill:
    """根据问题强制匹配技能"""
    # 1. 识别预算类型
    budget = match_budget_type(question)
    # 2. 识别查询意图
    intent = match_intent(question)
    # 3. 加载对应技能
    skill = load_skill(budget, intent)
    # 4. 注入到system_prompt（强制执行标记）
    return skill
```

### 4.2 system_prompt 强制注入

```
[强制执行] 当前查询匹配到技能: income_query
- 使用表: RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC
- 使用列: RG_NAME, YEAR_MONTH, BYS_JE
- SQL模板: SELECT {columns} FROM {table} WHERE ...
- 你只需要替换{columns}和{region}参数
- 禁止调用search_schema和describe_table探索其他表
```

**验收**: 匹配到技能后，LLM跳过探索直接填空执行

---

## Phase 5: 测试框架 + CI

**目标**: 自动化回归测试

### 5.1 测试结构

```
tests/
├── unit/                # 单元测试
│   ├── test_config.py
│   ├── test_tools.py
│   └── test_router.py
├── integration/         # 集成测试
│   ├── test_chat_flow.py
│   └── test_admin_api.py
└── fixtures/           # 测试数据
    └── sample_queries.json
```

### 5.2 回归测试

```bash
uv run pytest tests/  # 每次改动后自动验证
```

**验收**: 核心路径有自动化测试覆盖，改动后能快速验证

---

## 三、实施路线图

```
Phase 1 (1天): 配置中心 + 日志追踪 + server拆分
  └─ 目标: 代码可追溯、可调试

Phase 2 (1天): 业务规则收敛
  └─ 目标: 一处修改全局生效

Phase 3 (1天): 业务指标体系
  └─ 目标: 模板填空替代从零探索

Phase 4 (0.5天): 技能路由强制执行
  └─ 目标: LLM不可绕过语义层

Phase 5 (0.5天): 测试框架
  └─ 目标: 改动后可回归验证
```

---

## 四、每个Phase的验收标准

| Phase | 验收标准 | 验证方式 |
|-------|---------|---------|
| 1 | 配置统一读取；每条查询有完整trace日志；server.py <100行 | 代码审查+日志检查 |
| 2 | 预算类型映射只有一处定义；修改预算类型前缀无需改3个文件 | 代码搜索验证 |
| 3 | "收入排名"问题1轮执行；新加预算类型只需加1个JSON | 实际查询测试 |
| 4 | 匹配到技能后LLM不调search_schema；未匹配时正常探索 | trace日志验证 |
| 5 | 核心工具函数有单元测试；改动后`pytest`通过 | CI运行 |

---

## 五、不做什么（明确排除）

- 不引入新的外部框架（保持轻量）
- 不重写agent_loop核心循环（稳定可靠）
- 不改变前端（只改后端架构）
- 不引入微服务/容器化（单进程够用）
