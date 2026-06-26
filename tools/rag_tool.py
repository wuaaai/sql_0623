"""
RAG 知识库检索工具

依赖 Langchain (2) 项目的 Rag 模块。如果环境不支持（缺少 Vastbase 等依赖），
则返回友好提示。可通过 RAG_SERVICE_URL 环境变量配置 HTTP 调用模式。
"""

import json
import os
import sys

_RAG_AVAILABLE = False


def _try_init_rag():
    """尝试初始化 RAG 检索功能"""
    global _RAG_AVAILABLE
    if _RAG_AVAILABLE:
        return True

    # 先检查是否有 HTTP 服务模式
    service_url = os.environ.get("RAG_SERVICE_URL", "")
    if service_url:
        _RAG_AVAILABLE = True
        return True

    # 尝试导入 RAG 模块（需要 Vastbase 等依赖）
    _RAG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Langchain (2)")
    _RAG_SRC = os.path.join(_RAG_DIR, "src")

    # 加载 RAG 项目的 .env
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_RAG_DIR, ".env"), override=False)
    except Exception:
        pass

    sys.path.insert(0, _RAG_DIR)
    sys.path.insert(0, _RAG_SRC)

    try:
        from src.agent.tools.my_rag_tool import _sync_search_logic
        _RAG_AVAILABLE = True
        return True
    except ImportError as e:
        print(f"[RAG] 模块导入失败(Vastbase等依赖缺失): {e}")
        return False


def rag_search(query: str, top_k: int = 5) -> dict:
    """
    搜索预算解读知识库，返回相关文档片段。
    """
    if not _try_init_rag():
        return {
            "status": "error",
            "message": "知识库服务暂不可用（缺少Vastbase等依赖）。请联系管理员启动RAG服务。"
        }

    service_url = os.environ.get("RAG_SERVICE_URL", "")
    if service_url:
        try:
            import requests
            resp = requests.post(f"{service_url}/api/rag/search",
                               json={"query": query, "top_k": top_k}, timeout=30)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": f"RAG服务调用失败: {e}"}

    try:
        from src.agent.tools.my_rag_tool import _sync_search_logic
        result_text = _sync_search_logic(query, region_code=None)

        if not result_text:
            return {"status": "ok", "documents": [], "message": "未找到相关知识库内容"}

        paragraphs = [p.strip() for p in result_text.split("\n\n") if p.strip()]
        docs = paragraphs[:top_k]

        return {
            "status": "ok",
            "query": query,
            "document_count": len(docs),
            "documents": docs,
            "sources": ["河北省预算解读知识库"]
        }
    except Exception as e:
        return {"status": "error", "message": f"知识库检索失败: {e}"}
