"""
数据库连接管理工具

阶段1: connect_db, list_tables
"""

import sqlite3
import pymysql

_connection = None
_conn_info = None


def connect_db(db_type: str, database: str,
               host: str = None, port: int = 3306,
               user: str = None, password: str = None):
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

        elif db_type == "mysql":
            _connection = pymysql.connect(
                host=host, port=port, user=user,
                password=password, database=database,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor
            )
            _conn_info = {
                "db_type": "mysql", "host": host,
                "port": port, "database": database
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
        if _conn_info["db_type"] == "sqlite":
            cursor = _connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

        elif _conn_info["db_type"] == "mysql":
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
