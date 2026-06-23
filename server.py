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

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

from openai import OpenAI
from agent_loop import agent_runner_loop
from tools.schema import TOOLS_SCHEMA
from tools import db_connection, db_query


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
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=api_key, base_url=base_url)
    client.model = model
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

    def do_run_sql(self, args: dict) -> StepOutcome:
        self.captured_sql = args.get("sql", "")
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

    # 注入连接上下文，避免 LLM 重复尝试连接
    conn = db_connection._conn_info or {}
    system_prompt += (
        f"\n\n[当前数据库连接状态]\n"
        f"数据库类型: {conn.get('db_type', '')}\n"
        f"模式: {conn.get('schema', '')}\n"
        f"数据库已连接，请直接使用 list_tables 和 run_sql 响应用户需求。"
        f"不要再调用 connect_db。"
    )

    handler = ServerHandler()

    # 收集 agent 输出
    full_answer = ""
    for chunk in agent_runner_loop(
        client=client,
        system_prompt=system_prompt,
        user_input=req.question,
        handler=handler,
        tools_schema=TOOLS_SCHEMA,
        max_turns=20,
        verbose=False
    ):
        full_answer += chunk

    return ChatResponse(
        answer=full_answer.strip(),
        sql=handler.captured_sql,
        columns=handler.captured_columns,
        rows=handler.captured_rows,
        tool_calls=[]
    )


# ==== 静态文件 ====

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)


@app.get("/")
def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


# ==== 启动 ====

def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
