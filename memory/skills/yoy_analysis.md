# 复杂查询技能 — 同比分析与异常检测

## 触发条件
用户问"增长/下降/变化/异常/和去年比/哪个最快/哪个最慢"等对比性问题。

## 查询模式

### 模式1: 单地区同比
用户："河北1月收入比去年涨了还是跌了"
→ 定位表 → describe 确认列 → 选 BYS_JE, BYS_SNTYS, BYS_TBE, BYS_TBB
→ `WHERE RG_NAME='河北省' AND YEAR_MONTH='202501' AND XM_NAME LIKE '%合计%'`
→ 解读：BYS_TBE 为正=增长，为负=下降；BYS_TBB 为增幅百分比

### 模式2: 多地区同比排名
用户："哪些地区收入同比下降了"
→ `WHERE BYS_TBE < 0 AND XM_NAME LIKE '%合计%' AND RG_NAME NOT LIKE '%本级%'`
→ 嵌套子查询先 ORDER BY BYS_TBE ASC，外层 ROWNUM 限制

### 模式3: 阈值筛选
用户："增长超过10%的地区"
→ `WHERE BYS_TBB > 10`
用户："下降超过5千万的"
→ `WHERE BYS_TBE < -50000000`（注意单位，数据库存的是元）

### 模式4: 异常检测
用户："有没有收入特别异常的"
→ 计算所有地区的 BYS_TBB，找出绝对值最大的几个（正负两端）
→ `ORDER BY ABS(BYS_TBB) DESC`（达梦支持 ABS 函数）

### 模式5: 跨期对比
用户："这个月和上个月比"
→ 识别为环比（非同比），说明系统当前支持同比对比
→ 如需环比可分别查两个月的 BYS_JE 自行计算差值

## 解读话术

- BYS_TBE > 0: "同比增长了 XX 万元"
- BYS_TBE < 0: "同比下降了 XX 万元"
- BYS_TBB > 0: "增幅为 XX%"
- BYS_TBB < 0: "降幅为 XX%"
- 展示时用表格，包含本月数、上年同期数、增减额、增减率四列
