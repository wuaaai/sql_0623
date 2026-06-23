# 阶段1 测试问题集

## 基础 — 表浏览

| # | 问题 | 预期目标 |
|---|------|----------|
| 1 | 数据库中有哪些表 | 调用 list_tables，列出全部47张表的真实英文名，不编造中文含义 |
| 2 | 一共有多少张表 | 调用 list_tables，返回 47 |
| 3 | 表名中包含 YSZX 的有哪些 | 调用 list_tables 后筛选出 RDYS_LD_YSZX_ 开头的表 |
| 4 | BAS 开头的表有哪些 | 调用 list_tables，列出3张 RDYS_BAS_* 表 |
| 5 | 显示所有表名，按字母排序 | 调用 list_tables，按字母顺序展示 |

## 模糊语义 — 中文搜索

| # | 问题 | 预期目标 |
|---|------|----------|
| 6 | 支出相关的表有哪些 | 调用 search_schema("支出")，返回11张匹配表，附带注释 |
| 7 | 预算相关的表 | 调用 search_schema("预算")，返回25张表 |
| 8 | 收入分类在哪张表里 | 调用 search_schema("收入")，找到 RDYS_BAS_INCOMESORT |
| 9 | 查找和金融企业有关的表 | 调用 search_schema("金融") 或 search_schema("企业")，返回相关表 |
| 10 | 有没有关于工资的表 | 调用 search_schema("工资")，匹配 RDYS_LD_GZJD_* 系列 |
| 11 | 经济监督相关的表 | 调用 search_schema("监督")，匹配相关表 |
| 12 | 查找包含"完成"关键词的表 | 调用 search_schema("完成")，返回注释中包含"完成"的表 |
| 13 | 有没有关于农业的表 | 调用 search_schema("农业")，匹配相关表 |
| 14 | 查找和医疗保险相关的表 | 调用 search_schema("医疗") 或 search_schema("保险") |

## 表结构探索

| # | 问题 | 预期目标 |
|---|------|----------|
| 15 | 看看 RDYS_BAS_EXPFUNC 表的结构 | 调用 describe_table，返回20列及类型，附样例数据 |
| 16 | RDYS_BAS_MOFDIV 有哪些列 | 调用 describe_table，列出所有列名和类型 |
| 17 | RDYS_BAS_INCOMESORT 表里有什么字段 | 调用 describe_table，返回列信息 |
| 18 | 支出功能分类表的结构是什么 | 先 search_schema("支出") 找到 RDYS_BAS_EXPFUNC，再 describe_table |
| 19 | 看看那张收入表里有哪些列 | 先 search_schema("收入") 再 describe_table |

## 单表数据查询

| # | 问题 | 预期目标 |
|---|------|----------|
| 20 | 查看 RDYS_BAS_EXPFUNC 表的前5行 | 调用 run_sql，SELECT * WHERE ROWNUM <= 5 |
| 21 | 查询 RDYS_BAS_EXPFUNC 表的前10条数据 | ROWNUM <= 10 |
| 22 | 看看 RDYS_BAS_MOFDIV 表里有什么数据 | 先 describe_table 了解结构，再 SELECT 前几行 |
| 23 | 显示 RDYS_BAS_INCOMESORT 的前3行 | ROWNUM <= 3 |

## 统计查询

| # | 问题 | 预期目标 |
|---|------|----------|
| 24 | RDYS_BAS_EXPFUNC 表有多少条数据 | SELECT COUNT(*)，返回准确行数 |
| 25 | RDYS_BAS_MOFDIV 表的数据量 | SELECT COUNT(*)，返回 246 |
| 26 | 哪张表的数据量最大 | 可能需要查询多张表，逐一 COUNT |
| 27 | 统计 RDYS_LD_GZJD_FJRQY_FDQB 表的行数 | SELECT COUNT(*)，返回准确数字 |

## 综合场景 — 模糊到精确

| # | 问题 | 预期目标 |
|---|------|----------|
| 28 | 查询支出分类表的数据 | search_schema("支出") → 找到 RDYS_BAS_EXPFUNC → describe_table → run_sql |
| 29 | 预算收入完成情况表里有什么 | search_schema("预算收入") → 找到对应表 → describe → 展示结构 |
| 30 | 我想看财政收入分类的数据 | search_schema("收入") + search_schema("分类") → describe → run_sql |
| 31 | 那个财政部门划分的表，看看前几条 | search_schema → 找到 RDYS_BAS_MOFDIV → run_sql |

## 边界测试

| # | 问题 | 预期目标 |
|---|------|----------|
| 32 | 查询不存在的表 NOTEXIST_TABLE | 返回清晰的错误信息，建议用 list_tables |
| 33 | 搜索"xyz123不存在" | search_schema 返回"未找到匹配" |
| 34 | 只看前3行 | Agent 应追问"哪张表"，不能随意编造 |

## 结果展示规范

| # | 检查项 | 预期目标 |
|---|--------|----------|
| 35 | 所有回答中的表名 | 使用原始英文名（如 RDYS_BAS_EXPFUNC），不翻译 |
| 36 | 数字（表数、行数） | 来自工具返回，非编造 |
| 37 | SQL 语句 | 使用 ROWNUM 限制行数（非 LIMIT） |
| 38 | Markdown 格式 | 正确渲染为表格、标题、代码块，非原始文本 |
| 39 | 中文说明 | 不编造表的中文含义或业务说明 |

---

# 阶段2 测试问题集 — 条件筛选

## 等值匹配

| # | 问题 | 预期目标 |
|---|------|----------|
| 40 | 查询 RDYS_BAS_EXPFUNC 中 MOF_DIV_CODE 为 '130000000' 的数据 | 调用 describe_table → run_sql，WHERE MOF_DIV_CODE = '130000000' |
| 41 | RDYS_BAS_MOFDIV 中 LEVEL_NO 等于 3 的记录有哪些 | WHERE LEVEL_NO = 3（数字不加引号） |
| 42 | 查询 RDYS_BAS_EXPFUNC 中 IS_ENABLED 为 1 的记录 | WHERE IS_ENABLED = 1 |
| 43 | RDYS_BAS_INCOMESORT 中 FISCAL_YEAR 为 2021 的数据 | WHERE FISCAL_YEAR = 2021 |

## 比较运算

| # | 问题 | 预期目标 |
|---|------|----------|
| 44 | RDYS_BAS_EXPFUNC 中 LEVEL_NO 大于 2 的记录 | WHERE LEVEL_NO > 2 |
| 45 | RDYS_BAS_MOFDIV 中 LEVEL_NO 小于等于 2 的 | WHERE LEVEL_NO <= 2 |
| 46 | 查询 IS_LEAF 不等于 1 的记录 | WHERE IS_LEAF <> 1 或 != 1 |

## 模糊匹配 LIKE

| # | 问题 | 预期目标 |
|---|------|----------|
| 47 | 查询 RDYS_BAS_EXPFUNC 中 EXP_FUNC_NAME 包含"教育"的记录 | WHERE EXP_FUNC_NAME LIKE '%教育%' |
| 48 | 查询支出功能分类中名称包含"交通"的数据 | search_schema → describe → WHERE EXP_FUNC_NAME LIKE '%交通%' |
| 49 | RDYS_BAS_MOFDIV 中 MOF_DIV_NAME 以"综合"开头的 | WHERE MOF_DIV_NAME LIKE '综合%' |
| 50 | 收入分类表中名称包含"税"的有哪些 | search_schema("收入") → describe → WHERE INCOME_SORT_NAME LIKE '%税%' |
| 51 | 查找支出名称中包含"公路"的记录 | WHERE EXP_FUNC_NAME LIKE '%公路%' |

## 多条件 AND/OR

| # | 问题 | 预期目标 |
|---|------|----------|
| 52 | 查询 LEVEL_NO 为 3 且 IS_ENABLED 为 1 的支出分类 | WHERE LEVEL_NO = 3 AND IS_ENABLED = 1 |
| 53 | RDYS_BAS_EXPFUNC 中 FISCAL_YEAR 为 2021 且 LEVEL_NO 大于 1 的 | WHERE FISCAL_YEAR = 2021 AND LEVEL_NO > 1 |
| 54 | 查询 MOF_DIV_CODE 为 '130000000' 且 IS_LEAF 为 1 且已启用的 | WHERE MOF_DIV_CODE = '130000000' AND IS_LEAF = 1 AND IS_ENABLED = 1 |
| 55 | LEVEL_NO 为 2 或 3 的记录 | WHERE LEVEL_NO IN (2, 3) 或 LEVEL_NO = 2 OR LEVEL_NO = 3 |

## 排序 ORDER BY

| # | 问题 | 预期目标 |
|---|------|----------|
| 56 | 查询支出分类，按 LEVEL_NO 从小到大排列 | ORDER BY LEVEL_NO ASC |
| 57 | 查询 RDYS_BAS_MOFDIV，按 UPDATE_TIME 倒序显示前10条 | ORDER BY UPDATE_TIME DESC，ROWNUM <= 10 |
| 58 | 按 FISCAL_YEAR 降序，显示前5条 | ORDER BY FISCAL_YEAR DESC，ROWNUM <= 5 |

## 组合查询（筛选 + 排序 + 限制）

| # | 问题 | 预期目标 |
|---|------|----------|
| 59 | 查询已启用的支出分类，按级别排序，只要前10条 | WHERE IS_ENABLED = 1 ORDER BY LEVEL_NO ASC + ROWNUM <= 10 |
| 60 | 2021年的收入分类中包含"企业"的，按名称排序前5条 | search_schema → describe → WHERE FISCAL_YEAR = 2021 AND INCOME_SORT_NAME LIKE '%企业%' ORDER BY INCOME_SORT_NAME，ROWNUM <= 5 |
| 61 | 财政部门划分表中 LEVEL_NO=3 且包含"区"的记录 | describe → WHERE LEVEL_NO = 3 AND MOF_DIV_NAME LIKE '%区%' |

## 模糊场景——从描述到条件查询

| # | 问题 | 预期目标 |
|---|------|----------|
| 62 | 查询支出分类表中所有和"教育"相关的已启用记录 | search_schema("支出") → describe RDYS_BAS_EXPFUNC → WHERE EXP_FUNC_NAME LIKE '%教育%' AND IS_ENABLED = 1 |
| 63 | 财政部门划分表中，看看有哪些"开发区" | search_schema → describe RDYS_BAS_MOFDIV → WHERE MOF_DIV_NAME LIKE '%开发区%' |
| 64 | 收入分类中，2021年有哪些税种的收入 | search_schema("收入") → describe → WHERE FISCAL_YEAR = 2021 AND INCOME_SORT_NAME LIKE '%税%' |

## 边界测试

| # | 问题 | 预期目标 |
|---|------|----------|
| 65 | 查询 EXP_FUNC_NAME 包含"火星"的记录 | 执行查询，返回0行，告知用户无匹配 |
| 66 | 查询 LEVEL_NO 等于 99 的记录 | 返回0行或极少数 |
| 67 | 按不存在的列筛选 | Agent 应先 describe_table 确认列名，避免盲目查询 |

