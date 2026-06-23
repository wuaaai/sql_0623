"""
工具分发器 Handler

参考 GenericAgent 的 BaseHandler 模式:
dispatch(tool_name, args) → do_<tool_name>(args) → StepOutcome
"""

from dataclasses import dataclass
from typing import Any, Optional

from tools import db_connection, db_query


@dataclass
class StepOutcome:
    """工具执行结果"""
    data: Any              # 工具返回的数据
    next_prompt: Optional[str] = None  # 下一轮给LLM的提示
    should_exit: bool = False          # 是否终止对话


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
            if result["row_count"] == 0:
                return StepOutcome(
                    data=result,
                    next_prompt=f"SQL 执行成功，但查询结果为空。\n"
                                f"执行的SQL: {sql}\n"
                                f"请告知用户没有匹配的数据。"
                )
            else:
                # 将结果格式化为可读文本
                rows_display = _format_rows(result["columns"], result["rows"])
                warning = result.get("warning", "")
                return StepOutcome(
                    data=result,
                    next_prompt=f"SQL 执行成功，返回 {result['row_count']} 行数据。{warning}\n"
                                f"列: {result['columns']}\n"
                                f"数据:\n{rows_display}\n"
                                f"请用自然语言向用户展示和解释这些结果。"
                )
        else:
            return StepOutcome(
                data=result,
                next_prompt=f"SQL 执行失败: {result['message']}\n"
                            f"请检查SQL语句是否正确，或使用 list_tables 确认表名。"
            )


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
