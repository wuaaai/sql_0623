# SQL 生成技能

## 规则

1. **只能 SELECT**，禁止 INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE
2. 达梦数据库使用 `ROWNUM` 限制行数（不是 LIMIT）
3. 达梦数据库使用 `||` 连接字符串（不是 CONCAT）
4. 关键字大写: SELECT, FROM, WHERE, JOIN, ORDER BY, GROUP BY, ROWNUM

## 写法规范

```sql
SELECT column1, column2
FROM schema.table_name
WHERE condition
  AND another_condition
ORDER BY column1
```

- 每个子句独占一行
- AND/OR 条件对齐缩进
- 达梦查询前 N 行: `WHERE ROWNUM <= N`

## 安全

- 必须加 ROWNUM 限制（默认 <= 20）
- 遇到写操作自动拦截
- 不允许不带 ROWNUM 的大表全量查询
