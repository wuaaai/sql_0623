"""
SQL 错误分析与修复建议

classify_error: 分析错误信息，返回错误类型
suggest_fix:  根据错误类型返回修复建议
get_friendly_msg: 返回友好降级话术
"""

_ERROR_PATTERNS = [
    ("column", ["invalid identifier", "column", "unknown column", "not found",
                "ORA-00904", "column not allowed", "not a valid column"]),
    ("table", ["table or view does not exist", "table not found",
               "ORA-00942", "no such table", "relation"]),
    ("syntax", ["syntax error", "ORA-00936", "ORA-00933",
                "missing keyword", "missing expression", "unexpected"]),
    ("timeout", ["timeout", "timed out", "ORA-01013", "cancel", "interrupt"]),
    ("type", ["type mismatch", "datatype", "ORA-01722", "invalid number",
              "cannot convert", "inconsistent datatype"]),
]

_FRIENDLY_MSGS = {
    "column": "列名可能不正确。建议换个说法描述查询条件，系统会自动找到正确的列。",
    "table": "未找到对应的数据表。建议从'一般公共预算'等常用预算类型开始。",
    "syntax": "SQL语法需要调整。已尝试自动修正，建议简化查询条件后重试。",
    "timeout": "查询超时，数据量可能较大。已自动缩小查询范围，建议指定更具体的地区和时间。",
    "type": "数据类型不匹配。这可能是因为数据库结构与预期不一致，建议简化查询。",
    "unknown": "查询遇到技术问题。建议简化查询条件后重试，或换个方式描述需求。",
}


def classify_error(error_msg: str) -> str:
    """分析错误信息，返回错误类型: column/table/syntax/timeout/type/unknown"""
    msg_lower = error_msg.lower()
    for err_type, keywords in _ERROR_PATTERNS:
        for kw in keywords:
            if kw.lower() in msg_lower:
                return err_type
    return "unknown"


def suggest_fix(error_type: str, error_msg: str, table_name: str, sql: str) -> str:
    """返回修复建议文本，引导LLM修正SQL"""
    base = f"SQL执行失败: {error_msg[:200]}\n执行的SQL: {sql[:300]}"

    hints = {
        "column": (f"用 describe_table 确认 {table_name or '目标表'} 的正确列名。"
                   "检查列名大小写（达梦默认大写）和列名变体(BYS_JE/BY_JE, BYS_TBB/BY_TBBFS)。"),
        "table": "用 search_schema 或 list_tables 确认正确的表名。检查表名是否遗漏前缀。",
        "syntax": "检查关键字拼写和括号配对。简化SQL：先查少量列再逐步增加。检查达梦兼容性(不用LIMIT)。",
        "timeout": "添加更精准的WHERE条件缩小范围。用 resolve_time 限制时间。加 ROWNUM 限制行数。",
        "type": "检查聚合函数是否作用在数值列。检查比较条件类型一致。字符串值加单引号。",
        "unknown": "简化SQL，先查最基本的列。用 describe_table 确认表结构。",
    }

    hint = hints.get(error_type, hints["unknown"])
    return f"{base}\n\n[自动修正指引-{error_type}] {hint}\n请修正后重新执行 run_sql。"


def get_friendly_msg(error_type: str) -> str:
    """返回友好降级话术"""
    return _FRIENDLY_MSGS.get(error_type, _FRIENDLY_MSGS["unknown"])
