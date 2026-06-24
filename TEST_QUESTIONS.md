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

> 阶段2完整测试问题已移至 [STAGE2_TESTS.md](STAGE2_TESTS.md)，共56题覆盖8个子场景。
> 所有问题均为预算分析人员真实口语，不含英文表名/列名/编码。
> Agent 必须自动完成口语→表/列/值的映射。

