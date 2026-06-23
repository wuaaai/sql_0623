"""
数据库连接管理工具

阶段1: connect_db, list_tables
支持: 达梦(Dameng), MySQL, SQLite
"""

import sqlite3
import pymysql
import dmPython

_connection = None
_conn_info = None


def connect_db(db_type: str, database: str = None,
               host: str = None, port: int = None,
               user: str = None, password: str = None,
               schema: str = None):
    """建立数据库连接，保存为全局活跃连接"""
    global _connection, _conn_info

    # 先关闭旧连接
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None
        _conn_info = None

    try:
        if db_type == "sqlite":
            _connection = sqlite3.connect(database)
            _connection.row_factory = sqlite3.Row
            _conn_info = {"db_type": "sqlite", "database": database}
            return {
                "status": "success",
                "message": f"已连接到 SQLite: {database}"
            }

        elif db_type == "dameng":
            port = port or 5236
            kwargs = {
                "user": user,
                "password": password,
                "server": host,
                "port": port
            }
            if database:
                kwargs["database"] = database
            if schema:
                kwargs["schema"] = schema
            _connection = dmPython.connect(**kwargs)
            _conn_info = {
                "db_type": "dameng",
                "host": host,
                "port": port,
                "database": database,
                "schema": schema
            }
            return {
                "status": "success",
                "message": f"已连接到达梦: {host}:{port}/{database or '默认库'} (schema={schema})"
            }

        elif db_type == "mysql":
            port = port or 3306
            _connection = pymysql.connect(
                host=host, port=port, user=user,
                password=password, database=database,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor
            )
            _conn_info = {
                "db_type": "mysql", "host": host,
                "port": port, "database": database, "schema": schema
            }
            return {
                "status": "success",
                "message": f"已连接到 MySQL: {host}:{port}/{database}"
            }

        else:
            return {"status": "error", "message": f"不支持的数据库类型: {db_type}"}

    except Exception as e:
        _connection = None
        _conn_info = None
        return {"status": "error", "message": f"连接失败: {str(e)}"}


def list_tables():
    """列出当前连接中的所有表"""
    global _connection

    if _connection is None:
        return {"status": "error", "message": "未连接数据库，请先使用 connect_db"}

    try:
        db_type = _conn_info["db_type"]

        if db_type == "sqlite":
            cursor = _connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

        elif db_type == "dameng":
            cursor = _connection.cursor()
            schema = _conn_info.get("schema")
            if schema:
                cursor.execute(
                    f"SELECT table_name FROM all_tables WHERE owner = '{schema.upper()}' ORDER BY table_name"
                )
            else:
                cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
            tables = [row[0] for row in cursor.fetchall()]

        elif db_type == "mysql":
            cursor = _connection.cursor()
            cursor.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cursor.fetchall()]

        return {
            "status": "success",
            "table_count": len(tables),
            "tables": tables
        }

    except Exception as e:
        return {"status": "error", "message": f"获取表列表失败: {str(e)}"}
