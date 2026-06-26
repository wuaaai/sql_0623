# 阶段8: RAG问答 + Text-to-SQL 融合 — "既能问数，也能问答"

## 一、RAG项目架构分析

### 现有RAG项目 "Langchain (2)" 核心架构

```
Dify前端 → /v1/chat/completions (OpenAI兼容)
  → extract_region_code (地区码提取)
  → memory_manager.filter_recent_user_messages (Token感知历史压缩)
  → LangGraph Agent (my_agent1)
    ├─ 知识检索工具 (向量检索 data/*.docx 预算解读文档)
    ├─ rag_limiter (每轮最多4次知识库调用)
    └─ 流式输出 (SSE)
```

**知识库数据**: `data/` 目录 — 2019-2026年河北省预算解读 docx 文档 + 邯郸市预算解读
**向量存储**: Vastbase G100 向量数据库
**Agent框架**: LangGraph + LangChain
**API格式**: Dify 兼容的 OpenAI `/v1/chat/completions`

### 与Text-to-SQL项目的对比

| 维度 | Text-to-SQL | RAG项目 | 融合后 |
|------|-----------|---------|--------|
| 能力 | 查结构化数据（达梦数据库） | 查非结构化文档（预算解读） | 两者兼备 |
| Agent | OpenAI function calling | LangGraph Agent | 统一Agent |
| API | `/api/chat/stream` | `/v1/chat/completions` | 统一端点 |
| 工具 | 15个数据库原子工具 | RAG检索工具 | 15+1工具集 |
| 前端 | 预算Agent（自研） | Dify | 预算Agent增强 |
| 记忆 | 会话上下文 + 查询模式 | Token压缩记忆 | 统一记忆系统 |

---

## 二、产品设计（硅谷PM视角）

### 核心价值主张

**用户不再需要判断"这个问题该问数据库还是问知识库"**。一个输入框，Agent 自动判断：
- 用户问的是数据 → 走 Text-to-SQL 工具链
- 用户问的是知识/政策 → 走 RAG 检索工具链
- 用户既问数据又问政策 → 先查知识库理解上下文，再查数据库

### 典型用户场景

| 用户问题 | Agent判断 | 执行路径 |
|---------|---------|---------|
| "衡水市一般公共预算收入多少" | 数据查询 | Text-to-SQL |
| "2026年预算编制有什么新政策" | 知识问答 | RAG检索 |
| "预算解读中提到的新增专项转移支付，实际执行了多少" | 混合 | RAG→理解政策→提取关键词→Text-to-SQL查数据 |

### 前端体验设计

```
┌─────────────────────────────────────────────┐
│  预算Agent                                  │
├─────────────────────────────────────────────┤
│  输入框（一个输入框，自动路由）                 │
│  💬 问数据："衡水市收入多少"                    │
│  📚 问知识："2026年预算编制要求"                │
│  🔀 混合："新政策执行了多少钱"                  │
├─────────────────────────────────────────────┤
│  侧边栏：                                    │
│  - 数据库状态                               │
│  - 知识库状态（文档数量/最后更新时间）           │
│  - 表列表                                   │
└─────────────────────────────────────────────┘
```

### 智能路由策略

```
用户提问
  ├─ 包含数据关键词(收入/支出/金额/排名/累计/完成) → Text-to-SQL
  ├─ 包含知识关键词(政策/解读/要求/规定/编制/管理) → RAG
  ├─ 同时包含 → 混合模式(RAG先→SQL后)
  └─ 不确定 → 两者都查，对比结果给出最佳回答
```

---

## 三、工程实现（硅谷工程师视角）

### 集成架构

```
用户提问
  → 统一路由判断 (route_query)
  ├─ 数据库路径: search_schema → describe_table → run_sql → 答案
  ├─ 知识库路径: RAG检索 → LLM生成答案
  ├─ 混合路径: RAG检索 → 提取实体 → search_schema → run_sql → 综合答案
  └─ 自动路径: 两条路径都走 → 对比 → 选最佳答案
```

### 具体改动清单

#### 1. 新增 `tools/rag_tool.py` — RAG检索工具

```python
def search_knowledge_base(query: str, top_k: int = 5) -> dict:
    """搜索预算解读知识库，返回相关文档片段"""
    # 调用 Vastbase 向量检索
    # 返回: {"status": "success", "documents": [...], "sources": [...]}
```

注册为第16个原子工具: `rag_search`

#### 2. 新增 `tools/query_router.py` — 智能路由

```python
def route_query(question: str) -> str:
    """判断问题类型: sql / rag / hybrid"""
    data_keywords = ["收入","支出","金额","排名","累计","完成","预算数","执行","同比","环比"]
    knowledge_keywords = ["政策","解读","要求","规定","编制","管理","改革","制度","通知","办法"]
    
    has_data = any(kw in question for kw in data_keywords)
    has_knowledge = any(kw in question for kw in knowledge_keywords)
    
    if has_data and has_knowledge: return "hybrid"
    if has_data: return "sql"
    if has_knowledge: return "rag"
    return "auto"
```

#### 3. 修改 `server.py` — 路由注入

在 system_prompt 中注入路由判断结果，指导 LLM 选择正确的工具链。

#### 4. 修改 `static/index.html` — 前端路由展示

在回答中标注信息来源（数据库 / 知识库）。

#### 5. 新增 `memory/skills/rag_router.md` — 路由策略技能

### 保留原有功能

- ✅ Text-to-SQL 全部15个工具不变
- ✅ 前端界面不变（增强而非替换）
- ✅ 记忆系统不变
- ✅ 查询模式复用不变
- ✅ RAG项目独立可运行（不破坏原有服务）

### 新增依赖

| 依赖 | 用途 |
|------|------|
| `langchain-core` | LangChain消息模型 |
| `langgraph` | Agent编排（可选，复用现有agent_loop也可） |

---

## 四、实现步骤

### Phase 1: 知识库工具集成 (核心)

1. 从RAG项目提取 `rag_search` 检索函数
2. 封装为原子工具，注册到 `tools/schema.py`
3. 在 handler.py 添加 `do_rag_search`
4. 验证: "2026年预算编制有什么新政策"

### Phase 2: 智能路由

1. 创建 `query_router.py`
2. server.py 中注入路由判断到 system_prompt
3. LLM 根据路由选择工具链
4. 验证: 混合问题走双路径

### Phase 3: 前端增强

1. 回答中标注来源（数据库/知识库）
2. 侧边栏显示知识库状态
3. 知识库文档列表

### Phase 4: 深度集成

1. RAG检索结果辅助SQL生成（从政策文档中提取表名/列名）
2. SQL结果辅助RAG回答（用真实数据校验政策解读）
3. 统一记忆系统（数据查询+RAG问答共享上下文）

---

## 五、验收标准

| # | 场景 | 预期 |
|---|------|------|
| 1 | "衡水市收入多少" | 走SQL路径，返回数据 |
| 2 | "2026年预算编制新政策" | 走RAG路径，检索文档 |
| 3 | "解读中提到的新增转移支付执行了多少" | RAG→提取关键词→SQL→综合答案 |
| 4 | 所有原有SQL查询功能不受影响 | 回归测试通过 |
