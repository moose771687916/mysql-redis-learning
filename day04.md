# Day 4 · 聚合查询：COUNT / AVG / GROUP BY

> 日期：2026-10-11 · 主题：把一堆行"汇总"成一行的统计能力
> 前置：Day 3 已掌握多表设计与 JOIN

---

## 一、今日成果（一句话）

**SQL 查询能力全部通关——学会用 COUNT/AVG/SUM/MAX/MIN 汇总数据，用 GROUP BY 按类别统计，一条查询直接回答"平均分多少、每科多少、每人总分多少"这类真实报表问题。**

---

## 二、核心概念

1. **聚合函数（把很多行压成一行汇总）**：
   - `COUNT(*)` 数行数（多少人/多少条）
   - `AVG(列)` 平均值（平均分）
   - `SUM(列)` 求和（总分）
   - `MAX(列)` / `MIN(列)` 最大 / 最小
2. **GROUP BY 列名**：按某列"分堆"，每堆各自汇总一次。
3. **为什么快**：计算在数据库服务端内部完成，只返回汇总结果——数据越多，价值越大（不用把几百万行拉到程序里算）。
4. 聚合可以配合 JOIN（先拼表再分组）和 ORDER BY（按汇总结果排序）。

---

## 三、今日实操全记录

```sql
-- ① 学生总数
SELECT COUNT(*) FROM student3;              -- 3

-- ② 全部成绩平均分
SELECT AVG(score) FROM score;               -- 86.250000

-- ③ 最高分 / 最低分
SELECT MAX(score), MIN(score) FROM score;   -- 92.00 / 78.00

-- ④ 按科目分组看平均分
SELECT subject, AVG(score) FROM score GROUP BY subject;
-- 数学 84.000000 / 英语 88.500000

-- ⑤ 每个学生总成绩（JOIN + GROUP BY + ORDER BY 三件套）
SELECT student3.name, SUM(score.score)
FROM score
JOIN student3 ON score.student_id = student3.id
GROUP BY student3.id
ORDER BY SUM(score.score) DESC;
-- 小明 175.00 / 小华 92.00 / 小红 78.00
```

**模板**：`SELECT 分组列, 聚合函数(列) FROM 表 [JOIN ...] GROUP BY 分组列 [ORDER BY 聚合结果];`

---

## 四、速查表

| 想干什么 | 命令 |
|---|---|
| 数行数 | `SELECT COUNT(*) FROM 表;` |
| 平均值 | `SELECT AVG(列) FROM 表;` |
| 求和 | `SELECT SUM(列) FROM 表;` |
| 最大/最小 | `SELECT MAX(列), MIN(列) FROM 表;` |
| 按类统计 | `... GROUP BY 分类列;` |
| 按汇总排序 | `... ORDER BY 聚合函数(列) DESC;` |

---

## 五、下一步（Day 5 预告）

1. **学生管理系统小项目**：把 4 天所学全串成一个小程序（Python + 参数化 + 多表 + 聚合统计）——第一个"能交货"的完整作品
2. **Redis 入门**：SET / GET / EXPIRE，理解"缓存"为什么是数据库的好搭档

---

## 六、给未来的自己

- 报表问题 = 聚合函数 + GROUP BY，套模板就能写。
- "每个XX的平均/总数" = GROUP BY XX。
- 数据量大时，让数据库算，别把数据拉回程序算。
