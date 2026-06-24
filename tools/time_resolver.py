"""
时间解析工具

resolve_time: 将用户的时间表达解析为具体的 YEAR_MONTH 条件
- 无明确时间 → 查询数据库最新年月
- 明确时间 → 直接返回对应条件
- 相对时间 → 基于当前日期或上下文计算
"""

from datetime import datetime
from tools import db_connection as _db


def resolve_time(expression: str = None, context_month: str = None):
    """
    解析用户时间表达，返回 YEAR_MONTH 的 WHERE 条件片段。

    Args:
        expression: 用户的时间表达，如 "2025年1月"、"最近"、"今年"、None
        context_month: 上下文中的年月（如上一轮查询的 YEAR_MONTH），用于推断"上个月"

    Returns:
        {
            "status": "success",
            "expression": 原始表达,
            "resolved": 解析后的描述,
            "where_clause": WHERE 子句片段,
            "latest_month": 数据库最新年月,
            "current_month": 当前年月
        }
    """
    if _db._connection is None:
        return {"status": "error", "message": "未连接数据库"}

    current_month = datetime.now().strftime("%Y%m")
    current_year = datetime.now().strftime("%Y")

    # 查询数据库最新年月
    latest_month = None
    try:
        db_type = _db._conn_info["db_type"]
        if db_type == "dameng":
            schema = _db._conn_info.get("schema", "")
            cursor = _db._connection.cursor()
            # 从预算表找最新数据
            if schema:
                cursor.execute(f"""
                    SELECT MAX(YEAR_MONTH) FROM (
                        SELECT MAX(YEAR_MONTH) AS YEAR_MONTH FROM RDYS_LD_YSZX_YBGGYS_DQZCWCQK
                        UNION ALL
                        SELECT MAX(YEAR_MONTH) FROM RDYS_LD_YSSC_YSZX_QSYBGGYSSRWC
                    )
                """)
            else:
                cursor.execute("SELECT MAX(YEAR_MONTH) FROM RDYS_LD_YSZX_YBGGYS_DQZCWCQK")
            row = cursor.fetchone()
            if row and row[0]:
                latest_month = str(row[0])
    except Exception:
        latest_month = current_month

    if latest_month is None:
        latest_month = current_month

    # === 解析时间表达 ===

    # 情况1: 无明确时间 → 用数据库最新数据
    if not expression or not expression.strip():
        return {
            "status": "success",
            "expression": expression or "(未指定)",
            "resolved": f"未指定时间，使用数据库最新数据（{_format_month(latest_month)}）",
            "where_clause": f"YEAR_MONTH = '{latest_month}'",
            "latest_month": latest_month,
            "current_month": current_month
        }

    expr = expression.strip()

    # 情况2: 明确年月 "2025年1月"
    import re
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月?', expr)
    if m:
        year, month = m.group(1), m.group(2).zfill(2)
        ym = f"{year}{month}"
        return {
            "status": "success",
            "expression": expr,
            "resolved": f"{year}年{month}月",
            "where_clause": f"YEAR_MONTH = '{ym}'",
            "latest_month": latest_month,
            "current_month": current_month
        }

    # 情况3: 明确年份 "2025年"
    m = re.match(r'(\d{4})\s*年?$', expr)
    if m:
        year = m.group(1)
        return {
            "status": "success",
            "expression": expr,
            "resolved": f"{year}年全年",
            "where_clause": f"YEAR_MONTH LIKE '{year}%'",
            "latest_month": latest_month,
            "current_month": current_month
        }

    # 情况4: "最近N个月" — 必须在"最近"之前匹配
    m = re.match(r'最近\s*(\d+)\s*个?\s*月', expr)
    if m:
        n = int(m.group(1))
        months = _recent_months(latest_month, n)
        in_clause = ", ".join(f"'{m}'" for m in months)
        return {
            "status": "success",
            "expression": expr,
            "resolved": f"最近{n}个月（{_format_month(months[-1])} 至 {_format_month(months[0])}）",
            "where_clause": f"YEAR_MONTH IN ({in_clause})",
            "latest_month": latest_month,
            "current_month": current_month
        }

    # 情况5: 相对时间 "最近一个月" / "最新" / "最近"
    if any(w in expr for w in ["最近", "最新", "当前", "现在"]):
        return {
            "status": "success",
            "expression": expr,
            "resolved": f"数据库最新数据（{_format_month(latest_month)}）",
            "where_clause": f"YEAR_MONTH = '{latest_month}'",
            "latest_month": latest_month,
            "current_month": current_month
        }

    # 情况5: "上个月" — 基于上下文或最新数据
    if "上个月" in expr or "上月" in expr:
        base = context_month or latest_month
        prev = _prev_month(base)
        return {
            "status": "success",
            "expression": expr,
            "resolved": f"上个月（{_format_month(prev)}）",
            "where_clause": f"YEAR_MONTH = '{prev}'",
            "latest_month": latest_month,
            "current_month": current_month
        }

    # 情况6: "今年" / "本年"
    if expr in ["今年", "本年"]:
        return {
            "status": "success",
            "expression": expr,
            "resolved": f"今年（{current_year}年）",
            "where_clause": f"YEAR_MONTH LIKE '{current_year}%'",
            "latest_month": latest_month,
            "current_month": current_month
        }

    # 情况7: "去年" / "上年"
    if expr in ["去年", "上年"]:
        last_year = str(int(current_year) - 1)
        return {
            "status": "success",
            "expression": expr,
            "resolved": f"去年（{last_year}年）",
            "where_clause": f"YEAR_MONTH LIKE '{last_year}%'",
            "latest_month": latest_month,
            "current_month": current_month
        }

    # 情况9: 未识别的表达 → 返回原始表达，让 LLM 自行处理
    return {
        "status": "success",
        "expression": expr,
        "resolved": f"未识别的表达'{expr}'，尝试作为月份前缀匹配",
        "where_clause": f"YEAR_MONTH LIKE '%{expr}%'",
        "latest_month": latest_month,
        "current_month": current_month
    }


def _format_month(ym: str) -> str:
    """202501 → '2025年1月'"""
    if len(ym) == 6:
        return f"{ym[:4]}年{int(ym[4:])}月"
    return ym


def _prev_month(ym: str) -> str:
    """返回上一个月，202501 → 202412"""
    year, month = int(ym[:4]), int(ym[4:])
    if month == 1:
        return f"{year-1}12"
    return f"{year}{month-1:02d}"


def _recent_months(latest: str, n: int) -> list:
    """返回最近N个月，从最新开始倒序"""
    months = []
    ym = latest
    for _ in range(n):
        months.append(ym)
        ym = _prev_month(ym)
    return months
