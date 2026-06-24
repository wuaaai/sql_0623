# 聚合统计技能

## 核心判断

用户问题分两类——写 SQL 前先判断：

| 用户问法 | 类型 | 用什么 |
|---------|------|--------|
| "河北省XX收入合计" | 明细（查一行） | run_sql |
| "各市收入排名" | 统计（跨行汇总） | **需要 GROUP BY** |
| "收入最高的5个地市" | 统计（排名） | **需要 GROUP BY + ORDER BY** |
| "各月收入趋势" | 统计（时间聚合） | **需要 GROUP BY YEAR_MONTH** |
| "平均/汇总/总共" | 统计（聚合函数） | **需要 SUM/AVG/COUNT** |

## 实现路径

### 路径A: 用 run_aggregation（推荐，一步到位）

适合标准的"分组+聚合+排序+TOP N"查询。

```
run_aggregation(
  table_name="表名",
  group_by="RG_NAME",           -- 分组列
  aggregate="SUM(BYS_JE)",      -- 聚合表达式
  filters="XM_NAME LIKE '%合%计%'",  -- WHERE条件
  order="DESC",                 -- 排序
  limit=10                      -- TOP N
)
```

示例:
- "各市收入排名前10" → run_aggregation(t, "RG_NAME", "SUM(BYS_JE)", "XM_NAME LIKE '%合%计%'", "DESC", 10)
- "各月收入趋势" → run_aggregation(t, "YEAR_MONTH", "SUM(BYS_JE)", "XM_NAME LIKE '%合%计%'", "ASC", 12)
- "同比增长最快5地区" → run_aggregation(t, "RG_NAME", "AVG(BYS_TBB)", "XM_NAME LIKE '%合%计%'", "DESC", 5)

### 路径B: 用现有工具组合（灵活，适合复杂场景）

当 run_aggregation 无法满足时（如需要复杂 WHERE 条件、多表、子查询），用标准工具链：

```
search_schema → describe_table → run_sql(带GROUP BY的SQL)
```

**关键**: 用 run_sql 写聚合时，必须写 GROUP BY + 聚合函数，禁止 SELECT DISTINCT。

SQL模板（达梦）:
```sql
-- 分组排名
SELECT * FROM (
  SELECT RG_NAME, SUM(BYS_JE) as total
  FROM table WHERE ...
  GROUP BY RG_NAME
  ORDER BY total DESC
) WHERE ROWNUM <= N

-- 时间趋势  
SELECT YEAR_MONTH, SUM(BYS_JE) as total
FROM table WHERE ...
GROUP BY YEAR_MONTH
ORDER BY YEAR_MONTH
```

## 排名结果展示

- 表格包含：排名序号、分组名、聚合值
- 标注最高/最低
- 金额2位小数，百分比1位小数
