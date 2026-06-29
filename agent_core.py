"""
Agent 核心类

管理 LLM 客户端、系统提示词、Handler，提供统一的运行入口
"""

import os
from openai import OpenAI
from tools.config import config

from agent_loop import agent_runner_loop
from handler import TextToSQLHandler
from tools.schema import TOOLS_SCHEMA


def _load_system_prompt() -> str:
    """加载系统提示词"""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return "你是 Text-to-SQL 助手。"


class TextToSQLAgent:
    """Text-to-SQL Agent"""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or config.OPENAI_API_KEY
        self.base_url = base_url or config.OPENAI_BASE_URL
        self.model = model or config.OPENAI_MODEL

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.client.model = self.model

        self.system_prompt = _load_system_prompt()
        self.handler = TextToSQLHandler()
        self.tools_schema = TOOLS_SCHEMA

    def run(self, user_input: str, verbose: bool = True):
        """
        运行 Agent

        Args:
            user_input: 用户输入的自然语言查询
            verbose: 是否输出过程信息

        Yields:
            过程的文本片段
        """
        yield from agent_runner_loop(
            client=self.client,
            system_prompt=self.system_prompt,
            user_input=user_input,
            handler=self.handler,
            tools_schema=self.tools_schema,
            verbose=verbose
        )
