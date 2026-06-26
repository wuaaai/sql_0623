"""
RAG 知识库检索 — 自包含模块

Embedding: POST http://10.32.10.160:8991/embed (本地格式)
Rerank: POST http://10.32.10.160:8991/rerank?query=xxx (本地格式)
向量存储: PostgreSQL + Vastbase FloatVector
"""

import os
import requests
from typing import List

# 配置
EMBEDDING_URL = os.environ.get("RAG_EMBEDDING_URL", "http://10.32.10.160:8991/embed")
RERANK_URL = os.environ.get("RAG_RERANK_URL", "http://10.32.10.160:8991/rerank")
DB_CONNECTION = os.environ.get("RAG_DB_CONNECTION", "postgresql+psycopg2://postgres:123456@localhost:5432/postgres")
COLLECTION_NAME = os.environ.get("RAG_COLLECTION", "parent_child_db_1024")

_rag_initialized = False
_vector_store = None


def _embed_texts(texts: List[str]) -> List[List[float]]:
    """POST /embed body=[texts] → {"embeddings": [[...], ...]}"""
    try:
        resp = requests.post(EMBEDDING_URL, json=texts, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if "embeddings" in data:
            return data["embeddings"]
        return []
    except Exception as e:
        print(f"[RAG] Embedding失败: {e}")
        return []


def _embed_query(text: str) -> List[float]:
    embs = _embed_texts([text])
    return embs[0] if embs else []


def _rerank(query: str, texts: List[str]) -> List[dict]:
    """POST /rerank?query=xxx body=[texts] → {"ranked_documents": [...], "scores": [...]}"""
    if not texts:
        return []
    try:
        resp = requests.post(RERANK_URL, params={"query": query}, json=texts, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "ranked_documents" in data and "scores" in data:
            ranked = data["ranked_documents"]
            scores = data["scores"]
            return [{"text": t, "score": float(s)} for t, s in zip(ranked, scores)]
        return [{"text": t, "score": 0.0} for t in texts]
    except Exception as e:
        print(f"[RAG] Rerank失败: {e}")
        return [{"text": t, "score": float(len(texts) - i)} for i, t in enumerate(texts)]


def _init_vector_store():
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
        print(f"[RAG] 向量存储不可用(缺少vastbase): {e}")
        _rag_initialized = True
        return False


def _vector_search(query_embedding: List[float], k: int = 10) -> List[str]:
    if not _init_vector_store() or not _vector_store:
        return []
    try:
        TableCls = _vector_store["table"]
        Session = _vector_store["Session"]
        with Session(_vector_store["engine"]) as session:
            emb_col = TableCls.c_embedding
            dist = emb_col.cosine_distance(query_embedding)
            from sqlalchemy import text as sql_text
            rows = session.query(TableCls, dist.label("_d")).order_by(sql_text("_d")).limit(k).all()
        return [r[0].c_document for r in rows if r[0].c_document]
    except Exception as e:
        print(f"[RAG] 向量检索失败: {e}")
        return []


def rag_search(query: str, top_k: int = 5) -> dict:
    """搜索知识库: 向量粗排(k=10) → Rerank精排 → 返回top_k"""
    q_emb = _embed_query(query)
    if not q_emb:
        return {"status": "error", "message": "Embedding服务不可用"}

    docs = _vector_search(q_emb, k=10)
    if not docs:
        return {"status": "error", "message": "向量库无匹配结果或连接失败"}

    ranked = _rerank(query, docs)
    top = [d["text"][:800] for d in ranked[:top_k] if d.get("text")]

    return {"status": "ok", "query": query, "document_count": len(top), "documents": top}
