# Phase 1: 基建重构 — 详细工程实施计划

## 目标

建立项目工程化基础，使代码可追溯、可配置、可拆分。

## 当前问题清单

| # | 问题 | 具体表现 | 风险 |
|---|------|---------|------|
| 1 | 配置散落 | `os.environ.get("KEY","default")` 在6个文件中各写各的默认值 | 环境切换时一处漏改就出错 |
| 2 | 无追踪 | 查询出错只知道"达到最大轮次"，不知道哪一步耗时多 | 无法定位性能瓶颈 |
| 3 | server.py臃肿 | 单个文件包含聊天/管理/会话/流式4种逻辑共600行 | 改动任何功能都要读600行 |
| 4 | handler.py臃肿 | 16个do_方法 + 4个辅助函数在同一个类中 | 加新工具要修改这个类 |
| 5 | tools/目录扁平 | 16个py文件平铺，分不清哪些是数据库工具哪些是RAG工具 | 新人不知道从哪里看起 |

## 改动范围

**只改后端，不改前端。只重构结构，不改功能逻辑。**

---

## 任务1: 统一配置中心

### 创建 `tools/config.py`

```python
"""
统一配置中心 — 唯一配置入口
所有模块从这里读取配置，不再直接调 os.environ.get
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# 项目启动时自动加载 .env
_loaded = False

def _ensure_loaded():
    global _loaded
    if not _loaded:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        load_dotenv(env_path)
        _loaded = True


def _get(key: str, default: str = "") -> str:
    _ensure_loaded()
    return os.environ.get(key, default)


@dataclass
class Config:
    """全局配置单例"""

    # LLM
    OPENAI_API_KEY: str = field(default_factory=lambda: _get("OPENAI_API_KEY"))
    OPENAI_BASE_URL: str = field(default_factory=lambda: _get("OPENAI_BASE_URL", "https://api.deepseek.com"))
    OPENAI_MODEL: str = field(default_factory=lambda: _get("OPENAI_MODEL", "deepseek-chat"))

    # 达梦数据库
    DB_TYPE: str = field(default_factory=lambda: _get("DB_TYPE", "dameng"))
    DB_HOST: str = field(default_factory=lambda: _get("DB_HOST", "localhost"))
    DB_PORT: int = field(default_factory=lambda: int(_get("DB_PORT", "5236")))
    DB_USER: str = field(default_factory=lambda: _get("DB_USER", "SYSDBA"))
    DB_PASSWORD: str = field(default_factory=lambda: _get("DB_PASSWORD", "SYSDBA001"))
    DB_SCHEMA: str = field(default_factory=lambda: _get("DB_SCHEMA", "RDYS_PUBLIC_TBS"))

    # RAG
    RAG_EMBEDDING_URL: str = field(default_factory=lambda: _get("RAG_EMBEDDING_URL", "http://10.32.10.160:8991/embed"))
    RAG_RERANK_URL: str = field(default_factory=lambda: _get("RAG_RERANK_URL", "http://10.32.10.160:8991/rerank"))
    RAG_DB_CONNECTION: str = field(default_factory=lambda: _get("RAG_DB_CONNECTION", "postgresql+psycopg2://postgres:ROOT@127.0.0.1:5432/postgres?client_encoding=utf8"))
    RAG_COLLECTION: str = field(default_factory=lambda: _get("RAG_COLLECTION", "parent_child_db_1024"))

    # 服务
    SERVER_HOST: str = field(default_factory=lambda: _get("SERVER_HOST", "127.0.0.1"))
    SERVER_PORT: int = field(default_factory=lambda: int(_get("SERVER_PORT", "8000")))


# 全局单例
config = Config()
```

### 迁移规则

逐个文件替换 `os.environ.get("KEY", "default")` → `config.KEY`：

| 文件 | 替换处 | 
|------|--------|
| server.py | 6处（DB_*, LLM） |
| tools/rag_tool.py | 3处（RAG_*） |
| tools/rag_ingest.py | 3处（RAG_*） |
| tools/admin_db.py | 1处（RAG_DB_CONNECTION） |
| agent_core.py | 3处（OPENAI_*） |

### 验收标准

```bash
# 1. 所有模块通过 config.XXX 读取配置
grep -r "os.environ.get" tools/ server.py agent_core.py handler.py | wc -l
# 预期: 0

# 2. 修改 .env 后重启生效
# 3. config对象导入无副作用
```

---

## 任务2: 链路追踪日志

### 创建 `tools/tracer.py`

```python
"""
链路追踪日志 — 每次查询记录完整调用链
"""

import time, json, os
from datetime import datetime

TRACE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(TRACE_DIR, exist_ok=True)


class QueryTracer:
    """单次查询的追踪器"""

    def __init__(self, query_id: str, question: str):
        self.query_id = query_id
        self.question = question
        self.steps = []
        self.start_time = time.time()
        self._log("START", question=question[:100])

    def step(self, name: str, **kwargs):
        elapsed = round(time.time() - self.start_time, 2)
        entry = {"step": name, "elapsed": elapsed, **kwargs}
        self.steps.append(entry)
        self._log(name, elapsed=f"{elapsed}s", **kwargs)

    def done(self, turns: int = 0, sql: str = "", rows: int = 0):
        total = round(time.time() - self.start_time, 2)
        self.steps.append({"step": "DONE", "elapsed": total, "turns": turns, "rows": rows})
        self._log("DONE", elapsed=f"{total}s", turns=turns, rows=rows)
        self._save()

    def _log(self, step: str, **kwargs):
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items() if v)
        print(f"[TRACE {self.query_id[:8]}] {step} | {extra}")

    def _save(self):
        log_file = os.path.join(TRACE_DIR, f"{self.query_id[:8]}.json")
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump({
                "query_id": self.query_id,
                "question": self.question,
                "steps": self.steps,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
```

### 集成点

在 server.py 的 chat 和 chat_stream 端点中：

```python
import uuid
from tools.tracer import QueryTracer

# 每个请求创建一个tracer
tracer = QueryTracer(str(uuid.uuid4()), req.question)

# agent_loop之前记录
tracer.step("agent_start")

# 每轮循环中记录工具调用
# （在handler.dispatch中增加tracer记录）

# 完成后
tracer.done(turns=turn, sql=handler.captured_sql, rows=len(handler.captured_rows or []))
```

### 日志输出示例

```
[TRACE a1b2c3d4] START | question=河北省一般公共预算收入完成得怎么样
[TRACE a1b2c3d4] search_schema | elapsed=1.2s | keyword=一般公共预算收入
[TRACE a1b2c3d4] describe_table | elapsed=2.5s | table=RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC
[TRACE a1b2c3d4] run_sql | elapsed=3.8s | sql=SELECT... | rows=5
[TRACE a1b2c3d4] DONE | elapsed=4.2s | turns=3 | rows=5
```

### 验收标准

```bash
# 1. 每次查询后 logs/ 目录有对应日志文件
ls logs/

# 2. 日志包含完整的步骤记录
cat logs/a1b2c3d4.json | python -m json.tool

# 3. 控制台实时输出追踪信息
```

---

## 任务3: Server 服务层拆分

### 3.1 创建 `services/chat_service.py`

将 server.py 中 ~200 行的聊天逻辑（system_prompt构建、上下文注入、agent_loop调用）提取为独立函数：

```python
# services/chat_service.py

def build_system_prompt(question: str, clarify_count: int = 0) -> str:
    """构建完整的system_prompt（L0规则 + 工作记忆 + 全局记忆 + 会话上下文 + 历史模式 + 追问限制）"""
    
def run_chat(question: str, clarify_count: int = 0) -> ChatResponse:
    """执行一次非流式聊天"""

async def run_chat_stream(question: str, clarify_count: int = 0) -> AsyncGenerator:
    """执行一次流式聊天（生成器）"""
```

### 3.2 创建 `services/session_service.py`

```python
# services/session_service.py

def load_context() -> dict:
def save_context(ctx: dict):
def load_history() -> list:
def append_history(question: str, sql: str):
```

### 3.3 Server.py 瘦身

```python
# server.py — 只保留路由注册（目标 <80行）

from services.chat_service import run_chat, run_chat_stream
from services.session_service import load_context, save_context, load_history
from services.admin_service import (get_tables, add_table, delete_table, ...)

@app.post("/api/chat")
def chat(req: ChatRequest):
    return run_chat(req.question, req.clarify_count)

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    return StreamingResponse(run_chat_stream(req.question, req.clarify_count), ...)
```

### 拆分前后对比

| 文件 | 拆分前 | 拆分后 |
|------|--------|--------|
| server.py | 600行 | <100行（纯路由） |
| services/chat_service.py | - | ~250行（聊天逻辑） |
| services/session_service.py | - | ~80行（会话管理） |
| services/admin_service.py | - | ~60行（管理API） |

### 验收标准

```bash
wc -l server.py  # < 100行
ls services/      # 至少3个文件
```

---

## 任务4: Handler 工具分类

### 当前问题

`handler.py` 470行，16个 `do_` 方法平铺。新增工具需要：
1. 在 `tools/xxx.py` 写实现
2. 在 `tools/schema.py` 加注册
3. 在 `handler.py` 加 `do_xxx` 方法
4. 在 `handler.py` 加 import

步骤3和4每次都要改handler.py，容易冲突。

### 解决方案: 工具自注册

每个工具模块自带 handler 方法，通过装饰器自动注册：

```python
# tools/database/query.py

from tools.registry import tool_handler

@tool_handler("run_sql")
def handle_run_sql(args: dict) -> StepOutcome:
    ...
```

`tools/registry.py` 维护一个全局 dict，`handler.py` 的 dispatch 从 dict 中查找，不再需要逐个写 if/elif。

### 实施

只做目录重组，不改函数逻辑：

```
tools/
├── registry.py             # 工具注册表（新）
├── database/               # 数据库工具（重组）
│   ├── connect.py          # connect_db
│   ├── schema.py           # describe_table, search_schema, list_tables
│   ├── query.py            # run_sql
│   └── aggregation.py      # run_aggregation
├── analysis/               # 分析工具（重组）
│   ├── subquery.py         # run_subquery
│   ├── ratio.py            # calc_ratio
│   ├── anomaly.py          # detect_anomalies
│   └── cross_table.py      # find_relations, union_query
├── rag/                    # RAG工具（重组）
│   ├── search.py           # rag_search
│   └── ingest.py           # 文档导入
├── memory/                 # 记忆工具（重组）
│   ├── memory_core.py      # search_memory
│   └── pattern_store.py    # search_patterns
├── admin/                  # 管理工具
│   └── admin_db.py         # 表/文档管理
├── infra/                  # 基础工具（重组）
│   ├── config.py           # 配置中心
│   ├── tracer.py           # 链路追踪
│   ├── time_resolver.py    # resolve_time
│   ├── suggest_columns.py  # suggest_columns
│   └── error_handler.py    # 错误处理
└── schema.py               # 工具schema定义（保留）
```

### 验收标准

```bash
# 1. 目录结构正确
ls tools/database/ tools/analysis/ tools/rag/ tools/infra/

# 2. 原有功能不受影响
uv run python -c "from tools.schema import TOOLS_SCHEMA; print(len(TOOLS_SCHEMA), 'tools')"

# 3. handler.py import 行减少
grep "^from tools import" handler.py  # 应该只有1-2行
```

---

## 实施顺序

```
1. 创建 tools/config.py → 所有模块迁移
2. 创建 tools/tracer.py → handler中集成
3. 创建 services/ → server.py拆分
4. 重组 tools/ 目录
```

每步完成后验证服务能正常启动并处理查询。

---

## Phase 1 完成后的项目结构

```
sql_0623/
├── server.py              # 纯路由注册 (<100行)
├── handler.py              # 工具分发器 (精简)
├── agent_loop.py           # Agent循环 (不变)
├── services/               # 服务层 (新)
│   ├── chat_service.py
│   ├── session_service.py
│   └── admin_service.py
├── tools/
│   ├── config.py           # 配置中心 (新)
│   ├── tracer.py           # 链路追踪 (新)
│   ├── registry.py         # 注册表 (新)
│   ├── schema.py
│   ├── database/           # 数据库工具 (重组)
│   ├── analysis/           # 分析工具 (重组)
│   ├── rag/                # RAG工具 (重组)
│   ├── memory/             # 记忆工具 (重组)
│   ├── admin/              # 管理工具 (重组)
│   └── infra/              # 基础工具 (重组)
├── memory/
├── prompts/
├── PLAN/
├── tests/
├── admin/                  # 管理前端
├── static/                 # 聊天前端
├── logs/                   # 追踪日志 (新)
└── data/
```

## 验收总清单

| # | 检查项 | 验证方式 |
|---|--------|---------|
| 1 | config.py作为唯一配置入口 | `grep -r "os.environ.get" tools/ server.py` = 0 |
| 2 | 每次查询产生trace日志 | `ls logs/` 有文件 |
| 3 | server.py <100行 | `wc -l server.py` |
| 4 | tools/按功能分类 | `ls tools/database/ tools/analysis/ tools/rag/` |
| 5 | 16个工具全部可导入 | `from tools.schema import TOOLS_SCHEMA; len(TOOLS_SCHEMA) == 16` |
| 6 | 服务正常启动 | `uv run python server.py` 启动无报错 |
| 7 | 查询功能正常 | 前端发送查询能正常返回结果 |
