# 高效查询策略

## 目标：3轮内完成查询

每轮可以调用多个工具。合并调用减少轮次。

## 标准查询路径

### 路径1: 明确知道查什么（最快，2轮）
```
第1轮: search_schema(关键词) + resolve_time(时间表达)  [合并调用]
第2轮: describe_table(表名) + run_sql(SQL)  [合并调用，或拿到结构后直接写SQL执行]
```

### 路径2: 需要确认结构（3轮）
```
第1轮: search_schema(关键词) + resolve_time(时间表达)
第2轮: describe_table(表名)
第3轮: run_sql 或 run_aggregation
```

### 不要做的事（浪费轮次）
- ❌ describe_table 两张以上的表（先选一张最可能的查）
- ❌ describe_table 后还调 suggest_columns（describe 已展示列名）
- ❌ search_schema 反复调（第一次结果已够用）
- ❌ run_sql 执行后还要 run_sql 再查（除非用户追问）
- ❌ 用 SELECT DISTINCT 替代聚合（直接 SELECT 需要的列 + ORDER BY）

## 排名查询技巧

数据库有现成的排名表 `RDYS_LD_YSZX_YBGGYS_SZPMQK`:
- `SR_LJWCS_SORT`: 收入累计完成数排名
- `SR_TBE_SORT`: 收入同比增减排名
- `ZC_LJWCS_SORT`: 支出排名
- 直接 `SELECT * FROM SZPMQK WHERE ... ORDER BY SR_LJWCS_SORT` 即可

其他预算类型没有排名表时:
- 用 ORDER BY + ROWNUM 子查询
- 如果只是简单排序（不要聚合），直接 `SELECT ... FROM table WHERE ... ORDER BY col`

## 选择合适的表

根据预算类型和收支方向:
- 查"收入" → 找表名含 SR 或 收入 的表，或 search_schema("预算类型 收入")
- 查"支出" → 找表名含 ZC 或 支出 的表
- 查"排名" → 优先查 SZPMQK 排名表
- 查"累计" → 选 LJ_JE / BYLJS_JE 等累计列
- 查"本月" → 选 BYS_JE / BY_JE
