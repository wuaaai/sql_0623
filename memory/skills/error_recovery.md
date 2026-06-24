# 错误恢复技能

## 核心原则

SQL错误是正常的。系统自动分析→修正→重试，最多2次后友好降级。重试不消耗轮次。

## 自动重试流程

| 次数 | 行为 |
|------|------|
| 第1次 | classify_error→suggest_fix→注入修正指引 |
| 第2次 | 同上+最后一次警告 |
| 第3次 | 友好降级，向用户解释困难 |

## 错误类型与修复

### 列名错误 (column)
- 症状: "invalid identifier", ORA-00904
- 修复: describe_table确认列名→检查变体(BYS_JE/BY_JE)

### 表名错误 (table)
- 症状: "table or view does not exist", ORA-00942
- 修复: search_schema定位正确表→替换

### 语法错误 (syntax)
- 症状: "syntax error", "missing keyword"
- 修复: 检查ROWNUM位置/达梦兼容性(LIMIT→ROWNUM)

### 超时 (timeout)
- 症状: "timeout", ORA-01013
- 修复: 加ROWNUM限制/缩小WHERE范围

### 类型错误 (type)
- 症状: "type mismatch", ORA-01722
- 修复: TO_NUMBER()/TO_CHAR()显式转换
