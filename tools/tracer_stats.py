"""
tracer 统计分析 — 从日志中提取性能洞察
"""

import json, os, glob
from collections import defaultdict

TRACE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def analyze_traces(limit: int = 100) -> dict:
    """分析最近N条trace日志，返回统计报告"""
    if not os.path.exists(TRACE_DIR):
        return {"total_queries": 0, "message": "无trace日志"}

    files = sorted(glob.glob(f"{TRACE_DIR}/*.json"), key=os.path.getmtime, reverse=True)[:limit]

    stats = {
        "total_queries": len(files),
        "avg_duration": 0,
        "avg_turns": 0,
        "tool_frequency": defaultdict(int),
        "tool_avg_time": defaultdict(list),
        "slowest_queries": [],
        "errors": 0
    }

    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            total = data.get("total_seconds", 0)
            turns = data.get("turns", 0)
            stats["avg_duration"] += total
            stats["avg_turns"] += turns

            for step in data.get("steps", []):
                name = step.get("step", "")
                elapsed = step.get("elapsed", 0)
                if isinstance(elapsed, str):
                    elapsed = float(elapsed.replace("s", ""))
                stats["tool_frequency"][name] += 1
                stats["tool_avg_time"][name].append(elapsed)

            if total > 10:
                stats["slowest_queries"].append({
                    "id": data.get("query_id", "")[:8],
                    "question": data.get("question", "")[:80],
                    "duration": total,
                    "turns": turns
                })
        except Exception:
            stats["errors"] += 1

    if len(files) > 0:
        stats["avg_duration"] = round(stats["avg_duration"] / len(files), 2)
        stats["avg_turns"] = round(stats["avg_turns"] / len(files), 1)

    tool_avg = {}
    for name, times in stats["tool_avg_time"].items():
        tool_avg[name] = round(sum(times) / len(times), 2)
    stats["tool_avg"] = dict(sorted(tool_avg.items(), key=lambda x: x[1], reverse=True))
    stats["tool_freq_rank"] = dict(sorted(stats["tool_frequency"].items(), key=lambda x: x[1], reverse=True))

    return stats
