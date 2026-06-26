"""
RAG 文档导入脚本

将 data/ 目录下的 docx 预算解读文档向量化写入 PostgreSQL 向量库。
用法: uv run python tools/rag_ingest.py
"""

import os
import sys
import json
import hashlib
import requests
from typing import List
from docx import Document as DocxDocument

# 配置
EMBEDDING_URL = os.environ.get("RAG_EMBEDDING_URL", "http://10.32.10.160:8991/embed")
DB_CONNECTION = os.environ.get("RAG_DB_CONNECTION", "postgresql+psycopg2://postgres:ROOT@127.0.0.1:5432/postgres")
COLLECTION_NAME = os.environ.get("RAG_COLLECTION", "parent_child_db_1024")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images")

os.makedirs(IMAGE_DIR, exist_ok=True)

# 区划映射
MAPPING_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Langchain (2)", "src", "agent", "db", "region_mapping.json")
region_mapping = {}
if os.path.exists(MAPPING_PATH):
    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        region_mapping = json.load(f)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量向量化"""
    resp = requests.post(EMBEDDING_URL, json=texts, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("embeddings", [])


def extract_images_from_docx(docx_path: str, doc_filename: str) -> dict:
    """提取docx中的图片，返回 {image_rId: markdown_url}"""
    try:
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        doc = DocxDocument(docx_path)
        image_map = {}
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                img_data = rel.target_part.blob
                img_hash = hashlib.md5(img_data).hexdigest()
                ext = rel.target_part.ext or ".png"
                img_name = f"{img_hash}{ext}"
                img_path = os.path.join(IMAGE_DIR, img_name)
                if not os.path.exists(img_path):
                    with open(img_path, "wb") as f:
                        f.write(img_data)
                image_map[rel.rId] = f"![{img_name}]({img_name})"
        return image_map
    except Exception as e:
        print(f"  ⚠️ 提取图片失败: {e}")
        return {}


def parse_docx(docx_path: str, region_code: str = "130000000") -> List[dict]:
    """解析docx为父子块结构"""
    filename = os.path.basename(docx_path)
    print(f"📄 处理: {filename} (region={region_code})")

    image_map = extract_images_from_docx(docx_path, filename)

    doc = DocxDocument(docx_path)
    full_text = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # 检查内嵌图片
        for run in para.runs:
            if run._element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing'):
                for rId, md_url in image_map.items():
                    if rId in str(run._element.xml):
                        text += f"\n{md_url}\n"

        full_text.append(text)

    content = "\n".join(full_text)

    # 父块: *** 分隔
    parent_blocks = content.split("***")

    chunks = []
    for pi, parent in enumerate(parent_blocks):
        parent = parent.strip()
        if not parent:
            continue

        # 子块: <--split--> 分隔
        child_parts = parent.split("<--split-->")

        for ci, child in enumerate(child_parts):
            child = child.strip()
            if not child or len(child) < 20:
                continue

            # 子块内容加上文档名前缀
            child_content = f"文档名：{filename}\n\n{child}"

            chunk = {
                "text": child_content,
                "parent_text": f"文档名：{filename}\n\n{parent}",
                "metadata": {
                    "source": filename,
                    "type": "child_chunk",
                    "recall_context": f"文档名：{filename}\n\n{parent}",
                    "chunk_id": f"{filename}_p{pi}_c{ci}",
                    "region_code": region_code,
                }
            }
            chunks.append(chunk)

    print(f"  父块: {len(parent_blocks)}, 子块: {len(chunks)}")
    return chunks


def ingest_to_db(chunks: List[dict], batch_size: int = 32):
    """批量写入向量库"""
    from sqlalchemy import create_engine, Column, Integer, Text
    from sqlalchemy.orm import declarative_base, Session
    from vastbase.sqlalchemy import FloatVector

    Base = declarative_base()

    class RagTable(Base):
        __tablename__ = COLLECTION_NAME
        __table_args__ = {"extend_existing": True}
        id = Column(Integer, primary_key=True, autoincrement=True)
        c_document = Column(Text)
        c_embedding = Column(FloatVector(1024))
        c_metadata = Column(Text, default="{}")

    engine = create_engine(DB_CONNECTION, pool_pre_ping=True)
    Base.metadata.create_all(engine, tables=[RagTable.__table__])

    total = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["text"] for c in batch]
        embeddings = embed_texts(texts)

        with Session(engine) as session:
            for chunk, emb in zip(batch, embeddings):
                row = RagTable(
                    c_document=chunk["text"],
                    c_embedding=emb,
                    c_metadata=json.dumps(chunk["metadata"], ensure_ascii=False),
                )
                session.add(row)
            session.commit()

        total += len(batch)
        print(f"  写入 {total}/{len(chunks)}")

    print(f"✅ 导入完成: {total} 条记录")


def main():
    if not os.path.exists(DATA_DIR):
        print(f"❌ data/ 目录不存在: {DATA_DIR}")
        return

    # 收集所有docx文件
    docx_files = []
    for f in sorted(os.listdir(DATA_DIR)):
        if f.endswith(".docx") and not f.startswith("~"):
            docx_files.append(os.path.join(DATA_DIR, f))

    if not docx_files:
        print("❌ 未找到docx文件")
        return

    print(f"📂 找到 {len(docx_files)} 个docx文件")

    all_chunks = []
    for docx_path in docx_files:
        filename = os.path.basename(docx_path)
        region_code = region_mapping.get(filename, "130000000")
        chunks = parse_docx(docx_path, region_code)
        all_chunks.extend(chunks)

    print(f"\n📊 总计 {len(all_chunks)} 个子块，开始写入向量库...")
    ingest_to_db(all_chunks)


if __name__ == "__main__":
    main()
