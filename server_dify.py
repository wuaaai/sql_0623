"""
Text-to-SQL + RAG Dify 兼容后端（完整版）

提供 Dify 平台兼容的 OpenAI 格式 API:
- GET  /v1/models          凭据验证
- POST /v1/chat/completions 对话接口 (流式SSE)
- GET  /api/health          健康检查

与 server.py 共享全部业务逻辑: 配置中心/L0规则/工作记忆/会话上下文/
相似模式注入/业务指标强制执行/链路追踪/追问限制/查询模式保存
"""

import uvicorn, os, sys, re, time, json, uuid, traceback, asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from openai import OpenAI
from agent_loop import agent_runner_loop
from tools.schema import TOOLS_SCHEMA
from tools import db_connection, pattern_store, memory_core
from tools.config import config
from tools.tracer import QueryTracer
from handler import TextToSQLHandler, StepOutcome, ServerHandler

SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

app = FastAPI(title="预算 Agent Dify API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ================= 启动初始化 =================
def _init():
    db_connection.connect_db(db_type=config.DB_TYPE, host=config.DB_HOST, port=config.DB_PORT,
                             user=config.DB_USER, password=config.DB_PASSWORD, schema=config.DB_SCHEMA)
    print(f"[Dify] DB: {config.DB_SCHEMA}")
    from tools.admin_db import init_db
    init_db()

_init()
_start_time = time.time()

# ================= 数据模型 =================
class OpenAIMessage(BaseModel):
    role: str
    content: str

class OpenAIRequest(BaseModel):
    model: str = "budget-agent"
    messages: List[OpenAIMessage]
    stream: bool = True
    user: Optional[str] = "default_user"
    region_code: Optional[str] = None

# ================= 会话管理 =================
def _load_context():
    ctx_path = os.path.join(SESSIONS_DIR, "current.json")
    if os.path.exists(ctx_path):
        try:
            with open(ctx_path, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {}

def _save_context(ctx: dict):
    with open(os.path.join(SESSIONS_DIR, "current.json"), "w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False, indent=2)

# ================= 导入业务逻辑 =================
from server import _inject_guidance, _load_system_prompt

_REGION_CODE_PATTERN = re.compile(r"\n{2,}(\d{6,9})\s*$")

def _extract_region(messages: list):
    if not messages: return None, None
    for msg in reversed(messages):
        if msg.role == "user":
            m = _REGION_CODE_PATTERN.search(msg.content)
            if m:
                code = m.group(1)
                cleaned = _REGION_CODE_PATTERN.sub("", msg.content).rstrip()
                return code, cleaned
            break
    return None, None

# ================= API =================
@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": [{"id": "budget-agent", "object": "model", "owned_by": "custom"}]}


@app.get("/api/health")
def health():
    srv = {"status": "ok", "tools": len(TOOLS_SCHEMA), "uptime": int(time.time()-_start_time)}
    srv["services"] = {"dameng": "connected" if db_connection._connection else "disconnected"}
    if db_connection._conn_info: srv["services"]["schema"] = db_connection._conn_info.get("schema","")
    try:
        from sqlalchemy import create_engine, text
        e = create_engine(config.RAG_DB_CONNECTION)
        with e.connect() as c: c.execute(text("SELECT 1"))
        srv["services"]["postgres"] = "connected"
    except Exception: srv["services"]["postgres"] = "disconnected"
    try:
        import requests
        r = requests.get(config.RAG_EMBEDDING_URL.rsplit("/",1)[0], timeout=3)
        srv["services"]["embedding"] = "reachable"
    except Exception: srv["services"]["embedding"] = "unreachable"
    return srv


@app.post("/v1/chat/completions")
async def dify_chat(request: OpenAIRequest, raw_request: Request):
    try:
        raw_body = await raw_request.json()
        conversation_id = raw_body.get("sys.conversation_id", str(uuid.uuid4()))

        region_code, cleaned_q = _extract_region(request.messages)
        question = cleaned_q or next((m.content for m in reversed(request.messages) if m.role == "user"), "")

        # Dify 凭据验证: 仅对明确的测试词做快返，真实问题走完整流程
        _test_words = ("ping", "hello", "hi", "test", "help", "测试", "连接测试")
        if question.strip().lower() in _test_words or question.strip() == "你好":
            return {
                "id": f"chatcmpl-{int(time.time())}", "object": "chat.completion",
                "created": int(time.time()), "model": request.model,
                "choices": [{"message": {"role": "assistant", "content": "连接成功！我是预算助手。"}, "finish_reason": "stop"}]
            }

        print(f"[Dify] conv={conversation_id[:8]} q={question[:80]}")

        # ===== 完整 system_prompt 构建 =====
        system_prompt = _load_system_prompt()
        system_prompt = _inject_guidance(system_prompt, question)

        # L0 元规则
        l0_path = os.path.join(BASE_DIR, "memory", "L0_meta_rules.md")
        if os.path.exists(l0_path):
            with open(l0_path, encoding="utf-8") as f:
                system_prompt = f.read() + "\n\n" + system_prompt

        # DB连接状态（强制声明，防止LLM重复connect_db）
        system_prompt = f"\n[DB状态] 达梦已连接(schema={config.DB_SCHEMA})。禁止调用connect_db。直接调run_sql。\n"
        system_prompt += "[输出格式] 展示SQL语句时直接写，不要用markdown代码块(```)。\n"

        # 进度描述规范
        progress_path = os.path.join(BASE_DIR, "memory", "progress_guide.md")
        if os.path.exists(progress_path):
            with open(progress_path, encoding="utf-8") as f:
                system_prompt += "\n" + f.read() + "\n" + system_prompt

        # 工作记忆
        wm = memory_core.load_working_memory()
        if wm.get("discoveries"):
            system_prompt += "\n[工作记忆] " + "; ".join(f"{k}={v}" for k,v in list(wm["discoveries"].items())[-5:])

        # 全局记忆
        mem_path = os.path.join(BASE_DIR, "memory", "global_mem.txt")
        if os.path.exists(mem_path):
            with open(mem_path, encoding="utf-8") as f:
                system_prompt += f"\n\n[全局记忆]\n{f.read()}"

        # 会话上下文
        session_ctx = _load_context()
        if session_ctx.get("last_table"):
            system_prompt += f"\n\n[上一轮] 表:{session_ctx.get('last_table','')} SQL:{session_ctx.get('last_sql','')[:200]}\n复用上一轮上下文。"

        # 相似历史模式
        patterns = pattern_store.search_patterns(question, limit=3)
        if patterns.get("matched", 0) > 0:
            for i, p in enumerate(patterns.get("patterns", [])):
                system_prompt += f"\n[历史模式{i+1}] 相似度{p.get('similarity',0)}% 表:{p.get('table','')} SQL:{p.get('sql','')[:150]}"

        # 追问限制
        clarify_count = raw_body.get("sys.dialogue_count", 0)
        if clarify_count >= 3:
            system_prompt += "\n\n[强制] 已追问2次，直接执行。时间→最新, 地区→全部, 项目→合计"

        # ===== 执行 =====
        client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
        client.model = config.OPENAI_MODEL

        handler = ServerHandler()
        handler.current_question = question
        tracer = QueryTracer(str(uuid.uuid4()), question)
        handler.tracer = tracer

        user_msg = f"[强制] 必须调用工具获取真实数据。禁止编造。数据库已连接正常。\n用户问题: {question}"

        if not request.stream:
            full_answer = ""
            for chunk in agent_runner_loop(client=client, system_prompt=system_prompt, user_input=user_msg,
                                           handler=handler, tools_schema=TOOLS_SCHEMA, max_turns=20, verbose=False):
                full_answer += chunk
            tracer.done(sql=handler.captured_sql or "", rows=len(handler.captured_rows or []))
            if handler.captured_sql:
                pattern_store.save_pattern(question, handler.captured_sql)
                ctx = _load_context()
                ctx["last_table"] = handler.captured_table or ""
                ctx["last_sql"] = (handler.captured_sql or "")[:300]
                ctx["last_question"] = question[:100]
                _save_context(ctx)
            return {"id": f"chatcmpl-{int(time.time())}", "object": "chat.completion", "created": int(time.time()),
                    "model": request.model, "choices": [{"message": {"role":"assistant","content":full_answer.strip()},"finish_reason":"stop"}]}

        # 流式 SSE
        async def stream_generator():
            try:
                start = {"id":f"chatcmpl-{int(time.time())}","object":"chat.completion.chunk","created":int(time.time()),
                         "model":request.model,"choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":None}]}
                yield f"data: {json.dumps(start,ensure_ascii=False)}\n\n"

                for chunk in agent_runner_loop(client=client, system_prompt=system_prompt, user_input=user_msg,
                                               handler=handler, tools_schema=TOOLS_SCHEMA, max_turns=20, verbose=False):
                    if chunk.strip():
                        delta = {"id":f"chatcmpl-{int(time.time())}","object":"chat.completion.chunk","created":int(time.time()),
                                 "model":request.model,"choices":[{"index":0,"delta":{"content":chunk},"finish_reason":None}]}
                        yield f"data: {json.dumps(delta,ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)  # 立即刷新，确保流式输出

                tracer.done(sql=handler.captured_sql or "", rows=len(handler.captured_rows or []))
                if handler.captured_sql:
                    pattern_store.save_pattern(question, handler.captured_sql)
                    ctx = _load_context()
                    ctx["last_table"] = handler.captured_table or ""
                    ctx["last_sql"] = (handler.captured_sql or "")[:300]
                    ctx["last_question"] = question[:100]
                    _save_context(ctx)

                end = {"id":f"chatcmpl-{int(time.time())}","object":"chat.completion.chunk","created":int(time.time()),
                       "model":request.model,"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
                yield f"data: {json.dumps(end,ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                traceback.print_exc()
                err = {"id":f"chatcmpl-{int(time.time())}","object":"chat.completion.chunk","created":int(time.time()),
                       "model":request.model,"choices":[{"index":0,"delta":{"content":f"\n异常: {e}"},"finish_reason":"stop"}]}
                yield f"data: {json.dumps(err,ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("server_dify:app", host=config.SERVER_HOST, port=config.SERVER_PORT, reload=False)
