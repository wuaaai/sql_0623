"""
业务层自动反哺 — 分析 tracer 日志，输出业务层优化建议

独立模块，不依赖 server 运行。
用法: uv run python tools/business_feedback.py
"""

import json, os, glob
from collections import defaultdict, Counter
from datetime import datetime

TRACE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
BUSINESS_RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "business_rules.json")
METRICS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "business_metrics")
SKILLS_INDEX_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "skills_index.json")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "reports")


class BusinessFeedback:
    """分析 tracer 日志，生成业务层优化报告"""

    def __init__(self):
        self.traces = self._load_traces()
        self.rules = self._load_json(BUSINESS_RULES_PATH)
        self.metrics = self._load_metrics()
        self.skills = self._load_json(SKILLS_INDEX_PATH)

    def _load_traces(self):
        files = sorted(glob.glob(f"{TRACE_DIR}/*.json"), key=os.path.getmtime, reverse=True)
        traces = []
        for f in files:
            try:
                with open(f, encoding="utf-8") as fp:
                    traces.append(json.load(fp))
            except Exception:
                pass
        return traces

    def _load_json(self, path):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_metrics(self):
        metrics = {"total_metrics": 0, "coverage": defaultdict(set)}
        # 文件名→中文名映射
        name_map = {
            "general_public": "一般公共预算", "social_insurance": "社会保险",
            "state_capital": "国有资本", "gov_fund": "政府性基金"
        }
        for f in os.listdir(METRICS_DIR):
            if f.endswith(".json") and f != "index.json" and f != "templates.json":
                data = self._load_json(os.path.join(METRICS_DIR, f))
                budget_name = name_map.get(f.replace(".json", ""), f.replace(".json", ""))
                for m in data.get("metrics", []):
                    metrics["total_metrics"] += 1
                    # 记录这个指标的直接 intent
                    metrics["coverage"][m.get("intent", "")].add(budget_name)
                    # 记录变体覆盖的 intent
                    for v_name in m.get("variants", {}):
                        for intent_name, info in self.rules.get("column_patterns", {}).items():
                            if v_name == intent_name or any(kw in v_name for kw in info.get("keywords", [])):
                                metrics["coverage"][intent_name].add(budget_name)
        return metrics

    # ===== 分析1: 未匹配的查询 =====
    def unmatched_queries(self) -> list:
        """找出 tracer 中有 explore 步骤但没有业务指标匹配的查询"""
        unmatched = []
        for t in self.traces:
            steps = [s["step"] for s in t.get("steps", [])]
            has_explore = any(s in ("search_schema", "describe_table") for s in steps)
            has_sql = any(s == "run_sql" for s in steps)
            q = t.get("question", "")
            # 检测是否走了探索路径（说明没命中强制执行）
            if has_explore and has_sql:
                budget = self._detect_budget(q)
                intent = self._detect_intent(q)
                if not budget or not intent:
                    unmatched.append({
                        "question": q[:100],
                        "steps": len(steps),
                        "duration": t.get("total_seconds", 0),
                        "missing": "budget_type" if not budget else "intent",
                        "suggested_keywords": self._extract_keywords(q)
                    })
        return unmatched[:10]

    def _detect_budget(self, q):
        for name, info in self.rules.get("budget_types", {}).items():
            if name in q: return name
            for alias in info.get("aliases", []):
                if alias in q: return name
        return ""

    def _detect_intent(self, q):
        for name, info in self.rules.get("column_patterns", {}).items():
            for kw in info.get("keywords", []):
                if kw in q: return name
        return ""

    def _extract_keywords(self, q):
        """从问题中提取关键词，用于建议添加到 column_patterns 的 keywords"""
        existing = set()
        for info in self.rules.get("column_patterns", {}).values():
            for kw in info.get("keywords", []):
                existing.add(kw)
        # 简单提取: 2-4字的中文词组
        import re
        words = re.findall(r'[一-鿿]{2,4}', q)
        return [w for w in words if w not in existing][:5]

    # ===== 分析2: 高频查询模式 =====
    def frequent_patterns(self) -> list:
        """统计最常见的查询类型组合"""
        patterns = Counter()
        for t in self.traces:
            q = t.get("question", "")
            budget = self._detect_budget(q) or "未知"
            intent = self._detect_intent(q) or "未识别"
            patterns[f"{budget}+{intent}"] += 1
        return patterns.most_common(10)

    # ===== 分析3: 耗时分析 =====
    def slow_queries(self) -> list:
        """找出慢查询及瓶颈步骤"""
        slow = []
        for t in self.traces:
            total = t.get("total_seconds", 0)
            if total > 15:
                # 找最慢的步骤
                slowest_step = ("", 0)
                for s in t.get("steps", []):
                    elapsed = s.get("elapsed", 0)
                    if isinstance(elapsed, str):
                        elapsed = float(elapsed.replace("s", ""))
                    if elapsed > slowest_step[1]:
                        slowest_step = (s.get("step", ""), elapsed)
                slow.append({
                    "question": t.get("question", "")[:80],
                    "duration": total,
                    "turns": t.get("turns", 0),
                    "bottleneck": slowest_step[0],
                    "bottleneck_time": slowest_step[1]
                })
        return sorted(slow, key=lambda x: x["duration"], reverse=True)[:10]

    # ===== 分析4: 工具使用统计 =====
    def tool_usage(self) -> dict:
        """统计工具调用频率和平均耗时"""
        freq = Counter()
        times = defaultdict(list)
        for t in self.traces:
            for s in t.get("steps", []):
                name = s.get("step", "")
                elapsed = s.get("elapsed", 0)
                if isinstance(elapsed, str):
                    elapsed = float(elapsed.replace("s", ""))
                freq[name] += 1
                times[name].append(elapsed)
        result = {}
        for name in freq:
            result[name] = {
                "count": freq[name],
                "avg_time": round(sum(times[name]) / len(times[name]), 2),
                "max_time": round(max(times[name]), 2)
            }
        return dict(sorted(result.items(), key=lambda x: x[1]["count"], reverse=True))

    # ===== 分析5: 指标覆盖缺口 =====
    def coverage_gaps(self) -> list:
        gaps = []
        for intent_name, info in self.rules.get("column_patterns", {}).items():
            covered = self.metrics.get("coverage", {}).get(intent_name, set())
            all_budgets = {"一般公共预算", "社会保险", "国有资本", "政府性基金"}
            missing = [b for b in all_budgets if b not in covered]
            if missing:
                gaps.append({
                    "intent": intent_name,
                    "covered": list(covered),
                    "missing": missing
                })
        return gaps

    # ===== 生成完整报告 =====
    def generate_report(self) -> dict:
        return {
            "generated_at": datetime.now().isoformat(),
            "total_queries_analyzed": len(self.traces),
            "total_metrics": self.metrics["total_metrics"],
            "unmatched_queries": self.unmatched_queries(),
            "frequent_patterns": self.frequent_patterns(),
            "slow_queries": self.slow_queries(),
            "tool_usage": self.tool_usage(),
            "coverage_gaps": self.coverage_gaps(),
            "auto_suggestions": self._generate_suggestions()
        }

    def _generate_suggestions(self) -> list:
        """自动生成优化建议"""
        suggestions = []

        # 1. 覆盖缺口
        for gap in self.coverage_gaps():
            suggestions.append({
                "type": "add_metric",
                "priority": "high",
                "action": f"为 {', '.join(gap['missing'])} 添加 {gap['intent']} 指标",
                "detail": f"当前覆盖: {', '.join(gap['covered']) if gap['covered'] else '无'}, 缺失: {', '.join(gap['missing'])}"
            })

        # 2. 未匹配查询 → 建议加关键词
        for uq in self.unmatched_queries()[:3]:
            if uq["suggested_keywords"]:
                suggestions.append({
                    "type": "add_keyword",
                    "priority": "medium",
                    "action": f"将 '{uq['suggested_keywords'][0]}' 加入 column_patterns 关键词",
                    "detail": f"问题'{uq['question'][:50]}'未匹配，关键词候选: {uq['suggested_keywords'][:3]}"
                })

        # 3. 高频模式 → 建议提升优先级
        for pattern, count in self.frequent_patterns()[:3]:
            if count >= 3 and "未识别" not in pattern:
                suggestions.append({
                    "type": "optimize",
                    "priority": "low",
                    "action": f"高频查询模式 '{pattern}' ({count}次)，可预加载指标到缓存",
                    "detail": f"已将 '{pattern}' 标记为高频模式"
                })

        # 4. 瓶颈工具
        usage = self.tool_usage()
        for tool, stats in usage.items():
            if stats["count"] > 5 and stats["avg_time"] > 2:
                suggestions.append({
                    "type": "optimize",
                    "priority": "medium",
                    "action": f"工具 '{tool}' 平均耗时 {stats['avg_time']}s (调用{stats['count']}次)，考虑优化",
                    "detail": f"可以考虑缓存或预处理来加速"
                })

        return suggestions[:10]

    def save_report(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        report = self.generate_report()
        filename = f"feedback_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return path


if __name__ == "__main__":
    fb = BusinessFeedback()
    path = fb.save_report()
    print(f"报告已生成: {path}")
    print(f"分析查询数: {fb.traces.__len__()}")
    print(f"指标总数: {fb.metrics['total_metrics']}")
    print(f"覆盖缺口: {len(fb.coverage_gaps())} 处")
    print(f"未匹配查询: {len(fb.unmatched_queries())} 条")
    print(f"慢查询: {len(fb.slow_queries())} 条")
    print(f"自动建议: {len(fb._generate_suggestions())} 条")
