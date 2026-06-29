"""
链路追踪日志 — 每次查询记录完整调用链
"""

import json, os, time
from datetime import datetime

TRACE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(TRACE_DIR, exist_ok=True)


class QueryTracer:
    """单次查询的追踪器"""

    def __init__(self, query_id: str, question: str):
        self.query_id = query_id
        self.question = question
        self.steps = []
        self.start_time = time.time()
        self._log("START", q=question[:80])

    def step(self, name: str, **kwargs):
        elapsed = round(time.time() - self.start_time, 2)
        entry = {"step": name, "elapsed": elapsed, **kwargs}
        self.steps.append(entry)
        # 避免 kwargs 中的 elapsed 与 _log 参数冲突
        log_kwargs = {k: v for k, v in kwargs.items() if k != "elapsed"}
        self._log(name, elapsed=f"{elapsed}s", **log_kwargs)

    def done(self, turns: int = 0, sql: str = "", rows: int = 0):
        total = round(time.time() - self.start_time, 2)
        self._log("DONE", elapsed=f"{total}s", turns=turns, rows=rows)
        self._save(turns, rows, total)

    def _log(self, step: str, **kwargs):
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items() if v)
        print(f"[TRACE {self.query_id[:8]}] {step} | {extra}")

    def _save(self, turns: int, rows: int, total: float):
        log_file = os.path.join(TRACE_DIR, f"{self.query_id[:8]}.json")
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump({
                "query_id": self.query_id,
                "question": self.question,
                "steps": self.steps,
                "turns": turns,
                "rows": rows,
                "total_seconds": total,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
