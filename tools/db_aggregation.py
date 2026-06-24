"""
聚合查询工具

run_aggregation: 封装 GROUP BY + 聚合函数 + ORDER BY + ROWNUM 的完整逻辑。
LLM 只需指定分组列和聚合方式，工具自动生成正确的达梦 SQL。
"""

from tools import db_connection as _db


def run_aggregation(table_name: str, group_by: str, aggregate: str,
                    filters: str = "", order: str = "DESC", limit: int = 20):
    """
    执行聚合查询。

    Args:
        table_name: 表名
        group_by: 分组列名，如 RG_NAME, YEAR_MONTH, XM_NAME
        aggregate: 聚合表达式，如 "SUM(BYS_JE)", "AVG(BYS_TBB)", "COUNT(*)"
        filters: 额外的 WHERE 条件（不含 ROWNUM），如 "XM_NAME LIKE '%合计%' AND YEAR_MONTH = '202604'"
        order: 排序方向，DESC(默认) 或 ASC
        limit: 返回行数限制，默认20

    Returns:
        {"status": "success", "sql": "生成的SQL", "columns": [...], "rows": [...], "row_count": N}
    """
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    # 构建 WHERE 子句
    where_clause = ""
    if filters and filters.strip():
        where_clause = f"WHERE {filters}"

    # 构建 SELECT 列表
    alias = _agg_alias(aggregate)
    select_list = f"{group_by}, {aggregate} as {alias}"

    # 生成达梦兼容的聚合 SQL
    # ORDER BY 必须在子查询中（因为 ROWNUM 先于 ORDER BY 执行）
    if order.upper() in ("DESC", "ASC"):
        sql = f"""
SELECT * FROM (
  SELECT {select_list}
  FROM {table_name}
  {where_clause}
  GROUP BY {group_by}
  ORDER BY {alias} {order}
) WHERE ROWNUM <= {limit}"""
    else:
        # 不排序的情况
        sql = f"""
SELECT {select_list}
FROM {table_name}
{where_clause}
GROUP BY {group_by}
AND ROWNUM <= {limit}"""

    try:
        db_type = _db._conn_info["db_type"]

        if db_type == "dameng":
            cursor = _db._connection.cursor()
            cursor.execute(sql)
            col_names = [d[0] for d in cursor.description] if cursor.description else []
            rows = [dict(zip(col_names, row)) for row in cursor.fetchall()]

        elif db_type == "sqlite":
            # SQLite 用 LIMIT 而非 ROWNUM
            sql_lite = sql.replace(f"WHERE ROWNUM <= {limit}", "")
            sql_lite = sql_lite.replace(f"AND ROWNUM <= {limit}", "")
            if "ORDER BY" in sql_lite:
                # 重构为 SQLite 格式
                sql_lite = f"""
SELECT {select_list}
FROM {table_name}
{where_clause}
GROUP BY {group_by}
ORDER BY {alias} {order}
LIMIT {limit}"""
            cursor = _db._connection.execute(sql_lite)
            rows = [dict(row) for row in cursor.fetchall()]

        elif db_type == "mysql":
            # MySQL 用 LIMIT
            sql_mysql = sql.replace(f"WHERE ROWNUM <= {limit}", "")
            sql_mysql = sql_mysql.replace(f"AND ROWNUM <= {limit}", "")
            if "ORDER BY" in sql_mysql:
                sql_mysql = f"""
SELECT {select_list}
FROM {table_name}
{where_clause}
GROUP BY {group_by}
ORDER BY {alias} {order}
LIMIT {limit}"""
            cursor = _db._connection.cursor()
            cursor.execute(sql_mysql)
            rows = cursor.fetchall()

        return {
            "status": "success",
            "sql": sql.strip(),
            "group_by": group_by,
            "aggregate": aggregate,
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows[:limit]
        }

    except Exception as e:
        return {"status": "error", "message": f"聚合查询失败: {str(e)}"}


def _agg_alias(aggregate: str) -> str:
    """从聚合表达式提取别名，如 SUM(BYS_JE)→TOTAL, AVG(BYS_TBB)→AVG_VAL"""
    import re
    m = re.match(r'(SUM|AVG|COUNT|MAX|MIN)\s*\(\s*(\w+)\s*\)', aggregate, re.IGNORECASE)
    if m:
        func_name = m.group(1).upper()
        col = m.group(2)
        alias_map = {"SUM": "TOTAL", "AVG": "AVG_VAL", "COUNT": "CNT", "MAX": "MAX_VAL", "MIN": "MIN_VAL"}
        return alias_map.get(func_name, "RESULT")
    return "RESULT"
