# SQL 生成技能

## 规则

1. **只能 SELECT**，禁止 INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE
2. 达梦数据库使用 `ROWNUM` 限制行数（不是 LIMIT）
3. 达梦数据库使用 `||` 连接字符串（不是 CONCAT）
4. 关键字大写: SELECT, FROM, WHERE, JOIN, AND, OR, LIKE, BETWEEN, IN, ORDER BY, GROUP BY

## 写法规范

```sql
SELECT column1, column2
FROM table_name
WHERE condition1
  AND condition2
ORDER BY column1
```

- 每个子句独占一行
- AND/OR 条件对齐缩进
- 达梦查询前 N 行: `WHERE ROWNUM <= N`

## WHERE 条件模式

### 等值匹配
用户: "MOF_DIV_CODE 是 130000000" → `WHERE MOF_DIV_CODE = '130000000'`
用户: "级别为3" → `WHERE LEVEL_NO = 3`

### 比较运算
用户: "级别大于2" → `WHERE LEVEL_NO > 2`
用户: "金额大于等于1000" → `WHERE amount >= 1000`

### 模糊匹配 LIKE
用户: "名称包含教育" → `WHERE name LIKE '%教育%'`
用户: "以海南省开头" → `WHERE name LIKE '海南省%'`

### 多条件 AND/OR
用户: "级别为3且已启用" → `WHERE LEVEL_NO = 3 AND IS_ENABLED = 1`
用户: "级别为2或3" → `WHERE LEVEL_NO = 2 OR LEVEL_NO = 3`
也支持: `WHERE LEVEL_NO IN (2, 3)`

### BETWEEN 范围
用户: "FISCAL_YEAR 在 2020 到 2022 之间" → `WHERE FISCAL_YEAR BETWEEN 2020 AND 2022`

### NULL 判断
用户: "备注为空的" → `WHERE memo IS NULL`
用户: "有备注的" → `WHERE memo IS NOT NULL`

### ORDER BY 排序
用户: "按级别从低到高" → `ORDER BY LEVEL_NO ASC`
用户: "按时间倒序" → `ORDER BY UPDATE_TIME DESC`

## 安全

- 必须加 ROWNUM 限制（默认 <= 20，用户指定时用指定值）
- 不带 ROWNUM 的大表全量查询必须拒绝
- 遇到写操作自动拦截

## 达梦语法要点

- ROWNUM <= N (不是 LIMIT N)
- 字符串拼接: ||
- 当前日期: SYSDATE
- 字符串必须用单引号
- 数字不加引号: WHERE LEVEL_NO = 3 (不是 '3')
