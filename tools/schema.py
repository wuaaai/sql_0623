"""
Text-to-SQL 工具 Schema 定义 (OpenAI function-calling 格式)

阶段1: connect_db, list_tables, run_sql, describe_table, search_schema
"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "connect_db",
            "description": "连接数据库。支持达梦(Dameng)、MySQL 和 SQLite。使用其他数据库工具前必须先连接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_type": {
                        "type": "string",
                        "enum": ["dameng", "mysql", "sqlite"],
                        "description": "数据库类型: dameng=达梦数据库"
                    },
                    "host": {
                        "type": "string",
                        "description": "数据库主机地址 (sqlite时不需要)"
                    },
                    "port": {
                        "type": "integer",
                        "description": "端口号 (dameng默认5236, mysql默认3306, sqlite时不需要)",
                        "default": 5236
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
                    },
                    "schema": {
                        "type": "string",
                        "description": "模式名 (仅达梦/MySQL需要, 如 RDYS_PUBLIC_TBS)"
                    }
                },
                "required": ["db_type"]
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
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "查看指定表的结构：列名、数据类型、是否可空。同时返回一行样例数据帮助理解内容。用户描述模糊时先用此工具确认表结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名"
                    }
                },
                "required": ["table_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_schema",
            "description": "按关键词搜索表名和列名。当用户用模糊的中文描述（如'支出相关的表'、'金额列'）而你不知道具体表名/列名时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（中文或英文），会在表名和列名中进行模糊匹配"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_columns",
            "description": "根据表名和用户意图，智能推荐应查询的列名。用于避免 SELECT * 查询，按用户关注点（完成情况/同比/排名/预算执行）选择相关列。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名"
                    },
                    "intent": {
                        "type": "string",
                        "description": "用户意图描述，如：完成情况、同比、排名、预算执行"
                    }
                },
                "required": ["table_name", "intent"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_time",
            "description": "解析用户的时间表达为具体的SQL WHERE条件。当用户没有明确指定时间时，自动使用数据库最新数据。支持：明确年月(2025年1月)、相对时间(最近/今年/去年/上个月/最近N个月)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "用户的时间表达，如'2025年1月'、'最近'、'今年'。如果用户没有提到时间，传空字符串。"
                    },
                    "context_month": {
                        "type": "string",
                        "description": "上下文中的年月（格式YYYYMM），用于推断'上个月'等相对表达。无需上下文时不传。"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]
