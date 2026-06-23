# SQL 生成技能

## 核心规则

1. **只能 SELECT**，禁止写操作
2. 达梦: `ROWNUM` (非 LIMIT), `||` (非 CONCAT)
3. 关键字大写: SELECT, FROM, WHERE, AND, OR, LIKE, BETWEEN, IN, ORDER BY
4. 字符串单引号，数字不加引号
5. **写 WHERE 前必须 describe_table 确认列名**

## 预算业务查询模式

### 模式A: 按预算类型找表
用户说"一般公共预算" → search_schema("一般公共预算") 或 search_schema("YBGGYS")
找到表后 describe_table 确认结构，再根据用户具体需求写 SQL。

### 模式B: 按地区筛选
"河北省" → `WHERE RG_NAME = '河北省'`
"石家庄" → `WHERE RG_NAME LIKE '%石家庄%'`
"省本级" → `WHERE RG_NAME LIKE '%本级%'`
"各地市" → `WHERE RG_NAME NOT LIKE '%本级%'`

### 模式C: 按时间筛选
"2025年1月" → `WHERE YEAR_MONTH = '202501'`
"2025年" → `WHERE YEAR_MONTH LIKE '2025%'` 或 `WHERE DATE_YEAR = '2025'`
"今年" → 推断当前年份

### 模式D: 按项目筛选
"合计" → `WHERE XM_NAME LIKE '%合计%'`
"税收" → `WHERE XM_NAME LIKE '%税收%'`

### 模式E: 同比对比（核心场景）
用户问"增长/下降/比去年" → 选择同比列 BYS_TBE(增减额) 和 BYS_TBB(增减率)
"同比下降" → `WHERE BYS_TBE < 0`
"同比增长超过10%" → `WHERE BYS_TBB > 10`

### 模式F: 条件组合
"河北省2025年1月一般公共预算收入合计" →
```sql
SELECT RG_NAME, YEAR_MONTH, XM_NAME, YSS, BYS_JE, BYS_SNTYS, BYS_TBE, BYS_TBB
FROM table_name
WHERE RG_NAME = '河北省'
  AND YEAR_MONTH = '202501'
  AND XM_NAME LIKE '%合计%'
  AND ROWNUM <= 20
```

### 模式G: 智能列选择
不要 SELECT *，根据用户关注点选列:
- 用户关注"完成情况" → 选 BYS_JE, BYLJS_JE, YSS
- 用户关注"同比" → 选 BYS_JE, BYS_SNTYS, BYS_TBE, BYS_TBB
- 用户关注"排名" → 选 RG_NAME, 指标列, 加 ORDER BY
- 用户问"有哪些" → 选 RG_NAME, XM_NAME, YEAR_MONTH

## 达梦 ORDER BY + ROWNUM

```sql
-- 正确写法 (先排序再取前N)
SELECT * FROM (
  SELECT * FROM table_name
  WHERE conditions
  ORDER BY column_name DESC
) WHERE ROWNUM <= 10
```
