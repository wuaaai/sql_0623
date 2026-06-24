"""
跨表查询工具

find_relations: 分析两表公共列，发现关联关系
union_query: 多张同构表 UNION ALL 合并后聚合
"""

from tools import db_connection as _db


def find_relations(table_a: str, table_b: str):
    """分析两表的公共列，建议关联方式"""
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    try:
        from tools.db_schema import describe_table
        desc_a = describe_table(table_a)
        desc_b = describe_table(table_b)

        if desc_a["status"] != "success":
            return {"status": "error", "message": f"表 {table_a} 不存在或无法访问"}
        if desc_b["status"] != "success":
            return {"status": "error", "message": f"表 {table_b} 不存在或无法访问"}

        cols_a = {c["name"]: c["type"] for c in desc_a["columns"]}
        cols_b = {c["name"]: c["type"] for c in desc_b["columns"]}

        common = []
        only_a = []
        only_b = []

        for name in cols_a:
            if name in cols_b:
                common.append({"name": name, "type_a": cols_a[name], "type_b": cols_b[name]})
            else:
                only_a.append(name)

        for name in cols_b:
            if name not in cols_a:
                only_b.append(name)

        # 判断关联关系级别
        # 编码列(_CODE)是强关联键
        join_keys = []
        other_common = []
        for c in common:
            if c["name"].endswith("_CODE") or c["name"].endswith("_ID"):
                join_keys.append(c)
            else:
                other_common.append(c)

        overlap_ratio = len(common) / max(len(cols_a), len(cols_b)) if max(len(cols_a), len(cols_b)) > 0 else 0

        if overlap_ratio > 0.7 and len(join_keys) > 0:
            relation = "同构表(可UNION ALL合并)"
        elif len(join_keys) > 0:
            relation = "可通过编码列JOIN关联"
        elif len(common) > 3:
            relation = "有关联键但不确定关联方式"
        else:
            relation = "结构差异大，建议分别查询后对比"

        # 生成 JOIN SQL 模板
        join_sql = ""
        if join_keys:
            key = join_keys[0]["name"]
            join_sql = f"SELECT * FROM {table_a} a JOIN {table_b} b ON a.{key} = b.{key}"

        return {
            "status": "success",
            "table_a": table_a,
            "table_b": table_b,
            "col_count_a": len(cols_a),
            "col_count_b": len(cols_b),
            "common_count": len(common),
            "overlap_ratio": round(overlap_ratio, 2),
            "relation": relation,
            "join_keys": join_keys,
            "common_columns": common[:10],
            "only_in_a": only_a[:10],
            "only_in_b": only_b[:10],
            "join_sql_template": join_sql
        }

    except Exception as e:
        return {"status": "error", "message": f"分析表关系失败: {str(e)}"}


def union_query(tables: str, select_cols: str, group_by: str, aggregate: str,
                filters: str = "", order: str = "DESC", limit: int = 20):
    """
    对多张同构表执行 UNION ALL 合并后聚合查询。

    Args:
        tables: 逗号分隔的表名，如 "table1, table2, table3"
        select_cols: 要选择的列，如 "RG_NAME"
        group_by: 分组列
        aggregate: 聚合表达式，如 "SUM(BYS_JE)"
        filters: WHERE 条件(不含ROWNUM)
        order: DESC/ASC
        limit: 返回行数
    """
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    table_list = [t.strip() for t in tables.split(",") if t.strip()]
    if len(table_list) < 2:
        return {"status": "error", "message": "至少需要2张表进行合并"}

    try:
        alias = "TOTAL"
        import re
        m = re.match(r'(SUM|AVG|COUNT|MAX|MIN)\s*\(\s*(\w+)\s*\)', aggregate, re.IGNORECASE)
        if m:
            alias = m.group(1).upper() + "_VAL"

        # 构建 UNION ALL 子查询
        union_parts = []
        for t in table_list:
            part = f"SELECT {select_cols}, {aggregate} as {alias} FROM {t}"
            if filters.strip():
                part += f" WHERE {filters}"
            union_parts.append(part)

        inner_sql = "\nUNION ALL\n".join(union_parts)

        db_type = _db._conn_info["db_type"]

        if db_type == "dameng":
            sql = f"""
SELECT * FROM (
  SELECT {select_cols}, SUM({alias}) as {alias}
  FROM (
    {inner_sql}
  )
  GROUP BY {group_by}
  ORDER BY {alias} {order}
) WHERE ROWNUM <= {limit}"""
        else:
            sql = f"""
SELECT {select_cols}, SUM({alias}) as {alias}
FROM (
  {inner_sql}
)
GROUP BY {group_by}
ORDER BY {alias} {order}
LIMIT {limit}"""

        cursor = _db._connection.cursor()
        cursor.execute(sql)
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        rows = [dict(zip(col_names, row)) for row in cursor.fetchall()]

        return {
            "status": "success",
            "sql": sql.strip(),
            "tables": table_list,
            "table_count": len(table_list),
            "group_by": group_by,
            "aggregate": aggregate,
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows[:limit]
        }

    except Exception as e:
        return {"status": "error", "message": f"UNION查询失败: {str(e)}"}
