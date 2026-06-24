"""
深度分析工具

run_subquery: 两阶段子查询——先算A再查B
calc_ratio: 占比计算——部分/整体，窗口函数
detect_anomalies: 异常检测——均值±N倍标准差
"""

from tools import db_connection as _db


def run_subquery(table: str, base_sql: str, subquery_sql: str):
    """执行带子查询的两阶段查询。先执行subquery_sql获取标量值，再将结果嵌入base_sql中{SUBQUERY}占位符后执行。"""
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    try:
        db_type = _db._conn_info["db_type"]

        # 第一阶段：执行子查询获取标量值
        if db_type == "dameng":
            cursor = _db._connection.cursor()
            cursor.execute(subquery_sql)
            row = cursor.fetchone()
            subquery_value = row[0] if row else None
        elif db_type == "sqlite":
            row = _db._connection.execute(subquery_sql).fetchone()
            subquery_value = row[0] if row else None
        elif db_type == "mysql":
            cursor = _db._connection.cursor()
            cursor.execute(subquery_sql)
            row = cursor.fetchone()
            subquery_value = list(row.values())[0] if row else None

        if subquery_value is None:
            return {"status": "error", "message": "子查询未返回结果", "subquery_sql": subquery_sql.strip()}

        # 第二阶段：嵌入子查询结果
        formatted_val = str(subquery_value) if isinstance(subquery_value, (int, float)) else f"'{subquery_value}'"
        outer_sql = base_sql.replace("{SUBQUERY}", formatted_val)

        if db_type == "dameng":
            cursor = _db._connection.cursor()
            cursor.execute(outer_sql)
            col_names = [d[0] for d in cursor.description] if cursor.description else []
            rows = [dict(zip(col_names, row)) for row in cursor.fetchall()]
        else:
            return {"status": "error", "message": "仅支持达梦数据库"}

        return {
            "status": "success",
            "sql": outer_sql.strip(),
            "subquery_sql": subquery_sql.strip(),
            "subquery_result": subquery_value,
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows
        }

    except Exception as e:
        return {"status": "error", "message": f"子查询执行失败: {str(e)}"}


def calc_ratio(table: str, value_col: str, group_col: str, filters: str = ""):
    """计算占比：每个分组的value_col占总计的百分比。使用SUM() OVER()窗口函数。"""
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    where_clause = f"WHERE {filters}" if filters and filters.strip() else ""

    sql = f"""
SELECT {group_col}, {value_col},
       ROUND({value_col} / SUM({value_col}) OVER() * 100, 2) AS RATIO_PCT
FROM {table}
{where_clause}
ORDER BY {value_col} DESC"""

    try:
        db_type = _db._conn_info["db_type"]

        if db_type == "dameng":
            cursor = _db._connection.cursor()
            cursor.execute(sql)
            col_names = [d[0] for d in cursor.description] if cursor.description else []
            rows = [dict(zip(col_names, row)) for row in cursor.fetchall()]
        elif db_type == "sqlite":
            cursor = _db._connection.execute(sql)
            rows = [dict(row) for row in cursor.fetchall()]
        elif db_type == "mysql":
            cursor = _db._connection.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()

        total_pct = sum(row.get("RATIO_PCT", 0) or 0 for row in rows)

        return {
            "status": "success",
            "sql": sql.strip(),
            "value_col": value_col,
            "group_col": group_col,
            "total_pct": round(total_pct, 2),
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows
        }

    except Exception as e:
        return {"status": "error", "message": f"占比计算失败: {str(e)}"}


def detect_anomalies(table: str, value_col: str, group_col: str,
                     filters: str = "", threshold: float = 2.0):
    """异常检测：计算均值和标准差，标记超出均值±threshold倍标准差的离群值。"""
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    where_clause = f"WHERE {filters}" if filters and filters.strip() else ""

    try:
        db_type = _db._conn_info["db_type"]

        # 第一步：计算均值和标准差
        stats_sql = f"SELECT AVG({value_col}) AS MEAN_VAL, STDDEV({value_col}) AS STDDEV_VAL FROM {table} {where_clause}"

        if db_type == "dameng":
            cursor = _db._connection.cursor()
            cursor.execute(stats_sql)
            row = cursor.fetchone()
            mean_val = float(row[0]) if row and row[0] is not None else 0
            stddev_val = float(row[1]) if row and row[1] is not None else 0
        elif db_type == "sqlite":
            row = _db._connection.execute(stats_sql).fetchone()
            mean_val = float(row[0]) if row and row[0] is not None else 0
            stddev_val = float(row[1]) if row and row[1] is not None else 0
        elif db_type == "mysql":
            cursor = _db._connection.cursor()
            cursor.execute(stats_sql)
            row = cursor.fetchone()
            mean_val = float(list(row.values())[0]) if row and list(row.values())[0] else 0
            stddev_val = float(list(row.values())[1]) if row and list(row.values())[1] else 0

        if stddev_val == 0:
            return {
                "status": "success",
                "stats": {"mean": round(mean_val, 2), "stddev": 0, "upper_bound": round(mean_val, 2), "lower_bound": round(mean_val, 2)},
                "threshold": threshold,
                "message": "标准差为0，所有值相同，无异常",
                "anomaly_count": 0, "total_count": 0, "columns": [], "rows": []
            }

        upper_bound = mean_val + threshold * stddev_val
        lower_bound = mean_val - threshold * stddev_val

        # 第二步：查询所有行并标记异常
        anomaly_sql = f"""
SELECT {group_col}, {value_col},
       CASE WHEN {value_col} > {upper_bound} THEN '偏高异常'
            WHEN {value_col} < {lower_bound} THEN '偏低异常'
            ELSE '正常' END AS ANOMALY_FLAG,
       ROUND(({value_col} - {mean_val}) / {stddev_val}, 2) AS Z_SCORE
FROM {table} {where_clause}
ORDER BY ABS({value_col} - {mean_val}) DESC"""

        if db_type == "dameng":
            cursor = _db._connection.cursor()
            cursor.execute(anomaly_sql)
            col_names = [d[0] for d in cursor.description] if cursor.description else []
            all_rows = [dict(zip(col_names, row)) for row in cursor.fetchall()]
        else:
            return {"status": "error", "message": "仅支持达梦数据库"}

        anomaly_rows = [r for r in all_rows if r.get("ANOMALY_FLAG") != "正常"]

        return {
            "status": "success",
            "sql": anomaly_sql.strip(),
            "stats": {"mean": round(mean_val, 2), "stddev": round(stddev_val, 2), "upper_bound": round(upper_bound, 2), "lower_bound": round(lower_bound, 2)},
            "threshold": threshold,
            "anomaly_count": len(anomaly_rows),
            "total_count": len(all_rows),
            "columns": list(all_rows[0].keys()) if all_rows else [],
            "rows": anomaly_rows
        }

    except Exception as e:
        return {"status": "error", "message": f"异常检测失败: {str(e)}"}
