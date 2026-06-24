# 跨表分析技能

## 决策：选哪种跨表策略

```
用户问题
  ├─ "XX和YY对比" → 策略A: 并行查询+LLM对比
  ├─ "四大预算XX排名/合计" → 策略B: UNION ALL + 聚合
  ├─ "按XX分类汇总" → 策略C: 字典表JOIN
  └─ "这两张表怎么关联" → 策略D: find_relations发现
```

## 策略A: 并行查询+LLM对比（主路径）

适用: 跨预算对比。分别查各表，LLM并列展示对比。

步骤:
1. search_schema 定位两张表
2. 分别 describe_table → run_aggregation/run_sql
3. LLM 将两组结果并列展示，标注差异

## 策略B: UNION ALL + 聚合

适用: 同构表合并。四类预算结构相同，可合并后统一排名/汇总。

步骤:
1. search_schema 获取四类预算表
2. find_relations 确认同构
3. union_query 或 run_sql(含UNION ALL) 合并查询

## 策略C: 字典表JOIN

适用: 执行表 JOIN 字典表(RDYS_BAS_*)。

步骤:
1. find_relations(执行表, 字典表) 获取关联键
2. run_sql 写 JOIN + GROUP BY 字典表.名称列

常见关联键:
- EXP_FUNC_CODE → RDYS_BAS_EXPFUNC(支出分类)
- MOF_DIV_CODE → RDYS_BAS_MOFDIV(地区划分)
- RG_CODE → 地区 | YEAR_MONTH → 时间

## 策略D: 关系发现

步骤:
1. find_relations(table_a, table_b)
2. 用自然语言告知用户关联方式
3. 如用户要求查询，切换策略A/B/C

## 注意事项

- 对比时确保时间范围一致
- NULL标记为"无数据"
- 金额单位一致（都是元）
