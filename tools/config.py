"""
统一配置中心 — 唯一配置入口
所有模块从这里读取配置，不再直接调 os.environ.get
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

_env_loaded = False

def _ensure_loaded():
    global _env_loaded
    if not _env_loaded:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        load_dotenv(env_path)
        _env_loaded = True

def _get(key: str, default: str = "") -> str:
    _ensure_loaded()
    return os.environ.get(key, default)


@dataclass
class Config:
    """全局配置单例"""

    OPENAI_API_KEY: str = field(default_factory=lambda: _get("OPENAI_API_KEY"))
    OPENAI_BASE_URL: str = field(default_factory=lambda: _get("OPENAI_BASE_URL", "https://api.deepseek.com"))
    OPENAI_MODEL: str = field(default_factory=lambda: _get("OPENAI_MODEL", "deepseek-chat"))

    DB_TYPE: str = field(default_factory=lambda: _get("DB_TYPE", "dameng"))
    DB_HOST: str = field(default_factory=lambda: _get("DB_HOST", "localhost"))
    DB_PORT: int = field(default_factory=lambda: int(_get("DB_PORT", "5236")))
    DB_USER: str = field(default_factory=lambda: _get("DB_USER", "SYSDBA"))
    DB_PASSWORD: str = field(default_factory=lambda: _get("DB_PASSWORD", "SYSDBA001"))
    DB_SCHEMA: str = field(default_factory=lambda: _get("DB_SCHEMA", "RDYS_PUBLIC_TBS"))

    RAG_EMBEDDING_URL: str = field(default_factory=lambda: _get("RAG_EMBEDDING_URL", "http://10.32.10.160:8991/embed"))
    RAG_RERANK_URL: str = field(default_factory=lambda: _get("RAG_RERANK_URL", "http://10.32.10.160:8991/rerank"))
    RAG_DB_CONNECTION: str = field(default_factory=lambda: _get("RAG_DB_CONNECTION", "postgresql+psycopg2://postgres:ROOT@127.0.0.1:5432/postgres?client_encoding=utf8"))
    RAG_COLLECTION: str = field(default_factory=lambda: _get("RAG_COLLECTION", "parent_child_db_1024"))

    SERVER_HOST: str = field(default_factory=lambda: _get("SERVER_HOST", "127.0.0.1"))
    SERVER_PORT: int = field(default_factory=lambda: int(_get("SERVER_PORT", "8000")))


config = Config()
