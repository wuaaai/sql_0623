"""
查询模式积累与复用

save_pattern: 成功查询自动保存为可复用模式
search_patterns: 检索相似历史查询模式

所有模式统一存储在 query_patterns/patterns.json
"""

import json
import os
import re
from datetime import datetime

PATTERNS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "query_patterns")
PATTERNS_FILE = os.path.join(PATTERNS_DIR, "patterns.json")

os.makedirs(PATTERNS_DIR, exist_ok=True)


def _load_patterns() -> list:
    """加载所有查询模式"""
    if os.path.exists(PATTERNS_FILE):
        try:
            with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _save_patterns(patterns: list):
    """保存所有查询模式"""
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)


def _extract_budget_type(question: str) -> str:
    mapping = {
        "一般公共预算": "一般公共预算", "一般预算": "一般公共预算",
        "社保": "社会保险", "社保基金": "社会保险",
        "国有资本": "国有资本", "国资": "国有资本",
        "政府性基金": "政府性基金",
    }
    for key, val in mapping.items():
        if key in question:
            return val
    return "其他"


def _extract_table(sql: str) -> str:
    m = re.search(r'\bFROM\s+([a-zA-Z_][\w.]*)', sql, re.IGNORECASE)
    return m.group(1) if m else ""


def save_pattern(question: str, sql: str) -> dict:
    """保存成功查询模式，自动去重"""
    if not question or not sql:
        return {"status": "error", "message": "缺少问题或SQL"}

    patterns = _load_patterns()
    budget_type = _extract_budget_type(question)
    table = _extract_table(sql)

    # 检查重复（相同SQL）
    sql_clean = sql.replace(" ", "").upper()
    for p in patterns:
        if p.get("sql", "").replace(" ", "").upper() == sql_clean:
            p["use_count"] = p.get("use_count", 1) + 1
            p["last_used"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save_patterns(patterns)
            return {"status": "ok", "merged": True, "pattern_id": p["id"]}

    # 新建模式
    pattern_id = f"p_{len(patterns) + 1:04d}"
    pattern = {
        "id": pattern_id,
        "question": question,
        "sql": sql[:500],
        "table": table,
        "budget_type": budget_type,
        "use_count": 1,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_used": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    patterns.append(pattern)
    _save_patterns(patterns)

    return {"status": "ok", "merged": False, "pattern_id": pattern_id, "budget_type": budget_type}


def search_patterns(keyword: str, budget_type: str = "", limit: int = 3) -> dict:
    """检索相似历史查询模式"""
    patterns = _load_patterns()
    if not patterns:
        return {"status": "ok", "patterns": [], "keyword": keyword, "total_patterns": 0, "matched": 0}

    import re as _re

    # 提取关键词双字词组
    kw_bigrams = set()
    for i in range(len(keyword) - 1):
        chunk = keyword[i:i + 2]
        if _re.search(r'[一-鿿]{2}', chunk):
            kw_bigrams.add(chunk)

    scored = []
    for p in patterns:
        score = 0
        q = p.get("question", "")

        # 词组匹配
        q_bigrams = set()
        for i in range(len(q) - 1):
            chunk = q[i:i + 2]
            if _re.search(r'[一-鿿]{2}', chunk):
                q_bigrams.add(chunk)
        common = kw_bigrams & q_bigrams
        if kw_bigrams:
            score += len(common) / len(kw_bigrams) * 50

        # 子串匹配
        for chunk_len in [4, 6, 8]:
            for i in range(0, len(keyword) - chunk_len + 1, chunk_len // 2):
                if len(keyword[i:i + chunk_len]) >= 3 and keyword[i:i + chunk_len] in q:
                    score += 10
                    break

        # 表名匹配
        if p.get("table"):
            score += 20

        # 预算类型匹配
        if budget_type and p.get("budget_type") == budget_type:
            score += 25

        # 使用次数加成
        score += min(p.get("use_count", 1) * 3, 15)

        if score > 0:
            p["similarity"] = min(round(score), 95)
            scored.append(p)

    scored.sort(key=lambda x: x.get("similarity", 0), reverse=True)

    return {
        "status": "ok",
        "keyword": keyword,
        "total_patterns": len(patterns),
        "matched": min(len(scored), limit),
        "patterns": scored[:limit]
    }
