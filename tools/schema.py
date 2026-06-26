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
    },
    {
        "type": "function",
        "function": {
            "name": "run_aggregation",
            "description": "执行聚合统计查询（GROUP BY + 聚合函数 + 排序 + TOP N）。当用户问各市/各地/各月/排名/最高/最低/平均/汇总/趋势时使用。自动处理达梦ROWNUM+ORDER BY子查询。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名"
                    },
                    "group_by": {
                        "type": "string",
                        "description": "分组列名，如 RG_NAME（按地区）、YEAR_MONTH（按时间）、XM_NAME（按项目）"
                    },
                    "aggregate": {
                        "type": "string",
                        "description": "聚合表达式，如 SUM(BYS_JE)、AVG(BYS_TBB)、COUNT(*)、MAX(BYS_JE)"
                    },
                    "filters": {
                        "type": "string",
                        "description": "额外的WHERE条件（不含ROWNUM），如 XM_NAME LIKE '%合计%' AND YEAR_MONTH = '202604'"
                    },
                    "order": {
                        "type": "string",
                        "enum": ["DESC", "ASC"],
                        "description": "排序方向，默认DESC（从高到低）"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回行数，默认20"
                    }
                },
                "required": ["table_name", "group_by", "aggregate"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_relations",
            "description": "分析两张表之间的关系：发现公共列、建议关联方式（JOIN或UNION）。当用户问'这两张表怎么关联'或需要跨表查询前使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_a": {"type": "string", "description": "第一张表名"},
                    "table_b": {"type": "string", "description": "第二张表名"}
                },
                "required": ["table_a", "table_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "union_query",
            "description": "对多张同构表（结构相同的表）执行UNION ALL合并后聚合查询。用于跨预算类型合并排名、汇总。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tables": {"type": "string", "description": "逗号分隔的表名列表"},
                    "select_cols": {"type": "string", "description": "SELECT的列名"},
                    "group_by": {"type": "string", "description": "分组列名"},
                    "aggregate": {"type": "string", "description": "聚合表达式，如SUM(BYS_JE)"},
                    "filters": {"type": "string", "description": "WHERE条件(可选)"},
                    "order": {"type": "string", "enum": ["DESC", "ASC"], "description": "排序方向"},
                    "limit": {"type": "integer", "description": "返回行数，默认20"}
                },
                "required": ["tables", "select_cols", "group_by", "aggregate"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_subquery",
            "description": "带子查询的两阶段查询。先执行子查询获取标量值(如平均值)，再嵌入外层SQL执行。用于'超过全省平均'、'比XX市高'等与聚合值比较的场景。base_sql中用{SUBQUERY}占位。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "主表名"},
                    "base_sql": {"type": "string", "description": "外层SQL模板，用{SUBQUERY}占位子查询结果"},
                    "subquery_sql": {"type": "string", "description": "子查询SQL，必须返回单个标量值"}
                },
                "required": ["table", "base_sql", "subquery_sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calc_ratio",
            "description": "计算占比：每个分组值占总计的百分比。使用窗口函数SUM() OVER()。用于'各地市占全省比例'、'税收占比'等场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "表名"},
                    "value_col": {"type": "string", "description": "数值列名，如BYS_JE"},
                    "group_col": {"type": "string", "description": "分组列名，如RG_NAME"},
                    "filters": {"type": "string", "description": "WHERE条件(可选)"}
                },
                "required": ["table", "value_col", "group_col"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_anomalies",
            "description": "异常检测：计算均值和标准差，标记超出均值±threshold倍标准差的离群值。threshold默认2.0(95%置信区间)。用于'有没有异常'、'收入特别高/低'等场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "表名"},
                    "value_col": {"type": "string", "description": "检测的数值列"},
                    "group_col": {"type": "string", "description": "分组标识列，如RG_NAME"},
                    "filters": {"type": "string", "description": "WHERE条件(可选)"},
                    "threshold": {"type": "number", "description": "标准差倍数阈值，默认2.0"}
                },
                "required": ["table", "value_col", "group_col"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_patterns",
            "description": "检索历史成功查询模式。当用户的新问题与历史查询相似时，可参考历史SQL模板快速改写，避免重复探索表结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "用户问题关键词"},
                    "budget_type": {"type": "string", "description": "预算类型(可选)"},
                    "limit": {"type": "integer", "description": "返回条数，默认3"}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "跨层搜索记忆系统(L1索引/L3技能/L4模式)。用于查找之前学到的知识、相似查询模式或相关技能文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "layer": {"type": "string", "description": "搜索层级: all/L1/L3/L4，默认all"}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "搜索预算解读知识库（政策文档、预算解读等非结构化知识）。当用户问政策/规定/解读/编制要求等文档类问题时使用。注意：查具体数据（收入/支出/金额/排名）用 run_sql，查政策知识用 rag_search。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询文本"}
                },
                "required": ["query"]
            }
        }
    }
]
