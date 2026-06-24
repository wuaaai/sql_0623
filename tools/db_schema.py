"""
Schema 探索工具

describe_table: 查看表结构（列名、类型）+ 样例数据
search_schema: 按关键词搜索表和列名（支持预算类型中文→英文自动扩展）
suggest_columns: 根据用户意图智能推荐列名
"""

from tools import db_connection as _db

# 预算类型→英文缩写映射，用于 search_schema 自动扩展
BUDGET_TYPE_MAP = {
    "一般公共预算": "YBGGYS",
    "一般预算": "YBGGYS",
    "公共预算": "YBGGYS",
    "社会保险": "SHBXJJ",
    "社保基金": "SHBXJJ",
    "社保": "SHBXJJ",
    "国有资本": "GYZBJY",
    "国资预算": "GYZBJY",
    "国资": "GYZBJY",
    "政府性基金": "ZFXJJ",
    "政府基金": "ZFXJJ",
}

# 用户意图→推荐列名模式
INTENT_COLUMN_PATTERNS = {
    "完成情况": ["RG_NAME", "YEAR_MONTH", "XM_NAME", "YSS", "BYS_JE", "BY_JE", "BYLJS_JE"],
    "同比": ["BYS_JE", "BY_JE", "BYS_SNTYS", "BY_SNTYS", "BYS_TBE", "BY_TBE", "BYS_TBB", "BY_TBBFS"],
    "排名": ["RG_NAME", "YEAR_MONTH", "XM_NAME", "BYS_JE", "BY_JE", "BYS_TBB", "BY_TBBFS"],
    "预算执行": ["RG_NAME", "YSS", "BYS_JE", "BY_JE", "BYLJS_JE"],
}


def _find_budget_abbr(keyword: str) -> str:
    """如果关键词包含预算类型术语，返回英文缩写"""
    for term, abbr in BUDGET_TYPE_MAP.items():
        if term in keyword:
            return abbr
    return None


def describe_table(table_name: str):
    """查看表结构：列名、类型、是否可空，并附带一行样例数据"""
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    try:
        db_type = _db._conn_info["db_type"]
        columns = []
        sample_row = None

        if db_type == "dameng":
            schema = _db._conn_info.get("schema", "")
            cursor = _db._connection.cursor()

            if schema:
                cursor.execute(f"""
                    SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_DEFAULT
                    FROM ALL_TAB_COLUMNS
                    WHERE OWNER = '{schema.upper()}' AND TABLE_NAME = '{table_name.upper()}'
                    ORDER BY COLUMN_ID
                """)
            else:
                cursor.execute(f"""
                    SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_DEFAULT
                    FROM USER_TAB_COLUMNS
                    WHERE TABLE_NAME = '{table_name.upper()}'
                    ORDER BY COLUMN_ID
                """)

            for row in cursor.fetchall():
                columns.append({
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == 'Y' if row[2] else None,
                    "default": str(row[3]) if row[3] else None
                })

            try:
                cursor.execute(f"SELECT * FROM {table_name} WHERE ROWNUM <= 1")
                col_names = [d[0] for d in cursor.description]
                row = cursor.fetchone()
                if row:
                    sample_row = dict(zip(col_names, [str(v) if v is not None else None for v in row]))
            except Exception:
                sample_row = None

        elif db_type == "mysql":
            cursor = _db._connection.cursor()
            cursor.execute(f"DESCRIBE {table_name}")
            for row in cursor.fetchall():
                columns.append({
                    "name": row.get("Field", ""),
                    "type": row.get("Type", ""),
                    "nullable": row.get("Null", "YES") == "YES",
                    "default": row.get("Default")
                })
            try:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
                sample_row = cursor.fetchone()
            except Exception:
                sample_row = None

        elif db_type == "sqlite":
            cursor = _db._connection.execute(f"PRAGMA table_info({table_name})")
            for row in cursor.fetchall():
                columns.append({
                    "name": row[1],
                    "type": row[2],
                    "nullable": not row[3],
                    "default": row[4]
                })
            try:
                row = _db._connection.execute(f"SELECT * FROM {table_name} LIMIT 1").fetchone()
                if row:
                    sample_row = dict(row)
            except Exception:
                sample_row = None

        return {
            "status": "success",
            "table_name": table_name,
            "column_count": len(columns),
            "columns": columns,
            "sample_row": sample_row
        }

    except Exception as e:
        return {"status": "error", "message": f"获取表结构失败: {str(e)}"}


def search_schema(keyword: str):
    """按关键词搜索表和列名。对于预算类型术语会自动扩展为英文缩写搜索。"""
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    try:
        db_type = _db._conn_info["db_type"]
        matched_tables = []
        matched_columns = []

        if db_type == "dameng":
            schema = _db._conn_info.get("schema", "")
            cursor = _db._connection.cursor()
            kw = keyword.upper()

            # 构建搜索关键词列表：原始关键词 + 预算类型英文缩写
            search_keys = [keyword]
            abbr = _find_budget_abbr(keyword)
            if abbr:
                search_keys.append(abbr)

            table_results = {}  # name -> comment

            if schema:
                for sk in search_keys:
                    sk_upper = sk.upper()

                    # 1. 搜索表名
                    cursor.execute(f"""
                        SELECT TABLE_NAME FROM ALL_TABLES
                        WHERE OWNER = '{schema.upper()}'
                          AND TABLE_NAME LIKE '%{sk_upper}%'
                        ORDER BY TABLE_NAME
                    """)
                    for row in cursor.fetchall():
                        if row[0] not in table_results:
                            table_results[row[0]] = None

                    # 2. 搜索表注释
                    try:
                        cursor.execute(f"""
                            SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS
                            WHERE OWNER = '{schema.upper()}'
                              AND COMMENTS IS NOT NULL
                              AND COMMENTS LIKE '%{sk}%'
                            ORDER BY TABLE_NAME
                        """)
                        for row in cursor.fetchall():
                            if row[0] not in table_results:
                                table_results[row[0]] = row[1]
                            elif table_results[row[0]] is None and row[1]:
                                table_results[row[0]] = row[1]
                    except Exception:
                        pass

                    # 3. 搜索列名
                    cursor.execute(f"""
                        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
                        FROM ALL_TAB_COLUMNS
                        WHERE OWNER = '{schema.upper()}'
                          AND COLUMN_NAME LIKE '%{sk_upper}%'
                        ORDER BY TABLE_NAME, COLUMN_ID
                    """)
                    for row in cursor.fetchall():
                        matched_columns.append({
                            "table": row[0],
                            "column": row[1],
                            "type": row[2]
                        })

                    # 4. 搜索列注释
                    try:
                        cursor.execute(f"""
                            SELECT TABLE_NAME, COLUMN_NAME, COMMENTS
                            FROM ALL_COL_COMMENTS
                            WHERE OWNER = '{schema.upper()}'
                              AND COMMENTS IS NOT NULL
                              AND COMMENTS LIKE '%{sk}%'
                            ORDER BY TABLE_NAME, COLUMN_NAME
                        """)
                        for row in cursor.fetchall():
                            matched_columns.append({
                                "table": row[0],
                                "column": row[1],
                                "type": row[2] or ""
                            })
                    except Exception:
                        pass

                # 去重列结果
                seen = set()
                unique_cols = []
                for c in matched_columns:
                    key = (c["table"], c["column"])
                    if key not in seen:
                        seen.add(key)
                        unique_cols.append(c)
                matched_columns = unique_cols

                # 转为 dict 列表，带注释
                matched_tables = [
                    {"name": name, "comment": comment}
                    for name, comment in table_results.items()
                ]

            else:
                # 无 schema 时用 user_ 视图
                for sk in search_keys:
                    sk_upper = sk.upper()
                    cursor.execute(f"""
                        SELECT TABLE_NAME FROM USER_TABLES
                        WHERE TABLE_NAME LIKE '%{sk_upper}%'
                        ORDER BY TABLE_NAME
                    """)
                    for row in cursor.fetchall():
                        if row[0] not in table_results:
                            table_results[row[0]] = None

                cursor.execute(f"""
                    SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
                    FROM USER_TAB_COLUMNS
                    WHERE COLUMN_NAME LIKE '%{keyword.upper()}%'
                    ORDER BY TABLE_NAME, COLUMN_ID
                """)
                for row in cursor.fetchall():
                    matched_columns.append({
                        "table": row[0],
                        "column": row[1],
                        "type": row[2]
                    })

                matched_tables = [
                    {"name": name, "comment": comment}
                    for name, comment in table_results.items()
                ]

        elif db_type == "sqlite":
            cursor = _db._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name LIKE ? ORDER BY name",
                (f"%{keyword}%",)
            )
            matched_tables = [{"name": row[0], "comment": None} for row in cursor.fetchall()]

        return {
            "status": "success",
            "keyword": keyword,
            "matched_tables": matched_tables,
            "matched_columns": matched_columns
        }

    except Exception as e:
        return {"status": "error", "message": f"搜索失败: {str(e)}"}


def suggest_columns(table_name: str, intent: str):
    """根据表名和用户意图，建议相关的列名，避免 SELECT *"""
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    try:
        # 先获取表的所有列
        desc = describe_table(table_name)
        if desc["status"] != "success":
            return desc

        all_columns = [c["name"].upper() for c in desc["columns"]]
        all_columns_orig = [c["name"] for c in desc["columns"]]

        # 根据意图匹配推荐列
        suggested = []
        # 基础列始终包含
        base_cols = ["RG_NAME", "YEAR_MONTH", "XM_NAME", "AI_XM_NAME", "DEPT_NAME", "RG_CODE", "DEPT_CODE"]
        for bc in base_cols:
            for orig in all_columns_orig:
                if orig.upper() == bc and orig.upper() not in [s.upper() for s in suggested]:
                    suggested.append(orig)

        # 意图列
        for pattern_name, pattern_cols in INTENT_COLUMN_PATTERNS.items():
            if pattern_name in intent:
                for pc in pattern_cols:
                    for orig in all_columns_orig:
                        if orig.upper() == pc.upper() and orig.upper() not in [s.upper() for s in suggested]:
                            suggested.append(orig)

        # 如果没有明确的意图匹配，添加常用金额列
        if len(suggested) <= len(base_cols):
            amount_cols = ["YSS", "BYS_JE", "BY_JE", "BYLJS_JE", "BYS_SNTYS", "BY_SNTYS", "BYS_TBE", "BY_TBE", "BYS_TBB", "BY_TBBFS"]
            already = {s.upper() for s in suggested}
            for ac in amount_cols:
                for orig in all_columns_orig:
                    if orig.upper() == ac.upper() and orig.upper() not in already:
                        suggested.append(orig)
                        already.add(ac.upper())

        # 分析列名变体
        variants = {}
        variant_groups = [
            (["BYS_JE", "BY_JE"], "本月金额"),
            (["BYS_SNTYS", "BY_SNTYS"], "上年同期"),
            (["BYS_TBE", "BY_TBE"], "同比增减额"),
            (["BYS_TBB", "BY_TBBFS", "BYS_TBP"], "同比增减率"),
            (["BYS_TBB", "BYS_TBP"], "同比增减率"),
        ]
        for vg, vg_name in variant_groups:
            found = [c for c in all_columns_orig if c.upper() in [v.upper() for v in vg]]
            if len(found) > 1:
                variants[vg_name] = found

        return {
            "status": "success",
            "table_name": table_name,
            "intent": intent,
            "suggested_columns": suggested,
            "all_columns": all_columns_orig,
            "column_variants": variants
        }

    except Exception as e:
        return {"status": "error", "message": f"推荐列失败: {str(e)}"}
