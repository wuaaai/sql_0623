"""
工具分发器 Handler

参考 GenericAgent 的 BaseHandler 模式:
dispatch(tool_name, args) → do_<tool_name>(args) → StepOutcome
"""

from dataclasses import dataclass
from typing import Any, Optional

from tools import db_connection, db_query, db_schema, time_resolver, db_aggregation, db_cross_table, db_advanced, error_handler


@dataclass
class StepOutcome:
    """工具执行结果"""
    data: Any              # 工具返回的数据
    next_prompt: Optional[str] = None  # 下一轮给LLM的提示
    should_exit: bool = False          # 是否终止对话
    is_retry: bool = False             # 是否为错误重试（不消耗轮次）


class BaseHandler:
    """基础分发器: 将工具名映射到 do_<tool_name> 方法"""

    def dispatch(self, tool_name: str, args: dict) -> StepOutcome:
        method_name = f"do_{tool_name}"
        if hasattr(self, method_name):
            return getattr(self, method_name)(args)
        else:
            return StepOutcome(
                None,
                next_prompt=f"未知工具 {tool_name}，可用工具: connect_db, list_tables, run_sql",
                should_exit=False
            )


class TextToSQLHandler(BaseHandler):
    """Text-to-SQL 工具处理器"""

    def __init__(self):
        self.retry_count = 0

    def do_connect_db(self, args: dict) -> StepOutcome:
        result = db_connection.connect_db(
            db_type=args.get("db_type", "dameng"),
            host=args.get("host"),
            port=args.get("port"),
            user=args.get("user"),
            password=args.get("password"),
            database=args.get("database"),
            schema=args.get("schema")
        )
        return StepOutcome(
            data=result,
            next_prompt=f"连接结果: {result['message']}\n"
                        f"现在可以使用 list_tables 查看数据库中有哪些表。"
        )

    def do_list_tables(self, args: dict) -> StepOutcome:
        result = db_connection.list_tables()

        if result["status"] == "success":
            tables = result["tables"]
            total = result["table_count"]
            # 只给LLM看前20个表名，避免它自作主张"整理分类"
            preview = tables[:20]
            tables_str = ", ".join(preview)
            if total > 20:
                tables_str += f" ... 共{total}张"
            return StepOutcome(
                data=result,
                next_prompt=f"数据库中共有 {total} 张表。前20张: {tables_str}\n"
                            f"请直接列出这些表名，不要添加未经证实的说明。"
                            f"用户可能会问某张表的数据，请用 run_sql 查询。"
            )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"获取表列表失败: {result['message']}\n"
                            f"请检查数据库连接，可能需要重新 connect_db。"
            )

    def do_run_sql(self, args: dict) -> StepOutcome:
        sql = args["sql"]
        result = db_query.run_sql(sql)

        if result["status"] == "success":
            self.retry_count = 0
            if result["row_count"] == 0:
                return StepOutcome(
                    data=result,
                    next_prompt=f"SQL 执行成功，但查询结果为空。\n"
                                f"执行的SQL: {sql}\n请告知用户没有匹配的数据。"
                )
            else:
                rows_display = _format_rows(result["columns"], result["rows"])
                warning = result.get("warning", "")
                return StepOutcome(
                    data=result,
                    next_prompt=f"SQL 执行成功，返回 {result['row_count']} 行数据。{warning}\n"
                                f"列: {result['columns']}\n数据:\n{rows_display}\n"
                                f"请用自然语言向用户解释这些结果。"
                )
        else:
            self.retry_count += 1
            error_msg = result["message"]
            error_type = error_handler.classify_error(error_msg)

            if self.retry_count >= 3:
                self.retry_count = 0
                friendly = error_handler.get_friendly_msg(error_type)
                return StepOutcome(
                    data=result,
                    next_prompt=f"经过3次尝试仍无法完成查询。{friendly}\n错误: {error_msg[:200]}\n请向用户友好解释并建议简化查询。",
                    is_retry=False
                )

            table_name = args.get("table_name", "") or _extract_table_from_sql(sql)
            fix_prompt = error_handler.suggest_fix(error_type, error_msg, table_name, sql)
            tag = f"[第{self.retry_count}次自动修正]" if self.retry_count < 2 else "[最后一次自动修正]"
            return StepOutcome(
                data=result,
                next_prompt=f"{tag}\n{fix_prompt}",
                is_retry=True
            )

    def do_describe_table(self, args: dict) -> StepOutcome:
        result = db_schema.describe_table(args["table_name"])

        if result["status"] == "success":
            cols_desc_lines = []
            for c in result["columns"][:15]:  # 只展示前15列
                cols_desc_lines.append(
                    f"- {c['name']} ({c['type']}){' NULL' if c.get('nullable') else ''}"
                )
            cols_desc = "\n".join(cols_desc_lines)
            if result["column_count"] > 15:
                cols_desc += f"\n... 还有{result['column_count']-15}列，如需查看全部列请再次 describe_table"
            sample = ""
            if result.get("sample_row"):
                sample = f"\n样例: {result['sample_row']}"

            # 高亮金额列
            amount_keywords = ["JE", "YS", "TBE", "TBB", "TBP", "LJS", "SR", "ZC", "LJ_"]
            amount_cols = [c["name"] for c in result["columns"] if any(kw in c["name"].upper() for kw in amount_keywords)]
            amount_hint = ""
            if amount_cols:
                amount_hint = f"\n金额列: {', '.join(amount_cols[:8])}"

            return StepOutcome(
                data=result,
                next_prompt=f"表 {result['table_name']}（{result['column_count']}列）:\n{cols_desc}{amount_hint}{sample}\n"
                            f"直接查询。"
            )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"获取表结构失败: {result['message']}\n"
                            f"请用 list_tables 确认表名是否正确。"
            )

    def do_search_schema(self, args: dict) -> StepOutcome:
        keyword = args["keyword"]
        result = db_schema.search_schema(keyword)

        if result["status"] == "success":
            tables = result.get("matched_tables", [])
            columns = result.get("matched_columns", [])

            # 检测预算类型，提示下一步
            budget_hint = ""
            from tools.db_schema import BUDGET_TYPE_MAP
            for term, abbr in BUDGET_TYPE_MAP.items():
                if term in keyword:
                    budget_hint = f"\n[预算类型] 检测到「{term}」，对应表名前缀={abbr}"
                    break

            msg = f"搜索 '{keyword}' 的结果:{budget_hint}\n"
            if tables:
                # 兼容新旧格式: str 或 dict
                table_names = [t["name"] if isinstance(t, dict) else t for t in tables]
                msg += f"\n匹配的表 ({len(tables)}): {', '.join(table_names[:15])}"
                if len(tables) > 15:
                    msg += f" ... 还有{len(tables)-15}张"
                # 显示注释
                comments = [t for t in tables if isinstance(t, dict) and t.get("comment")]
                if comments:
                    msg += "\n表注释: " + "; ".join(
                        f"{c['name']}={c['comment']}" for c in comments[:5]
                    )
            if columns:
                msg += f"\n匹配的列 ({len(columns)}): "
                col_strs = [f"{c['table']}.{c['column']}({c['type']})" for c in columns[:10]]
                msg += ", ".join(col_strs)
                if len(columns) > 10:
                    msg += f" ... 还有{len(columns)-10}列"
            if not tables and not columns:
                msg += "\n未找到匹配，建议尝试: 一般公共预算/社保/国资/政府性基金"

            guidance = ""
            if tables:
                first_table = table_names[0] if table_names else ""
                if first_table:
                    guidance = (
                        f"\n[下一步] describe_table({first_table}) 查看结构后直接 run_sql 查询"
                    )

            return StepOutcome(
                data=result,
                next_prompt=msg + guidance
            )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"搜索失败: {result['message']}"
            )

    def do_suggest_columns(self, args: dict) -> StepOutcome:
        result = db_schema.suggest_columns(args["table_name"], args["intent"])

        if result["status"] == "success":
            suggested = result["suggested_columns"]
            variants = result.get("column_variants", {})

            msg = f"表 {result['table_name']} 针对「{result['intent']}」的推荐列:\n"
            msg += f"推荐列: {', '.join(suggested)}\n"
            if variants:
                msg += "列名变体: " + "; ".join(
                    f"{k}→{' 或 '.join(v)}" for k, v in variants.items()
                )
            return StepOutcome(
                data=result,
                next_prompt=msg + "\n请用这些列名写 SELECT 查询，不要写 SELECT *。"
            )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"获取推荐列失败: {result['message']}"
            )

    def do_resolve_time(self, args: dict) -> StepOutcome:
        result = time_resolver.resolve_time(
            expression=args.get("expression", ""),
            context_month=args.get("context_month")
        )

        if result["status"] == "success":
            return StepOutcome(
                data=result,
                next_prompt=f"时间解析结果: {result['resolved']}\n"
                            f"WHERE 条件: {result['where_clause']}\n"
                            f"数据库最新数据: {_format_ym(result.get('latest_month',''))}\n"
                            f"请在 SQL 的 WHERE 子句中使用此条件。"
            )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"时间解析失败: {result['message']}"
            )

    def do_run_aggregation(self, args: dict) -> StepOutcome:
        result = db_aggregation.run_aggregation(
            table_name=args["table_name"],
            group_by=args["group_by"],
            aggregate=args["aggregate"],
            filters=args.get("filters", ""),
            order=args.get("order", "DESC"),
            limit=args.get("limit", 20)
        )

        if result["status"] == "success":
            rows_display = _format_rows(result["columns"], result["rows"])
            return StepOutcome(
                data=result,
                next_prompt=f"聚合查询成功，返回 {result['row_count']} 行。\n"
                            f"SQL: {result.get('sql', '')}\n"
                            f"分组: {result['group_by']} | 聚合: {result['aggregate']}\n"
                            f"数据:\n{rows_display}\n"
                            f"请用自然语言向用户解释结果，标注最高/最低值。"
            )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"聚合查询失败: {result['message']}\n"
                            f"请检查表名、分组列、聚合表达式是否正确，先用 describe_table 确认。"
            )

    def do_find_relations(self, args: dict) -> StepOutcome:
        result = db_cross_table.find_relations(args["table_a"], args["table_b"])

        if result["status"] == "success":
            msg = f"表关系分析: {result['table_a']} ↔ {result['table_b']}\n"
            msg += f"关系类型: {result['relation']}\n"
            msg += f"公共列数: {result['common_count']} / 重叠度: {result['overlap_ratio']}\n"

            if result.get("join_keys"):
                keys = [k["name"] for k in result["join_keys"]]
                msg += f"关联键: {', '.join(keys)}\n"
                if result.get("join_sql_template"):
                    msg += f"JOIN模板: {result['join_sql_template']}\n"

            return StepOutcome(
                data=result,
                next_prompt=msg + "\n根据以上分析，向用户说明两表的关联方式和建议的查询方法。"
            )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"分析失败: {result['message']}"
            )

    def do_union_query(self, args: dict) -> StepOutcome:
        result = db_cross_table.union_query(
            tables=args["tables"],
            select_cols=args["select_cols"],
            group_by=args["group_by"],
            aggregate=args["aggregate"],
            filters=args.get("filters", ""),
            order=args.get("order", "DESC"),
            limit=args.get("limit", 20)
        )

        if result["status"] == "success":
            rows_display = _format_rows(result["columns"], result["rows"])
            return StepOutcome(
                data=result,
                next_prompt=f"跨表合并查询成功，合并 {result['table_count']} 张表，返回 {result['row_count']} 行。\n"
                            f"SQL: {result.get('sql', '')[:300]}\n"
                            f"数据:\n{rows_display}\n"
                            f"请用自然语言向用户解释合并后的结果。"
            )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"合并查询失败: {result['message']}\n"
                            f"请先用 find_relations 确认表结构是否适合合并。"
            )

    def do_run_subquery(self, args: dict) -> StepOutcome:
        result = db_advanced.run_subquery(
            table=args["table"],
            base_sql=args["base_sql"],
            subquery_sql=args["subquery_sql"]
        )
        if result["status"] == "success":
            rows_display = _format_rows(result["columns"], result["rows"])
            return StepOutcome(
                data=result,
                next_prompt=f"子查询完成。子查询结果={result.get('subquery_result')}，外层返回{result['row_count']}行。\n数据:\n{rows_display}\n请向用户解释哪些满足条件。"
            )
        else:
            return StepOutcome(data=result, next_prompt=f"子查询失败: {result['message']}")

    def do_calc_ratio(self, args: dict) -> StepOutcome:
        result = db_advanced.calc_ratio(
            table=args["table"], value_col=args["value_col"],
            group_col=args["group_col"], filters=args.get("filters", "")
        )
        if result["status"] == "success":
            rows_display = _format_rows(result["columns"], result["rows"])
            return StepOutcome(
                data=result,
                next_prompt=f"占比计算完成，总和={result['total_pct']}%。\n数据:\n{rows_display}\n请解释各分组占比，标出最高/最低。"
            )
        else:
            return StepOutcome(data=result, next_prompt=f"占比失败: {result['message']}")

    def do_detect_anomalies(self, args: dict) -> StepOutcome:
        result = db_advanced.detect_anomalies(
            table=args["table"], value_col=args["value_col"],
            group_col=args["group_col"], filters=args.get("filters", ""),
            threshold=args.get("threshold", 2.0)
        )
        if result["status"] == "success":
            if result.get("anomaly_count", 0) == 0:
                return StepOutcome(data=result, next_prompt=f"异常检测: 未发现异常值。均值={result.get('stats',{})}")
            rows_display = _format_rows(result["columns"], result["rows"])
            return StepOutcome(
                data=result,
                next_prompt=f"异常检测: {result['total_count']}行中发现{result['anomaly_count']}个异常(阈值±{result['threshold']}σ)。\n统计: {result.get('stats',{})}\n异常数据:\n{rows_display}\n请解释哪些是异常。"
            )
        else:
            return StepOutcome(data=result, next_prompt=f"异常检测失败: {result['message']}")


def _extract_table_from_sql(sql: str) -> str:
    """从SQL中提取表名（FROM后的第一个标识符）"""
    import re
    m = re.search(r'\bFROM\s+([a-zA-Z_][\w.]*)', sql, re.IGNORECASE)
    return m.group(1) if m else ""


def _format_ym(ym: str) -> str:
    """202501 → 2025年1月"""
    if len(ym) == 6:
        return f"{ym[:4]}年{int(ym[4:])}月"
    return ym


def _format_rows(columns: list, rows: list, max_display: int = 20) -> str:
    """将查询结果格式化为可读文本"""
    if not rows:
        return "（无数据）"

    lines = []
    # 列名行
    header = " | ".join(columns)
    lines.append(header)
    lines.append("-" * len(header))

    for row in rows[:max_display]:
        values = [str(row.get(col, "")) for col in columns]
        lines.append(" | ".join(values))

    if len(rows) > max_display:
        lines.append(f"... 还有 {len(rows) - max_display} 行未显示")

    return "\n".join(lines)
