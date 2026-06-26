"""
RAG 知识库检索 — 自包含模块（不依赖 Langchain (2) 项目）

embedding/rerank: HTTP API (10.32.10.160:30189)
向量存储: PostgreSQL + Vastbase FloatVector
"""

import json
import os
import requests
from typing import List, Optional


# ========== 配置（从环境变量读取） ==========
EMBEDDING_URL = os.environ.get("RAG_EMBEDDING_URL", "http://10.32.10.160:30189/v1/embeddings")
EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "/workspace/bge-m3")
RERANK_URL = os.environ.get("RAG_RERANK_URL", "http://10.32.10.160:30189/v1/rerank")
RERANK_MODEL = os.environ.get("RAG_RERANK_MODEL", "/workspace/bge-reranker-large")
DB_CONNECTION = os.environ.get("RAG_DB_CONNECTION", "postgresql+psycopg2://postgres:123456@localhost:5432/postgres")
COLLECTION_NAME = os.environ.get("RAG_COLLECTION", "parent_child_db_1024")

_rag_initialized = False
_embeddings = None
_vector_store = None


def _build_headers(api_key: str = "") -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


# ========== Embedding 服务 ==========
def _embed_texts(texts: List[str]) -> List[List[float]]:
    """调用 embedding API，兼容 OpenAI 格式"""
    try:
        payload = {"input": texts, "model": EMBEDDING_MODEL}
        resp = requests.post(EMBEDDING_URL, json=payload, headers=_build_headers(), timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if "data" in data:
            return [item["embedding"] for item in sorted(data["data"], key=lambda x: x.get("index", 0))]
        return []
    except Exception as e:
        print(f"[RAG] Embedding失败: {e}")
        return []


def _embed_query(text: str) -> List[float]:
    embs = _embed_texts([text])
    return embs[0] if embs else []


# ========== Rerank 服务 ==========
def _rerank(query: str, texts: List[str]) -> List[dict]:
    """调用 rerank API，返回排序后的 [{text, score}]"""
    if not texts:
        return []
    try:
        payload = {"query": query, "documents": texts, "model": RERANK_MODEL}
        resp = requests.post(RERANK_URL, json=payload, headers=_build_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "results" in data:
            items = sorted(data["results"], key=lambda x: x.get("relevance_score", 0), reverse=True)
            return [{"text": texts[r["index"]], "score": r.get("relevance_score", 0)}
                    for r in items if r.get("index", -1) < len(texts)]
        if "data" in data:
            items = sorted(data["data"], key=lambda x: x.get("score", 0), reverse=True)
            return [{"text": texts[r["index"]], "score": r.get("score", 0)}
                    for r in items if r.get("index", -1) < len(texts)]
        return [{"text": t, "score": 0.0} for t in texts]
    except Exception as e:
        print(f"[RAG] Rerank失败: {e}")
        return [{"text": t, "score": float(len(texts) - i)} for i, t in enumerate(texts)]


# ========== 向量检索 ==========
def _init_vector_store():
    """初始化向量存储（延迟加载）"""
    global _rag_initialized, _vector_store
    if _rag_initialized:
        return _vector_store is not None

    try:
        from sqlalchemy import create_engine, Column, Integer, Text
        from sqlalchemy.orm import declarative_base, Session
        from vastbase.sqlalchemy import FloatVector

        Base = declarative_base()

        class RagDoc(Base):
            __tablename__ = COLLECTION_NAME
            __table_args__ = {"extend_existing": True}
            id = Column(Integer, primary_key=True, autoincrement=True)
            c_document = Column(Text)
            c_embedding = Column(FloatVector(1024))
            c_metadata = Column(Text, default="{}")

        engine = create_engine(DB_CONNECTION, pool_pre_ping=True)
        _vector_store = {"engine": engine, "table": RagDoc, "Session": Session}
        _rag_initialized = True
        print("[RAG] 向量存储初始化成功")
        return True
    except ImportError as e:
        print(f"[RAG] 向量存储初始化失败(缺少vastbase模块): {e}")
        _rag_initialized = True
        return False


def _vector_search(query_embedding: List[float], k: int = 10) -> List[str]:
    """向量相似度检索，返回文档文本列表"""
    if not _init_vector_store() or not _vector_store:
        return []

    try:
        TableCls = _vector_store["table"]
        Session = _vector_store["Session"]

        with Session(_vector_store["engine"]) as session:
            emb_col = TableCls.c_embedding
            distance_expr = emb_col.cosine_distance(query_embedding)
            from sqlalchemy import text as sql_text
            rows = session.query(TableCls, distance_expr.label("_distance")) \
                .order_by(sql_text("_distance")).limit(k).all()

        docs = [row[0].c_document for row in rows if row[0].c_document]
        return docs
    except Exception as e:
        print(f"[RAG] 向量检索失败: {e}")
        return []


# ========== 对外接口 ==========
def rag_search(query: str, top_k: int = 5) -> dict:
    """
    搜索预算解读知识库: 向量粗排(k=10) → Rerank精排 → 返回top_k文档片段
    """
    # Step 1: 生成查询向量
    query_emb = _embed_query(query)
    if not query_emb:
        return {"status": "error", "message": "Embedding服务不可用，请检查网络连接"}

    # Step 2: 向量检索粗排
    docs = _vector_search(query_emb, k=10)
    if not docs:
        return {"status": "error", "message": "向量数据库无匹配结果或连接失败"}

    # Step 3: Rerank 精排
    ranked = _rerank(query, docs)
    top_docs = ranked[:top_k]

    # Step 4: 返回结果
    documents = [d["text"][:800] for d in top_docs if d.get("text")]

    return {
        "status": "ok",
        "query": query,
        "document_count": len(documents),
        "documents": documents,
        "sources": ["河北省预算解读知识库"]
    }
