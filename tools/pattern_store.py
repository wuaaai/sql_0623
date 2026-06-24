"""
查询模式积累与复用

save_pattern: 成功查询自动保存为可复用模式
search_patterns: 检索相似历史查询模式
"""

import json
import os
import re
from datetime import datetime

PATTERNS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "query_patterns")
PATTERNS_SUBDIR = os.path.join(PATTERNS_DIR, "patterns")
INDEX_PATH = os.path.join(PATTERNS_DIR, "index.json")
STATS_PATH = os.path.join(PATTERNS_DIR, "stats.json")

os.makedirs(PATTERNS_SUBDIR, exist_ok=True)


def _load_index():
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"patterns": [], "by_budget_type": {}, "by_query_type": {}}


def _save_index(idx):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


def _extract_budget_type(question: str) -> str:
    """从用户问题中提取预算类型"""
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


def _extract_query_type(question: str, sql: str) -> str:
    """从问题和SQL推断查询类型"""
    sql_upper = sql.upper()
    if "GROUP BY" in sql_upper:
        return "聚合统计"
    if "ORDER BY" in sql_upper and "DESC" in sql_upper:
        return "排名"
    if "AVG" in sql_upper or "SUM" in sql_upper:
        return "汇总"
    if any(w in question for w in ["同比", "增长", "下降", "去年"]):
        return "同比对比"
    if any(w in question for w in ["排名", "最高", "最低", "TOP"]):
        return "排名"
    if any(w in question for w in ["趋势", "各月", "变化"]):
        return "时间趋势"
    return "精准筛选"


def _extract_table(sql: str) -> str:
    m = re.search(r'\bFROM\s+([a-zA-Z_][\w.]*)', sql, re.IGNORECASE)
    return m.group(1) if m else ""


def _extract_columns(sql: str) -> list:
    """从SELECT和FROM之间提取列名"""
    m = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    cols_str = m.group(1)
    if "*" in cols_str:
        return ["*"]
    cols = re.findall(r'([a-zA-Z_][\w.]*)', cols_str)
    return [c for c in cols if c.upper() not in ("AS", "DISTINCT", "ROUND", "NVL", "SUM", "AVG", "COUNT", "MAX", "MIN")][:10]


def save_pattern(question: str, sql: str) -> dict:
    """保存成功查询模式，自动去重"""
    if not question or not sql:
        return {"status": "error", "message": "缺少问题或SQL"}

    idx = _load_index()
    budget_type = _extract_budget_type(question)
    query_type = _extract_query_type(question, sql)
    table = _extract_table(sql)
    columns = _extract_columns(sql)

    # 检查是否与已有模式重复
    for p in idx["patterns"]:
        if p.get("sql") and p["sql"].replace(" ", "").upper() == sql.replace(" ", "").upper():
            # 相同SQL，增加使用计数
            p["use_count"] = p.get("use_count", 1) + 1
            p["last_used"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save_index(idx)
            return {"status": "ok", "merged": True, "pattern_id": p["id"]}

    # 新建模式
    pattern_id = f"p_{len(idx['patterns']) + 1:04d}"
    pattern = {
        "id": pattern_id,
        "question": question,
        "sql": sql[:500],
        "table": table,
        "columns": columns,
        "budget_type": budget_type,
        "query_type": query_type,
        "use_count": 1,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_used": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    # 保存单个模式文件
    with open(os.path.join(PATTERNS_SUBDIR, f"{pattern_id}.json"), "w", encoding="utf-8") as f:
        json.dump(pattern, f, ensure_ascii=False, indent=2)

    # 更新索引
    idx["patterns"].append({"id": pattern_id, "budget_type": budget_type, "query_type": query_type,
                            "table": table, "question": question[:80], "use_count": 1})
    idx["by_budget_type"].setdefault(budget_type, []).append(pattern_id)
    idx["by_query_type"].setdefault(query_type, []).append(pattern_id)
    _save_index(idx)

    return {"status": "ok", "merged": False, "pattern_id": pattern_id, "budget_type": budget_type}


def search_patterns(keyword: str, budget_type: str = "", limit: int = 3) -> dict:
    """检索相似历史查询模式"""
    idx = _load_index()
    if not idx["patterns"]:
        return {"status": "ok", "patterns": [], "keyword": keyword}

    scored = []
    kw_lower = keyword.lower()

    # 提取关键词：中文按字符，英文按空格
    import re as _re
    kw_chars = set(kw_lower)
    # 提取2-4字的中文词组
    kw_bigrams = set()
    for i in range(len(keyword)-1):
        chunk = keyword[i:i+2]
        if _re.search(r'[一-鿿]{2}', chunk):
            kw_bigrams.add(chunk)

    for p_info in idx["patterns"]:
        pid = p_info["id"]
        pattern_file = os.path.join(PATTERNS_SUBDIR, f"{pid}.json")
        if not os.path.exists(pattern_file):
            continue
        try:
            with open(pattern_file, "r", encoding="utf-8") as f:
                p = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        score = 0
        q = p.get("question", "")

        # 中文词组匹配（权重最高）
        q_bigrams = set()
        for i in range(len(q)-1):
            chunk = q[i:i+2]
            if _re.search(r'[一-鿿]{2}', chunk):
                q_bigrams.add(chunk)
        common_bigrams = kw_bigrams & q_bigrams
        if kw_bigrams:
            score += len(common_bigrams) / len(kw_bigrams) * 50

        # 子串匹配
        if len(kw_lower) > 3:
            for chunk_len in [4, 6, 8]:
                for i in range(0, len(keyword) - chunk_len + 1, chunk_len // 2):
                    sub = keyword[i:i+chunk_len]
                    if len(sub) >= 3 and sub in q:
                        score += 10
                        break

        # 表名匹配（同一张表+20分）
        if p.get("table") == p_info.get("table"):
            score += 20

        # 预算类型匹配
        if budget_type and p.get("budget_type") == budget_type:
            score += 25

        # 使用次数加成
        score += min(p.get("use_count", 1) * 3, 15)

        if score > 0:
            similarity = min(round(score), 95)
            p["similarity"] = similarity
            p["score"] = score
            scored.append({"pattern": p, "score": score, "similarity": similarity})

    # 排序取Top N
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top = scored[:limit]

    return {
        "status": "ok",
        "keyword": keyword,
        "total_patterns": len(idx["patterns"]),
        "matched": len(top),
        "patterns": [s["pattern"] for s in top]
    }
