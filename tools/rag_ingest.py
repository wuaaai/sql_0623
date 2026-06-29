# -*- coding: utf-8 -*-
"""
RAG Document Ingestion Script
Reads docx from data/, splits into chunks, embeds via API, writes to PostgreSQL.
Usage: uv run python tools/rag_ingest.py
"""

import os, sys, json, hashlib, requests
from typing import List
from docx import Document as DocxDocument
from tools.config import config

EMBEDDING_URL = config.RAG_EMBEDDING_URL
DB_CONNECTION = config.RAG_DB_CONNECTION
COLLECTION_NAME = config.RAG_COLLECTION
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images")
MAPPING_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Langchain (2)", "src", "agent", "db", "region_mapping.json")

os.makedirs(IMAGE_DIR, exist_ok=True)
region_mapping = json.load(open(MAPPING_PATH, encoding="utf-8")) if os.path.exists(MAPPING_PATH) else {}


def embed_texts(texts):
    resp = requests.post(EMBEDDING_URL, json=texts, timeout=120)
    resp.raise_for_status()
    return resp.json().get("embeddings", [])


def parse_docx(docx_path, region_code="130000000"):
    filename = os.path.basename(docx_path)
    print(f"[INGEST] {filename} region={region_code}")
    doc = DocxDocument(docx_path)
    content = "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    parents = [p.strip() for p in content.split("***") if p.strip()]
    chunks = []
    for pi, parent in enumerate(parents):
        for ci, child in enumerate(p.strip() for p in parent.split("<--split-->") if p.strip()):
            if len(child) < 20: continue
            chunks.append({
                "text": f"doc: {filename}\n\n{child}",
                "parent": f"doc: {filename}\n\n{parent}",
                "meta": {"source": filename, "type": "child_chunk",
                         "recall_context": f"doc: {filename}\n\n{parent}",
                         "chunk_id": f"{filename}_p{pi}_c{ci}", "region_code": region_code}
            })
    print(f"  parents={len(parents)} children={len(chunks)}")
    return chunks


def ingest_to_db(chunks, batch_size=32):
    from sqlalchemy import create_engine, Column, Integer, Text
    from sqlalchemy.orm import declarative_base, Session
    from pgvector.sqlalchemy import Vector

    Base = declarative_base()
    class RagTable(Base):
        __tablename__ = COLLECTION_NAME
        __table_args__ = {"extend_existing": True}
        id = Column(Integer, primary_key=True, autoincrement=True)
        c_document = Column(Text)
        c_embedding = Column(Vector(1024))
        c_metadata = Column(Text, default="{}")

    engine = create_engine(DB_CONNECTION, pool_pre_ping=True)
    Base.metadata.create_all(engine, tables=[RagTable.__table__])
    total = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        embs = embed_texts([c["text"] for c in batch])
        with Session(engine) as s:
            for c, e in zip(batch, embs):
                s.add(RagTable(c_document=c["text"], c_embedding=e,
                               c_metadata=json.dumps(c["meta"], ensure_ascii=False)))
            s.commit()
        total += len(batch)
        print(f"  progress {total}/{len(chunks)}")
    print(f"[DONE] {total} records")
    return total


def main():
    if not os.path.exists(DATA_DIR):
        print(f"[ERROR] data/ not found"); return
    files = [os.path.join(DATA_DIR, f) for f in sorted(os.listdir(DATA_DIR))
             if f.endswith(".docx") and not f.startswith("~")]
    if not files:
        print("[ERROR] No docx files"); return
    print(f"[START] {len(files)} files")
    chunks = []
    for f in files:
        chunks += parse_docx(f, region_mapping.get(os.path.basename(f), "130000000"))
    print(f"\n[TOTAL] {len(chunks)} chunks")
    ingest_to_db(chunks)


if __name__ == "__main__":
    main()
