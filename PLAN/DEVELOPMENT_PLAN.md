# Text-to-SQL 项目开发计划

## 参考架构 (GenericAgent)

GenericAgent 核心架构:
- **Agent Loop** (~100行): 感知环境 → 任务推理 → 执行工具 → 写入记忆 → 循环
- **9个原子工具**: code_run, file_read, file_write, file_patch, web_scan, web_execute_js, ask_user, update_working_checkpoint, start_long_term_update
- **工具定义**: JSON Schema (OpenAI function-calling 格式)
- **Handler 模式**: BaseHandler.dispatch() 将工具名映射到 do_<tool_name>() 方法
- **分层记忆**: L0(元规则) → L1(索引) → L2(全局事实) → L3(技能SOP) → L4(会话存档)

## 项目目录结构

```
sql_0623/
├── README.md                  # 项目说明
├── CLAUDE.md                  # 开发规范
├── requirements.txt           # Python 依赖
├── main.py                    # 入口: 初始化Agent, 启动对话
├── agent_loop.py              # Agent 执行循环 (核心, ~100行)
├── agent_core.py              # Agent 主类: LLM客户端管理, 任务队列
├── handler.py                 # 工具分发器: do_<tool_name>() 实现
├── tools/
│   ├── __init__.py
│   ├── schema.py              # 所有工具的 JSON Schema 定义
│   ├── db_connection.py       # 数据库连接管理 (连接池)
│   ├── db_schema.py           # 表结构查询 (list_tables, describe_table, search_schema)
│   ├── db_query.py            # SQL执行 (run_sql, explain_sql, sample_data)
│   ├── db_write.py            # 写操作确认 (危险操作需用户确认)
│   ├── file_ops.py            # 文件读写工具
│   └── code_executor.py       # Python代码执行器
├── prompts/
│   └── system_prompt.txt      # text-to-SQL 系统提示词
├── memory/                    # Agent 记忆存储
│   └── global_mem.txt         # 全局记忆 (L2)
└── temp/                      # 临时文件 (查询结果缓存等)
```

## 分阶段开发步骤

### 第1阶段: 项目骨架 & Agent核心循环

**目标**: 搭建可运行的最小Agent框架

1. 创建项目目录结构
2. 实现 `agent_loop.py` — 核心执行循环
   - messages → LLM chat → 解析 tool_calls → dispatch → 收集结果 → 下一轮
3. 实现 `agent_core.py` — Agent主类
   - LLM客户端管理
   - 任务队列
   - 系统提示词加载
4. 实现 `handler.py` — BaseHandler + dispatch 机制
5. 实现 `tools/schema.py` — 先注册1个基础工具 (ask_user)
6. 实现 `main.py` — 命令行入口

**验证**: 启动Agent, 发送简单消息, 确认LLM调用和工具分发流程正确
**提交**: "feat: 搭建Agent核心框架，实现执行循环和工具分发机制"

---

### 第2阶段: 数据库连接工具

**目标**: 定义并实现数据库连接相关的原子工具

1. 实现 `tools/db_connection.py`:
   - `connect_db(db_type, host, port, user, password, database)` — 建立数据库连接
   - `list_connections()` — 查看当前所有连接
   - `close_connection(conn_id)` — 关闭指定连接
   - `test_connection(conn_id)` — 测试连接是否存活
2. 在 `tools/schema.py` 中注册工具定义
3. 在 `handler.py` 中实现 `do_connect_db`, `do_list_connections` 等方法
4. 支持 MySQL, PostgreSQL, SQLite

**验证**: Agent能接收"连接本地MySQL数据库"指令, 调用connect_db工具, 成功建立连接
**提交**: "feat: 实现数据库连接管理工具 (connect/list/test/close)"

---

### 第3阶段: Schema探索工具

**目标**: 让Agent能探索和理解数据库结构

1. 实现 `tools/db_schema.py`:
   - `list_tables(conn_id)` — 列出所有表
   - `describe_table(conn_id, table_name)` — 获取表结构 (列名、类型、注释)
   - `get_relationships(conn_id, table_name)` — 获取外键关系
   - `search_schema(conn_id, keyword)` — 按关键词搜索表和列名
   - `get_indexes(conn_id, table_name)` — 获取索引信息
2. 注册工具并实现 handler 方法

**验证**: Agent连接数据库后能自动探索表结构, 理解表之间的关系
**提交**: "feat: 实现Schema探索工具 (list/describe/search/indexes)"

---

### 第4阶段: SQL执行 & 验证工具

**目标**: Agent能生成并执行SQL, 验证结果

1. 实现 `tools/db_query.py`:
   - `run_sql(conn_id, sql)` — 执行SELECT查询, 返回结果
   - `explain_sql(conn_id, sql)` — 获取执行计划
   - `sample_data(conn_id, table_name, limit)` — 抽样查看表数据
   - `validate_sql(conn_id, sql)` — 语法校验 (EXPLAIN而不实际执行)
2. 实现 `tools/db_write.py`:
   - `run_write_sql(conn_id, sql)` — 执行INSERT/UPDATE/DELETE (需用户确认)
3. 注册工具并实现 handler 方法

**验证**: Agent能根据自然语言问题生成SQL, 先explain验证, 再执行并返回结果
**提交**: "feat: 实现SQL执行与验证工具 (run/explain/sample/validate)"

---

### 第5阶段: Text-to-SQL 完整流程

**目标**: 串联所有工具, 实现端到端的 text-to-SQL

1. 编写 `prompts/system_prompt.txt` — text-to-SQL专家提示词
   - 要求Agent先探索schema再写SQL
   - SQL编写规范 (格式化、别名、注释)
   - 安全规则 (禁止DROP/TRUNCATE, 写操作需确认)
2. 实现 `tools/code_executor.py` — Python代码执行器
   - 用于复杂的数据处理、结果可视化
3. 实现 `tools/file_ops.py`:
   - `save_result(path, data)` — 将查询结果保存为CSV/JSON
   - `load_context(path)` — 加载上下文文件
4. 添加 `tools/schema.py` 中注册所有工具

**验证**: 端到端测试: "查询上个月销售额最高的10个产品" → Agent自动探索schema → 生成SQL → 执行 → 返回结果
**提交**: "feat: 完成text-to-SQL完整流程，添加系统提示词和文件工具"

---

### 第6阶段: 增强 & 优化

**目标**: 提升准确率和用户体验

1. 多轮对话上下文管理 — Agent记住之前探索过的表和结构
2. 错误自动修复 — SQL执行失败时根据错误信息自动修正
3. 查询结果缓存 — 相同SQL短时间内不重复执行
4. 结果展示优化 — 表格格式化输出
5. 添加记忆系统 — 常用查询模式写入L2/L3记忆

**验证**: 复杂多轮对话: 先查用户表, 再查订单表, 最后关联查询 - Agent全程自动完成
**提交**: "feat: 多轮对话上下文、错误自修复、结果缓存与格式化"

---

### 第7阶段: 高级数据库工具

**目标**: 扩展更多专业数据库工具

1. `compare_tables(conn_id, table_a, table_b)` — 对比两张表结构差异
2. `find_similar_columns(conn_id, column_name)` — 查找相似列名
3. `suggest_join(conn_id, table_a, table_b)` — 建议JOIN条件
4. `get_table_stats(conn_id, table_name)` — 获取表统计信息 (行数、大小)
5. `export_schema_doc(conn_id, output_path)` — 导出数据库文档

**验证**: Agent能在复杂多表场景下自动找到关联关系并生成正确的JOIN查询
**提交**: "feat: 高级数据库工具 (compare/find_similar/suggest_join/stats/export)"

---

## 技术选型

| 组件 | 选型 | 原因 |
|------|------|------|
| LLM调用 | openai SDK (兼容多厂商) | 通用标准, 支持OpenAI/DeepSeek等 |
| 数据库驱动 | pymysql + psycopg2 + sqlite3 | 覆盖主流数据库 |
| SQL解析 | sqlparse (仅做格式化, 不做复杂解析) | 轻量 |
| 异步 | 不需要 | text-to-SQL场景不需要高并发 |

## 核心设计原则

1. **原子工具**: 每个工具只做一件事, 输入输出清晰
2. **Agent自主决策**: Agent自己决定调用哪些工具、什么顺序, 不硬编码流程
3. **安全第一**: 写操作必须用户确认, 禁止危险SQL
4. **Schema优先**: 生成SQL前必须先探索表结构, 不允许盲写
