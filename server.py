"""
Text-to-SQL Web 服务

FastAPI 后端，提供:
- POST /api/connect    连接数据库
- POST /api/chat       自然语言查询 (返回结构化结果)
- GET  /api/tables     列出表
- GET  /api/health     健康检查
"""

import json
import os
import sys

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi import UploadFile
from pydantic import BaseModel
from typing import Optional
import asyncio
import uuid
from datetime import datetime

# 会话目录
SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

sys.path.insert(0, os.path.dirname(__file__))

from openai import OpenAI
from agent_loop import agent_runner_loop
from tools.schema import TOOLS_SCHEMA
from tools import db_connection, db_query, pattern_store, memory_core, admin_db
from tools.config import config


# ==== 请求/响应模型 ====

class ConnectRequest(BaseModel):
    db_type: str = "dameng"
    host: str = "localhost"
    port: int = 5236
    user: str = "SYSDBA"
    password: str = "SYSDBA001"
    database: Optional[str] = None
    db_schema: Optional[str] = "RDYS_PUBLIC_TBS"


class ChatRequest(BaseModel):
    question: str
    clarify_count: int = 0


class ChatResponse(BaseModel):
    answer: str
    sql: Optional[str] = None
    columns: Optional[list] = None
    rows: Optional[list] = None
    tool_calls: list = []


# ==== FastAPI 应用 ====

app = FastAPI(title="Text-to-SQL Agent", version="0.1.0")


def _load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return "你是 Text-to-SQL 助手。"


def _build_client():
    """从环境变量创建 OpenAI 客户端"""
    client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
    client.model = config.OPENAI_MODEL
    return client


# ==== 自定义 Handler: 捕获 SQL 和查询结果 ====

from handler import TextToSQLHandler, StepOutcome


class ServerHandler(TextToSQLHandler):
    """服务端 Handler, 额外捕获 SQL 和结果"""

    def __init__(self):
        super().__init__()
        self.captured_sql = None
        self.captured_columns = None
        self.captured_rows = None
        self.captured_table = None

    def do_run_sql(self, args: dict) -> StepOutcome:
        self.captured_sql = args.get("sql", "")
        # 从SQL提取表名
        import re
        m = re.search(r'\bFROM\s+([a-zA-Z_][\w.]*)', self.captured_sql or "", re.IGNORECASE)
        if m:
            self.captured_table = m.group(1)
        outcome = super().do_run_sql(args)
        if outcome.data and outcome.data.get("status") == "success":
            self.captured_columns = outcome.data.get("columns", [])
            self.captured_rows = outcome.data.get("rows", [])
        return outcome


# ==== API 路由 ====

@app.get("/api/health")
def health():
    return {"status": "ok", "connected": db_connection._connection is not None}


@app.post("/api/connect")
def connect(req: ConnectRequest):
    result = db_connection.connect_db(
        db_type=req.db_type,
        host=req.host,
        port=req.port,
        user=req.user,
        password=req.password,
        database=req.database,
        schema=req.db_schema
    )
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/tables")
def list_tables():
    result = db_connection.list_tables()
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.post("/api/chat")
def chat(req: ChatRequest):
    if db_connection._connection is None:
        raise HTTPException(status_code=400, detail="请先连接数据库")

    client = _build_client()
    system_prompt = _load_system_prompt()

    # L0 元规则（最高优先级，永远生效）
    l0_path = os.path.join(os.path.dirname(__file__), "memory", "L0_meta_rules.md")
    if os.path.exists(l0_path):
        with open(l0_path, "r", encoding="utf-8") as f:
            system_prompt = f.read() + "\n\n" + system_prompt

    # 注入工作记忆
    wm = memory_core.load_working_memory()
    if wm.get("discoveries"):
        system_prompt += "\n[工作记忆] "
        system_prompt += "; ".join(f"{k}={v}" for k, v in list(wm["discoveries"].items())[-5:])

    # DB连接
    conn = db_connection._conn_info or {}
    system_prompt += f"\n\n[DB: dameng, schema={conn.get('schema', '')}, 已连接。禁止调connect_db，直接调run_sql查数据。]"

    # 注入全局记忆
    mem_path = os.path.join(os.path.dirname(__file__), "memory", "global_mem.txt")
    if os.path.exists(mem_path):
        with open(mem_path, "r", encoding="utf-8") as f:
            system_prompt += f"\n\n[全局记忆]\n{f.read()}"

    # 注入会话上下文(上一轮的查询摘要)
    session_ctx = _load_context()
    if session_ctx.get("last_table") or session_ctx.get("last_question"):
        system_prompt += (
            f"\n\n[上一轮查询] 用户刚问过: {session_ctx.get('last_question','')[:100]}\n"
            f"使用的表: {session_ctx.get('last_table','')}\n"
            f"SQL: {session_ctx.get('last_sql','')[:200]}\n"
            f"预算类型: {session_ctx.get('budget_type','')} | 时间: {session_ctx.get('time_period','')}\n"
            f"【用户当前问题是上一轮的追问，复用上一轮的表名和上下文，只改筛选条件。】\n"
        )

    # 注入相似历史查询模式
    patterns = pattern_store.search_patterns(req.question, limit=3)
    if patterns.get("matched", 0) > 0:
        top = patterns["patterns"][0]
        if top.get("similarity", 0) >= 80:
            # 高相似度：直接复用，跳过探索
            system_prompt += (
                f"\n\n[强制-复用历史模式 相似度{top.get('similarity',0)}%]\n"
                f"历史问题: {top.get('question','')[:100]}\n"
                f"表名: {top.get('table','')}\n"
                f"SQL: {top.get('sql','')[:300]}\n"
                f"【禁止调用 search_schema 和 describe_table。直接用上表名写SQL执行 run_sql。】\n"
            )
        else:
            system_prompt += "\n\n[参考-相似历史查询]\n"
            for i, p in enumerate(patterns.get("patterns", [])):
                system_prompt += (
                    f"[模式{i+1}] 相似度{p.get('similarity',0)}% | "
                    f"表: {p.get('table','')} | "
                    f"SQL: {p.get('sql','')[:150]}\n"
                )
            system_prompt += "请参考以上模式，不需要重新探索表结构。\n"

    # 追问次数限制：第3次(clarify_count>=2) 强制不追问
    if req.clarify_count >= 2:
        system_prompt += (
            "\n\n[强制规则] 你已经追问了2次，本次必须直接执行查询，不能再追问。"
            "缺失的条件使用默认值：\n"
            "- 时间→用 resolve_time(\"\") 获取最新数据\n"
            "- 地区→不筛选\n"
            "- 项目→用\"合计\"\n"
        )

    handler = ServerHandler()
    handler.current_question = req.question

    # 在用户消息前注入工具调用指令，防止 LLM 跳过工具直接编造
    user_msg = f"[强制] 你必须调用工具(run_sql/describe_table)获取真实数据后回答。禁止编造、禁止说'连接失败'。数据库已连接正常。\n用户问题: {req.question}"

    # 收集 agent 输出
    full_answer = ""
    for chunk in agent_runner_loop(
        client=client,
        system_prompt=system_prompt,
        user_input=user_msg,
        handler=handler,
        tools_schema=TOOLS_SCHEMA,
        max_turns=20,
        verbose=False
    ):
        full_answer += chunk

    # 保存成功的最终查询模式
    if handler.captured_sql:
        try:
            pattern_store.save_pattern(req.question, handler.captured_sql)
        except Exception:
            pass

    # 保存查询摘要到会话上下文（下一轮复用）
    try:
        ctx = _load_context()
        ctx["last_question"] = req.question[:100]
        ctx["last_table"] = handler.captured_table or _extract_table_from_sql(handler.captured_sql or "")
        ctx["last_sql"] = (handler.captured_sql or "")[:300]
        _save_context(ctx)
    except Exception:
        pass

    # 自动保存查询历史
    _append_history(req.question, handler.captured_sql or "")

    return ChatResponse(
        answer=full_answer.strip(),
        sql=handler.captured_sql,
        columns=handler.captured_columns,
        rows=handler.captured_rows,
        tool_calls=[]
    )


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式输出 chat 响应（SSE）"""
    if db_connection._connection is None:
        raise HTTPException(status_code=400, detail="请先连接数据库")

    client = _build_client()
    system_prompt = _load_system_prompt()

    # L0 元规则（最高优先级，永远生效）
    l0_path = os.path.join(os.path.dirname(__file__), "memory", "L0_meta_rules.md")
    if os.path.exists(l0_path):
        with open(l0_path, "r", encoding="utf-8") as f:
            system_prompt = f.read() + "\n\n" + system_prompt

    # 注入工作记忆
    wm = memory_core.load_working_memory()
    if wm.get("discoveries"):
        system_prompt += "\n[工作记忆] "
        system_prompt += "; ".join(f"{k}={v}" for k, v in list(wm["discoveries"].items())[-5:])

    # DB连接
    conn = db_connection._conn_info or {}
    system_prompt += (
        f"\n\n[DB: dameng, schema={conn.get('schema', '')}, 已连接，勿调connect_db]"
    )

    # 注入全局记忆
    mem_path = os.path.join(os.path.dirname(__file__), "memory", "global_mem.txt")
    if os.path.exists(mem_path):
        with open(mem_path, "r", encoding="utf-8") as f:
            system_prompt += f"\n\n[参考]\n{f.read()[:800]}"

    # 注入会话上下文
    session_ctx = _load_context()
    if session_ctx.get("budget_type") or session_ctx.get("region"):
        system_prompt += f"\n\n[会话上下文] 上次预算={session_ctx.get('budget_type','')} 地区={session_ctx.get('region','')}。优先复用。"

    # 注入相似历史查询模式
    patterns = pattern_store.search_patterns(req.question, limit=3)
    if patterns.get("matched", 0) > 0:
        top = patterns["patterns"][0]
        if top.get("similarity", 0) >= 80:
            system_prompt += (
                f"\n\n[强制-复用 相似度{top.get('similarity',0)}%] "
                f"表名:{top.get('table','')} SQL:{top.get('sql','')[:200]}\n"
                f"禁止调 search_schema 和 describe_table，直接用上表名写SQL执行 run_sql。\n"
            )
        else:
            system_prompt += "\n\n[参考-相似历史查询]\n"
            for p in patterns.get("patterns", []):
                system_prompt += f"[模式] 表:{p.get('table','')} SQL:{p.get('sql','')[:150]}\n"
            system_prompt += "参考以上模式，不需要重新探索。\n"

    # 追问限制（流式端点）
    if req.clarify_count >= 2:
        system_prompt += "\n\n[强制] 已追问2次，必须直接查。时间→最新, 地区→全部, 项目→合计"

    handler = ServerHandler()
    handler.current_question = req.question

    user_msg = f"[强制] 你必须调用工具(run_sql/describe_table)获取真实数据后回答。禁止编造、禁止说'连接失败'。数据库已连接正常。\n用户问题: {req.question}"

    async def generate():
        for chunk in agent_runner_loop(
            client=client,
            system_prompt=system_prompt,
            user_input=user_msg,
            handler=handler,
            tools_schema=TOOLS_SCHEMA,
            max_turns=20,
            verbose=False
        ):
            # 检测工具调用标记（agent_loop 中 yield 的格式）
            if chunk.startswith("🛠️"):
                yield f"data: {json.dumps({'type': 'tool', 'text': chunk}, ensure_ascii=False)}\n\n"
            elif chunk.strip():
                yield f"data: {json.dumps({'type': 'text', 'text': chunk}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)

        # 自动保存查询历史
        _append_history(req.question, handler.captured_sql or "")

        # 保存成功的最终查询模式
        if handler.captured_sql:
            try:
                pattern_store.save_pattern(req.question, handler.captured_sql)
            except Exception:
                pass

        # 发送最终结果
        result = {
            "type": "done",
            "sql": handler.captured_sql,
            "columns": handler.captured_columns,
            "rows": handler.captured_rows
        }
        yield f"data: {json.dumps(result, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ==== 会话管理 ====

def _load_context():
    """加载当前会话上下文"""
    ctx_path = os.path.join(SESSIONS_DIR, "current.json")
    if os.path.exists(ctx_path):
        try:
            with open(ctx_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"budget_type": "", "region": "", "time_period": "", "last_table": "", "last_query": ""}


def _save_context(ctx: dict):
    """保存会话上下文"""
    with open(os.path.join(SESSIONS_DIR, "current.json"), "w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False, indent=2)


def _load_history():
    """加载查询历史"""
    hist_path = os.path.join(SESSIONS_DIR, "history.json")
    if os.path.exists(hist_path):
        try:
            with open(hist_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _save_history(history: list):
    """保存查询历史（最多50条）"""
    with open(os.path.join(SESSIONS_DIR, "history.json"), "w", encoding="utf-8") as f:
        json.dump(history[:50], f, ensure_ascii=False, indent=2)


def _append_history(question: str, sql: str = ""):
    """追加查询到历史"""
    history = _load_history()
    history.insert(0, {
        "question": question,
        "sql": sql[:500] if sql else "",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    _save_history(history)


class SessionSaveRequest(BaseModel):
    budget_type: str = ""
    region: str = ""
    time_period: str = ""
    last_table: str = ""
    last_query: str = ""


@app.post("/api/session/save")
def session_save(req: SessionSaveRequest):
    ctx = req.model_dump()
    _save_context(ctx)
    return {"status": "ok", "context": ctx}


@app.get("/api/session/load")
def session_load():
    ctx = _load_context()
    history = _load_history()
    return {"status": "ok", "context": ctx, "history": history[:20]}


@app.get("/api/session/list")
def session_list():
    return {"status": "ok", "history": _load_history()[:50]}



# ==== 管理后台 API ====
@app.get("/api/admin/tables")
def admin_tables(search: str = "", budget_type: str = "", page: int = 1):
    return admin_db.get_tables(search, budget_type, page)

@app.get("/api/admin/tables/{table_name}")
def admin_table_detail(table_name: str):
    r = admin_db.get_table(table_name)
    if not r: raise HTTPException(404, "表不存在")
    return r

@app.post("/api/admin/tables")
async def admin_table_add(request: Request):
    req = await request.json()
    return admin_db.add_table(req.get("table_name",""), req.get("comment",""), req.get("budget_type",""))

@app.put("/api/admin/tables/{table_name}")
async def admin_table_update(table_name: str, request: Request):
    req = await request.json()
    return admin_db.update_table(table_name, req.get("comment"), req.get("budget_type"))

@app.delete("/api/admin/tables/{table_name}")
def admin_table_delete(table_name: str):
    return admin_db.delete_table(table_name)

@app.put("/api/admin/tables/{table_name}/toggle")
def admin_table_toggle(table_name: str):
    return admin_db.toggle_table(table_name)

@app.post("/api/admin/tables/{table_name}/sync")
def admin_table_sync(table_name: str):
    return admin_db.sync_table(table_name)

@app.get("/api/admin/tables/{table_name}/regions")
def admin_table_regions_get(table_name: str):
    return admin_db.get_table_regions(table_name)

@app.put("/api/admin/tables/{table_name}/regions")
async def admin_table_regions_set(table_name: str, request: Request):
    req = await request.json()
    return admin_db.set_table_regions(table_name, req.get("regions", []))

@app.get("/api/admin/documents")
def admin_docs(search: str = "", page: int = 1):
    return admin_db.get_documents(search, page)

@app.post("/api/admin/documents")
async def admin_doc_upload(file: UploadFile = None, regions: str = "[]"):
    if not file: raise HTTPException(400, "请上传文件")
    path = os.path.join(DATA_DIR, file.filename)
    with open(path, "wb") as f:
        f.write(await file.read())
    admin_db.add_document(file.filename, path)
    return {"status": "ok", "source": file.filename}

@app.delete("/api/admin/documents/{source}")
def admin_doc_delete(source: str):
    return admin_db.delete_document(source)

@app.put("/api/admin/documents/{source}/toggle")
def admin_doc_toggle(source: str):
    return admin_db.toggle_document(source)

@app.get("/api/admin/documents/{source}/regions")
def admin_doc_regions_get(source: str):
    return admin_db.get_doc_regions(source)

@app.put("/api/admin/documents/{source}/regions")
async def admin_doc_regions_set(source: str, request: Request):
    req = await request.json()
    return admin_db.set_doc_regions(source, req.get("regions", []))

@app.get("/api/admin/overview")
def admin_overview(region_code: str = ""):
    return admin_db.get_overview(region_code)

@app.get("/api/admin/regions/tree")
def admin_regions_tree():
    with open(os.path.join(DATA_DIR, "region_tree.json"), encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/admin/logs")
def admin_logs(page: int = 1):
    return admin_db.get_logs(page)

@app.get("/admin")
def admin_page():
    return FileResponse(os.path.join(static_dir, "admin.html"))


# ==== 静态文件 ====

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


# ==== 启动 ====

def main():
    import uvicorn
    # 启动时自动连接数据库
    try:
        db_connection.connect_db(
            db_type=config.DB_TYPE,
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            schema=config.DB_SCHEMA
        )
        print(f"[启动] 已自动连接数据库 {config.DB_SCHEMA}")
    except Exception as e:
        print(f"[启动] 数据库自动连接失败: {e}")
    # 初始化管理数据库（依赖达梦连接）
    admin_db.init_db()
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
