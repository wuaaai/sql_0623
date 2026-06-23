"""
Schema 探索工具

describe_table: 查看表结构（列名、类型）+ 样例数据
search_schema: 按关键词搜索表和列名
"""

from tools import db_connection as _db


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

            # 获取列信息
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

            # 获取一行样例
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
    """按关键词搜索表和列名，帮助用户从模糊描述找到正确的表"""
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

            if schema:
                # 1. 搜索表名
                cursor.execute(f"""
                    SELECT TABLE_NAME, NULL FROM ALL_TABLES
                    WHERE OWNER = '{schema.upper()}'
                      AND TABLE_NAME LIKE '%{kw}%'
                    ORDER BY TABLE_NAME
                """)
                matched_tables = [row[0] for row in cursor.fetchall()]

                # 2. 搜索表注释（中文注释匹配）
                try:
                    cursor.execute(f"""
                        SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS
                        WHERE OWNER = '{schema.upper()}'
                          AND COMMENTS IS NOT NULL
                          AND COMMENTS LIKE '%{keyword}%'
                        ORDER BY TABLE_NAME
                    """)
                    for row in cursor.fetchall():
                        if row[0] not in matched_tables:
                            matched_tables.append(row[0])
                except Exception:
                    pass

                # 3. 搜索列名
                cursor.execute(f"""
                    SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
                    FROM ALL_TAB_COLUMNS
                    WHERE OWNER = '{schema.upper()}'
                      AND COLUMN_NAME LIKE '%{kw}%'
                    ORDER BY TABLE_NAME, COLUMN_ID
                """)
                for row in cursor.fetchall():
                    matched_columns.append({
                        "table": row[0],
                        "column": row[1],
                        "type": row[2]
                    })
            else:
                cursor.execute(f"""
                    SELECT TABLE_NAME FROM USER_TABLES
                    WHERE TABLE_NAME LIKE '%{kw}%'
                    ORDER BY TABLE_NAME
                """)
                matched_tables = [row[0] for row in cursor.fetchall()]

                cursor.execute(f"""
                    SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
                    FROM USER_TAB_COLUMNS
                    WHERE COLUMN_NAME LIKE '%{kw}%'
                    ORDER BY TABLE_NAME, COLUMN_ID
                """)
                for row in cursor.fetchall():
                    matched_columns.append({
                        "table": row[0],
                        "column": row[1],
                        "type": row[2]
                    })

        elif db_type == "sqlite":
            cursor = _db._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name LIKE ? ORDER BY name",
                (f"%{keyword}%",)
            )
            matched_tables = [row[0] for row in cursor.fetchall()]

        return {
            "status": "success",
            "keyword": keyword,
            "matched_tables": matched_tables,
            "matched_columns": matched_columns
        }

    except Exception as e:
        return {"status": "error", "message": f"搜索失败: {str(e)}"}
