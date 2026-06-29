"""
业务指标加载器 — 根据用户问题匹配业务指标，返回表名/列名/SQL模板
"""

import json, os

_METRICS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "business_metrics")


def _load_json(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_business_metric(budget_type: str = "", intent: str = "") -> dict:
    """根据预算类型和查询意图，返回匹配的业务指标模板"""
    index = _load_json(os.path.join(_METRICS_DIR, "index.json"))
    templates = _load_json(os.path.join(_METRICS_DIR, "templates.json"))

    files_to_load = []
    if budget_type:
        f = index.get("budget_type_mapping", {}).get(budget_type)
        if f: files_to_load.append(f)
    if intent:
        files = index.get("intent_mapping", {}).get(intent, [])
        files_to_load.extend(files)
    files_to_load = list(set(files_to_load))

    matched = []
    prefix_map = {"一般公共预算":"YBGGYS","社会保险":"SHBXJJ","国有资本":"GYZBJY","政府性基金":"ZFXJJ"}
    prefix = prefix_map.get(budget_type, "")

    for fname in files_to_load:
        data = _load_json(os.path.join(_METRICS_DIR, fname))
        for m in data.get("metrics", []):
            table_match = not prefix or prefix in m.get("table","")
            intent_match = not intent or m.get("intent") == intent or intent in m.get("variants", {})
            if table_match and intent_match:
                matched.append(m)

    return {
        "status": "ok",
        "budget_type": budget_type,
        "intent": intent,
        "matched": len(matched),
        "metrics": matched[:3],
        "templates": templates.get("templates", {})
    }
