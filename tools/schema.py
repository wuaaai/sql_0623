"""
Text-to-SQL 工具 Schema 定义 (OpenAI function-calling 格式)

阶段1: connect_db, list_tables, run_sql
"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "connect_db",
            "description": "连接数据库。支持 MySQL 和 SQLite。使用其他数据库工具前必须先连接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_type": {
                        "type": "string",
                        "enum": ["mysql", "sqlite"],
                        "description": "数据库类型"
                    },
                    "host": {
                        "type": "string",
                        "description": "数据库主机地址 (sqlite时不需要)"
                    },
                    "port": {
                        "type": "integer",
                        "description": "端口号 (sqlite时不需要)",
                        "default": 3306
                    },
                    "user": {
                        "type": "string",
                        "description": "用户名 (sqlite时不需要)"
                    },
                    "password": {
                        "type": "string",
                        "description": "密码 (sqlite时不需要)"
                    },
                    "database": {
                        "type": "string",
                        "description": "数据库名 (sqlite时为文件路径)"
                    }
                },
                "required": ["db_type", "database"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "列出当前连接数据库中的所有表。返回表名列表。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "执行 SELECT 查询并返回结果。仅支持只读查询，禁止 INSERT/UPDATE/DELETE/DROP 等写操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的 SELECT 查询语句"
                    }
                },
                "required": ["sql"]
            }
        }
    }
]
