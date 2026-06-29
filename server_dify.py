"""
Text-to-SQL + RAG Dify 兼容后端

提供 Dify 平台兼容的 OpenAI 格式 API:
- GET  /v1/models          凭据验证
- POST /v1/chat/completions 对话接口 (流式SSE)

参考: Langchain (2)/server.py 的 Dify 集成模式
"""

import uvicorn, os, sys, re, time, json, uuid, traceback
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from openai import OpenAI
from agent_loop import agent_runner_loop
from tools.schema import TOOLS_SCHEMA
from tools import db_connection, pattern_store
from tools.config import config
from handler import TextToSQLHandler, StepOutcome, ServerHandler

app = FastAPI(title="预算 Agent Dify API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ================= 启动初始化 =================
def _init():
    db_connection.connect_db(db_type=config.DB_TYPE, host=config.DB_HOST, port=config.DB_PORT,
                             user=config.DB_USER, password=config.DB_PASSWORD, schema=config.DB_SCHEMA)
    print(f"[Dify] DB connected: {config.DB_SCHEMA}")
    from tools.admin_db import init_db
    init_db()
    print("[Dify] Admin initialized")

_init()
_start_time = time.time()

# ================= 数据模型 (OpenAI兼容) =================
class OpenAIMessage(BaseModel):
    role: str
    content: str

class OpenAIRequest(BaseModel):
    model: str = "budget-agent"
    messages: List[OpenAIMessage]
    stream: bool = True
    user: Optional[str] = "default_user"
    region_code: Optional[str] = None

# ================= 辅助函数 =================
_REGION_CODE_PATTERN = re.compile(r"\n{2,}(\d{6,9})\s*$")

def extract_region_code(messages: list):
    """从最后一条 user 消息末尾提取地区码"""
    if not messages: return None
    for msg in reversed(messages):
        if msg.role == "user":
            match = _REGION_CODE_PATTERN.search(msg.content)
            if match:
                code = match.group(1)
                cleaned = _REGION_CODE_PATTERN.sub("", msg.content).rstrip()
                return code, cleaned
            break
    return None, None

# ================= 业务路由 =================
from server import _inject_guidance, _load_system_prompt

# ================= API =================
@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "budget-agent", "object": "model", "owned_by": "custom"},
            {"id": "text-to-sql", "object": "model", "owned_by": "custom"},
        ],
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "connected": db_connection._connection is not None, "uptime": int(time.time() - _start_time)}


@app.post("/v1/chat/completions")
async def dify_chat(request: OpenAIRequest, raw_request: Request):
    try:
        # 提取 Dify 注入的系统变量
        raw_body = await raw_request.json()
        conversation_id = raw_body.get("sys.conversation_id", str(uuid.uuid4()))
        user_id = raw_body.get("sys.user_id", None)

        # 提取地区码 + 清理消息
        region_code, cleaned_question = extract_region_code(request.messages)
        if cleaned_question:
            question = cleaned_question
        else:
            question = next((m.content for m in reversed(request.messages) if m.role == "user"), "")

        print(f"[Dify] conv={conversation_id[:8]} user={user_id} q={question[:80]}")

        # 构建 system_prompt
        client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
        client.model = config.OPENAI_MODEL

        system_prompt = _load_system_prompt()
        system_prompt = _inject_guidance(system_prompt, question)

        # L0 元规则
        l0_path = os.path.join(BASE_DIR, "memory", "L0_meta_rules.md")
        if os.path.exists(l0_path):
            with open(l0_path, encoding="utf-8") as f:
                system_prompt = f.read() + "\n\n" + system_prompt

        handler = ServerHandler()
        handler.current_question = question

        # 非流式
        if not request.stream:
            full_answer = ""
            for chunk in agent_runner_loop(client=client, system_prompt=system_prompt, user_input=question,
                                           handler=handler, tools_schema=TOOLS_SCHEMA, max_turns=20, verbose=False):
                full_answer += chunk
            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [{"message": {"role": "assistant", "content": full_answer.strip()}, "finish_reason": "stop"}]
            }

        # 流式 SSE
        async def stream_generator():
            try:
                # 起始包
                start_chunk = {
                    "id": f"chatcmpl-{int(time.time())}", "object": "chat.completion.chunk",
                    "created": int(time.time()), "model": request.model,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(start_chunk, ensure_ascii=False)}\n\n"

                for chunk in agent_runner_loop(client=client, system_prompt=system_prompt, user_input=question,
                                               handler=handler, tools_schema=TOOLS_SCHEMA, max_turns=20, verbose=False):
                    if chunk.strip():
                        delta = {
                            "id": f"chatcmpl-{int(time.time())}", "object": "chat.completion.chunk",
                            "created": int(time.time()), "model": request.model,
                            "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]
                        }
                        yield f"data: {json.dumps(delta, ensure_ascii=False)}\n\n"

                # 结束包
                end_chunk = {
                    "id": f"chatcmpl-{int(time.time())}", "object": "chat.completion.chunk",
                    "created": int(time.time()), "model": request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

                # 保存模式
                if handler.captured_sql:
                    pattern_store.save_pattern(question, handler.captured_sql)

            except Exception as e:
                print(f"[Dify] Stream error: {e}")
                traceback.print_exc()
                error_payload = {
                    "id": f"chatcmpl-{int(time.time())}", "object": "chat.completion.chunk",
                    "created": int(time.time()), "model": request.model,
                    "choices": [{"index": 0, "delta": {"content": f"\n系统异常: {e}"}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("server_dify:app", host=config.SERVER_HOST, port=config.SERVER_PORT, reload=False)
