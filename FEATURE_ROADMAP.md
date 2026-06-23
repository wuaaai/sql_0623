# Text-to-SQL 功能目标渐进计划

## 总目标

用户用自然语言描述需求 → Agent自动理解数据库结构 → 生成正确SQL → 执行并返回结果

## 功能阶段 (每个阶段都是可独立交付、可验收的功能增量)

---

### 阶段1: 单表查询 — "能查了"

**用户能做什么**: 连接数据库，查询单张表的数据

**验收用例**:
```
用户: 查询users表的所有数据
Agent: 自动连接数据库 → 找到users表 → 执行 SELECT * FROM users → 返回结果

用户: 看看products表的前10行
Agent: 自动探索 → 执行 SELECT * FROM products LIMIT 10
```

**需要的原子工具**:
- `connect_db` — 连接数据库
- `list_tables` — 列出所有表
- `run_sql` — 执行查询

**验证条件**: 用户说"查XX表"，Agent能正确返回数据

---

### 阶段2: 条件筛选 — "能筛选了"

**用户能做什么**: 按条件过滤数据，指定返回哪些列

**验收用例**:
```
用户: 查询年龄大于30的用户姓名和邮箱
Agent: 生成 SELECT name, email FROM users WHERE age > 30

用户: 找出状态为"已发货"且金额超过1000的订单
Agent: 生成 SELECT * FROM orders WHERE status = '已发货' AND amount > 1000
```

**需要的原子工具**:
- `describe_table` — 查看表结构（列名、类型，Agent才知道有哪些列可用）

**验证条件**: 用户描述筛选条件，Agent能正确生成WHERE子句

---

### 阶段3: 聚合统计 — "能统计了"

**用户能做什么**: 分组统计、排序、聚合计算

**验收用例**:
```
用户: 统计每个部门的员工人数
Agent: 生成 SELECT dept_id, COUNT(*) FROM employees GROUP BY dept_id

用户: 销售额最高的10个产品，从高到低排列
Agent: 生成 SELECT product_name, SUM(amount) as total 
       FROM orders GROUP BY product_name ORDER BY total DESC LIMIT 10
```

**需要的原子工具**:
- `sample_data` — 抽样查看数据（理解列的含义和取值范围）

**验证条件**: 用户说"统计/汇总/排名"，Agent能生成带GROUP BY/ORDER BY/聚合函数的SQL

---

### 阶段4: 多表关联 — "能关联了"

**用户能做什么**: 跨多张表的关联查询

**验收用例**:
```
用户: 列出每个订单的客户名称和产品名称
Agent: 先查orders/customers/products三张表的结构
      → 发现orders有customer_id和product_id
      → 生成 SELECT c.name, p.name, o.amount, o.created_at
         FROM orders o
         JOIN customers c ON o.customer_id = c.id
         JOIN products p ON o.product_id = p.id

用户: 哪些客户从来没有下过订单
Agent: 生成 SELECT * FROM customers c
       LEFT JOIN orders o ON c.id = o.customer_id
       WHERE o.id IS NULL
```

**需要的原子工具**:
- `get_relationships` — 获取外键关系（加速Agent发现表之间的关联）
- `search_schema` — 按关键词搜索列名（如搜索"客户"能找到customer_id）

**验证条件**: 用户的问题涉及2张以上表，Agent能正确生成JOIN

---

### 阶段5: 复杂业务查询 — "能处理复杂问题了"

**用户能做什么**: 子查询、窗口函数、时间范围等复杂场景

**验收用例**:
```
用户: 查询上个月每个类别中销售额排名前3的产品
Agent: 生成带窗口函数 ROW_NUMBER() OVER (PARTITION BY category ORDER BY SUM(amount) DESC)

用户: 找出薪资高于部门平均薪资的员工
Agent: 生成子查询 SELECT * FROM employees e1
       WHERE salary > (SELECT AVG(salary) FROM employees e2 WHERE e1.dept_id = e2.dept_id)

用户: 最近30天注册但从未登录过的用户
Agent: 生成 LEFT JOIN + IS NULL + 时间条件
```

**需要的原子工具**:
- `explain_sql` — 获取执行计划（验证SQL是否正确、性能如何）
- `validate_sql` — 语法校验（生成后先验证再执行）

**验证条件**: 包含子查询/窗口函数/CTE的业务问题能正确解答

---

### 阶段6: 多轮对话 & 上下文记忆 — "能连续聊了"

**用户能做什么**: 连续提问，Agent记住上下文，不需要每次重复说明

**验收用例**:
```
用户: 看看数据库里有哪些表
Agent: [列出所有表]

用户: 订单表是什么样的
Agent: [显示orders表结构 + 样例数据]

用户: 哪个客户的订单最多
Agent: 自动关联customers和orders，统计并排序

用户: 把他的详细信息也显示出来
Agent: 理解"他"指的是上一步查出的客户，正确追加查询
```

**需要的原子工具**:
- `update_working_checkpoint` — 工作记忆（记录当前会话探索过的表、发现的关系）

**验证条件**: 3轮以上的连续对话，Agent能正确理解代词和上下文

---

### 阶段7: 自动纠错 & 结果解释 — "能自我修正了"

**用户能做什么**: SQL出错时Agent自动分析错误并修正；执行结果附带解释

**验收用例**:
```
用户: 查询上个月每天的订单总额
Agent: 生成SQL → 执行 → 报错"column 'month' not found"
      → Agent读错误信息 → 探索表结构 → 发现列名是'created_at'
      → 修正: SELECT DATE(created_at), SUM(amount) ...
      → 执行成功 → 返回结果 + 解释"按created_at日期分组统计amount总和"

用户: 产品和库存的关系是什么
Agent: 探索schema → 发现products和inventory通过product_id关联
      → 向用户说明"products表通过product_id关联到inventory表，
         可以用以下SQL查询各产品的库存情况: ..."
```

**需要的原子工具**:
- 错误自动分析（解析数据库错误信息，映射到schema问题）
- 结果解释（用自然语言说明SQL做了什么）

**验证条件**: SQL执行失败时Agent能自动修正1-2次后成功

---

### 阶段8: 写操作 & 安全确认 — "能安全写入了"

**用户能做什么**: 通过自然语言对数据库进行INSERT/UPDATE操作，危险操作需确认

**验收用例**:
```
用户: 把张三的邮箱改成 zhangsan@example.com
Agent: 生成 UPDATE users SET email = 'zhangsan@example.com' WHERE name = '张三'
      → 弹确认: "将对users表执行UPDATE，影响1行，是否确认？"
      → 用户确认后执行

用户: 删除所有已取消且超过1年的订单
Agent: 生成SQL → 弹确认: "将删除XX行数据，是否确认？" → 确认后执行
```

**需要的原子工具**:
- `run_write_sql` — 写操作执行（内部有安全校验，拦截DROP/TURNCATE/不带WHERE的DELETE）
- `ask_user` — 向用户确认危险操作

**验证条件**: 写操作必须经过确认流程，危险SQL被自动拦截

---

## 功能递进总览

```
阶段1: 单表查询       ─── SELECT *
阶段2: 条件筛选       ─── WHERE, LIMIT, 指定列
阶段3: 聚合统计       ─── GROUP BY, ORDER BY, COUNT/SUM/AVG
阶段4: 多表关联       ─── JOIN, LEFT JOIN, 外键
阶段5: 复杂查询       ─── 子查询, 窗口函数, CTE
阶段6: 多轮对话       ─── 上下文记忆, 代词理解
阶段7: 自动纠错       ─── 错误分析, 自我修正, 结果解释
阶段8: 安全写入       ─── INSERT/UPDATE/DELETE + 确认机制
```

每个阶段在前一阶段基础上叠加新能力，所有已实现的能力不退化。
