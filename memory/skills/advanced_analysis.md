# 深度分析技能

## 决策：用哪个工具

```
用户问题
  ├─ "超过/低于 平均/XX市" → run_subquery
  ├─ "占比/比例/比重" → calc_ratio
  ├─ "比上月/环比/增长下降" → run_sql + LAG模板
  └─ "异常/特别/不对劲" → detect_anomalies
```

## 子查询 (run_subquery)
先算子查询得标量→嵌入外层SQL的{SUBQUERY}占位符。

示例: "超过全省平均的地市"
```
run_subquery(table, 
  "SELECT RG_NAME, BYS_JE FROM table WHERE BYS_JE > {SUBQUERY}",
  "SELECT AVG(BYS_JE) FROM table WHERE XM_NAME LIKE '%合%计%'")
```

## 占比 (calc_ratio)
窗口函数 SUM() OVER() 自动算分母。

示例: "各地市占全省比例"
```
calc_ratio(table, "BYS_JE", "RG_NAME", "XM_NAME LIKE '%合%计%'")
```
结果含 RATIO_PCT 列，总和≈100%。

## 环比 (run_sql + LAG)
达梦支持 LAG 窗口函数。

```sql
SELECT RG_NAME, YEAR_MONTH, BYS_JE,
  LAG(BYS_JE,1) OVER (PARTITION BY RG_NAME ORDER BY YEAR_MONTH) AS PREV,
  BYS_JE - LAG(BYS_JE,1) OVER (PARTITION BY RG_NAME ORDER BY YEAR_MONTH) AS DIFF
FROM table WHERE ...
```

## 异常检测 (detect_anomalies)
Z-Score = (值-均值)/标准差。threshold默认2.0。

示例: "有没有异常的地市"
```
detect_anomalies(table, "BYS_JE", "RG_NAME", "XM_NAME LIKE '%合%计%'", 2.0)
```

阈值指南:
- 2.0: 常规(95%置信区间外)
- 2.5: 严格(减少误报)
- 3.0: 极端(向领导汇报用)
