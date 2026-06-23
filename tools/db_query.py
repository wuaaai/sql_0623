"""
SQL 查询执行工具

阶段1: run_sql (仅SELECT)
支持: 达梦(Dameng), MySQL, SQLite
"""

from tools import db_connection as _db


# 禁止的SQL关键词，防止写操作
_FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "REPLACE", "GRANT", "REVOKE"
]


def run_sql(sql: str):
    """执行 SELECT 查询，返回格式化结果"""

    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库，请先使用 connect_db"}

    # 安全检查：禁止写操作
    sql_upper = sql.strip().upper()
    for kw in _FORBIDDEN_KEYWORDS:
        if sql_upper.startswith(kw) or f" {kw} " in sql_upper:
            return {
                "status": "error",
                "message": f"禁止执行写操作 ({kw})。run_sql 仅支持 SELECT 查询。"
            }

    try:
        db_type = _db._conn_info["db_type"]

        if db_type == "sqlite":
            cursor = _db._connection.execute(sql)
            rows = [dict(row) for row in cursor.fetchall()]

        elif db_type == "dameng":
            cursor = _db._connection.cursor()
            cursor.execute(sql)
            col_names = [d[0] for d in cursor.description] if cursor.description else []
            rows = [dict(zip(col_names, row)) for row in cursor.fetchall()]

        elif db_type == "mysql":
            cursor = _db._connection.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()

        # 格式化输出
        if not rows:
            return {
                "status": "success",
                "row_count": 0,
                "columns": [],
                "rows": [],
                "message": "查询结果为空"
            }

        columns = list(rows[0].keys())
        result_rows = rows[:50]
        truncated = len(rows) > 50

        result = {
            "status": "success",
            "row_count": len(rows),
            "columns": columns,
            "rows": result_rows
        }

        if truncated:
            result["warning"] = f"结果超过50行，仅显示前50行（共{len(rows)}行）"

        return result

    except Exception as e:
        return {"status": "error", "message": f"SQL执行失败: {str(e)}"}
