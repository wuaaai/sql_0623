# Phase 5: 稳定性 + 可观测性 + 测试框架 — 详细工程计划

## 一、现状诊断

Phase 1-4 完成了基础设施和业务语义层，但缺少质量保障体系。

| 维度 | 现状 | 问题 |
|------|------|------|
| 测试 | 无自动化测试 | 改代码后只能手动验证 |
| tracer | 有数据但未分析 | 日志堆积但没用来优化 |
| 文档 | 分散在 PLAN/ 和 tests/ | 新人不清楚从哪里开始 |
| 错误监控 | 控制台输出 | 无结构化错误日志 |

## 二、目标

1. **tracer 数据可分析** — 汇总查询统计，发现性能瓶颈
2. **自动化回归测试** — 核心路径可自动验证
3. **健康检查增强** — 启动时检测所有服务（达梦/PG/Embedding）状态
4. **README 更新** — 反映当前项目全貌

---

## 三、任务清单

### 任务1: tracer 统计报告工具

**创建 `tools/tracer_stats.py`**

```python
"""
tracer 统计分析 — 从日志中提取性能洞察
"""

import json, os, glob
from collections import defaultdict

TRACE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

def analyze_traces(limit: int = 100) -> dict:
    """分析最近N条trace日志，返回统计报告"""
    files = sorted(glob.glob(f"{TRACE_DIR}/*.json"), key=os.path.getmtime, reverse=True)[:limit]
    
    stats = {
        "total_queries": len(files),
        "avg_duration": 0,
        "avg_turns": 0,
        "tool_frequency": defaultdict(int),
        "tool_avg_time": defaultdict(list),
        "slowest_queries": [],
        "errors": 0
    }
    
    for f in files:
        try:
            with open(f) as fp:
                data = json.load(fp)
            total = data.get("total_seconds", 0)
            turns = data.get("turns", 0)
            stats["avg_duration"] += total
            stats["avg_turns"] += turns
            
            for step in data.get("steps", []):
                name = step.get("step", "")
                stats["tool_frequency"][name] += 1
                stats["tool_avg_time"][name].append(step.get("elapsed", 0))
            
            if total > 10:
                stats["slowest_queries"].append({
                    "id": data.get("query_id","")[:8],
                    "question": data.get("question","")[:80],
                    "duration": total,
                    "turns": turns
                })
        except Exception:
            stats["errors"] += 1
    
    if len(files) > 0:
        stats["avg_duration"] = round(stats["avg_duration"] / len(files), 2)
        stats["avg_turns"] = round(stats["avg_turns"] / len(files), 1)
    
    # 计算工具平均耗时
    tool_avg = {}
    for name, times in stats["tool_avg_time"].items():
        tool_avg[name] = round(sum(times) / len(times), 2)
    stats["tool_avg"] = dict(sorted(tool_avg.items(), key=lambda x: x[1], reverse=True))
    
    # 频率排序
    stats["tool_freq_rank"] = dict(sorted(stats["tool_frequency"].items(), key=lambda x: x[1], reverse=True))
    
    return stats
```

**使用方式**:
```bash
uv run python -c "from tools.tracer_stats import analyze_traces; import json; print(json.dumps(analyze_traces(), ensure_ascii=False, indent=2))"
```

**产物示例**:
```json
{
  "total_queries": 45,
  "avg_duration": 12.3,
  "avg_turns": 4.2,
  "tool_freq_rank": {"run_sql": 38, "search_schema": 22, "describe_table": 18},
  "tool_avg": {"rag_search": 2.5, "run_sql": 1.8, "describe_table": 1.2},
  "slowest_queries": [{"question": "衡水市各区县收入", "duration": 45.2, "turns": 18}]
}
```

**验收**: 运行 analyze_traces() 返回结构化统计报告

---

### 任务2: 健康检查增强

**增强 `GET /api/health`**

当前只检查达梦连接。增加检查项：

```python
@app.get("/api/health")
def health():
    status = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "dameng": {"connected": False, "schema": ""},
            "postgres": {"connected": False},
            "embedding": {"reachable": False},
            "rag_tool": {"ready": False}
        },
        "tools": len(TOOLS_SCHEMA),
        "uptime_seconds": int(time.time() - _start_time)
    }
    
    # 达梦
    if db_connection._connection:
        status["services"]["dameng"] = {"connected": True, "schema": db_connection._conn_info.get("schema","")}
    
    # PostgreSQL (向量库)
    try:
        from tools.config import config
        from sqlalchemy import create_engine, text
        engine = create_engine(config.RAG_DB_CONNECTION)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        status["services"]["postgres"]["connected"] = True
    except Exception:
        pass
    
    # Embedding
    try:
        import requests
        r = requests.get(config.RAG_EMBEDDING_URL.rsplit("/",1)[0], timeout=3)
        status["services"]["embedding"]["reachable"] = r.status_code < 500
    except Exception:
        pass
    
    # RAG工具
    try:
        from tools.rag_tool import _init_vector_store
        status["services"]["rag_tool"]["ready"] = _init_vector_store()
    except Exception:
        pass
    
    return status
```

**验收**: `GET /api/health` 返回4个服务状态

---

### 任务3: 自动化回归测试

**创建 `tests/` 测试框架**

#### 3.1 测试基础设施 `tests/conftest.py`

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
```

#### 3.2 配置测试 `tests/test_config.py`

```python
def test_config_loaded():
    from tools.config import config
    assert config.OPENAI_API_KEY, "API key not set"
    assert config.DB_TYPE == "dameng"

def test_tools_count():
    from tools.schema import TOOLS_SCHEMA
    assert len(TOOLS_SCHEMA) == 17

def test_business_rules():
    import json
    with open("memory/business_rules.json", encoding="utf-8") as f:
        rules = json.load(f)
    assert len(rules["budget_types"]) == 4
    assert len(rules["column_patterns"]) == 4

def test_metrics_all_budget_types():
    from tools.business_loader import load_business_metric
    for b in ["一般公共预算","社会保险","国有资本","政府性基金"]:
        r = load_business_metric(b, "完成情况")
        assert r["matched"] > 0, f"No metrics for {b}"

def test_skills_index():
    import json
    with open("memory/skills_index.json", encoding="utf-8") as f:
        index = json.load(f)
    assert len(index["skills"]) >= 8

def test_regions_tree():
    import json
    with open("data/region_tree.json", encoding="utf-8") as f:
        tree = json.load(f)
    assert tree["code"] == "130000000"
    assert len(tree.get("children", [])) == 11
```

#### 3.3 工具测试 `tests/test_tools.py`

```python
def test_tracer():
    from tools.tracer import QueryTracer
    t = QueryTracer("test-1", "test question")
    t.step("run_sql", rows=5)
    t.done(rows=5)
    # 验证日志文件已创建
    import os, glob
    files = glob.glob("logs/test-1*.json")
    assert len(files) > 0

def test_admin_db():
    from tools.admin_db import get_tables
    r = get_tables()
    assert r["total"] == 47  # 应已导入47张表

def test_error_classification():
    from tools.error_handler import classify_error
    assert classify_error("ORA-00904: invalid identifier") == "column"
    assert classify_error("ORA-00942: table not found") == "table"
    assert classify_error("syntax error") == "syntax"
```

**运行方式**:
```bash
uv run pytest tests/ -v
```

**验收**: 运行 `uv run pytest tests/ -v` 所有测试通过

---

### 任务4: README 更新

更新 `README.md`，反映当前项目全貌：

```markdown
# sql_0623 — Text-to-SQL + RAG 预算分析助手

## 项目概述
面向财政预算分析人员的自然语言查询助手。
- **Text-to-SQL**: 17个原子工具，达梦数据库47张表
- **RAG**: 知识库检索，2006条预算解读文档向量
- **管理后台**: Vue3 + Vite，表/文档权限管理

## 快速启动
cp .env.example .env  # 编辑配置
uv run python server.py  # 启动后端(8000)
cd admin && npm install && npm run dev  # 启动管理前端(3000)

## 项目结构
- server.py — FastAPI入口
- handler.py — 工具分发器 + ServerHandler
- tools/ — 17个原子工具
- memory/ — 业务规则 + 技能文件 + 业务指标
- admin/ — Vue3管理前端
- static/ — 聊天前端
- PLAN/ — 设计文档
- tests/ — 测试文件

## 开发阶段
Phase 1: 配置中心 + 链路追踪 ✅
Phase 2: 业务规则JSON化 + 技能路由 ✅
Phase 3: 业务指标体系 ✅
Phase 4: 指标全覆盖 + 代码健康度 ✅
Phase 5: 稳定性 + 测试框架 ← 当前

## 技术栈
Python 3.11 | FastAPI | OpenAI SDK | Dameng | PostgreSQL+pgvector | Vue3+Vite
```

---

## 四、改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `tools/tracer_stats.py` | **新建** | tracer统计分析 |
| `tests/conftest.py` | **新建** | pytest配置 |
| `tests/test_config.py` | **新建** | 配置+规则验证 |
| `tests/test_tools.py` | **新建** | 工具功能验证 |
| `server.py` | **修改** | 增强 /api/health |
| `README.md` | **修改** | 更新项目说明 |

**总计**: 4个新文件 + 2个文件修改

---

## 五、验收清单

| # | 检查项 | 验证方式 |
|---|--------|---------|
| 1 | tracer统计可运行 | `analyze_traces()` 返回结构化报告 |
| 2 | health返回4个服务状态 | `curl localhost:8000/api/health` |
| 3 | pytest通过 | `uv run pytest tests/ -v` 全部绿色 |
| 4 | 配置测试覆盖 | test_config全通过 |
| 5 | 工具测试覆盖 | test_tools全通过 |
| 6 | README更新 | 反映当前项目全貌 |
