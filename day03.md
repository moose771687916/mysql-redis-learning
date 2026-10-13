# Day 3 · 多表设计与 JOIN 联表查询

> 日期：2026-10-11 · 主题：把数据拆到多张表，再用一条查询拼回来
> 前置：Day 2 已掌握主键、约束、数据类型、参数化

---

## 一、今日成果（一句话）

**学会了真实系统的地基——多表设计（外键挂钩）+ JOIN 联表查询，用一条 SQL 把三张表拼成完整成绩单。**

---

## 二、为什么一张表不够

| 一张表塞所有 | 毛病 |
|---|---|
| "软件1班"重复存 | 冗余——改名要改多处 |
| 没考的科目空着 | 空值泛滥 |
| 考 N 门就要加 N 列 | 没法扩展 |

**正确做法**：分柜子存（班级/学生/成绩三张表），用"编号"互相挂钩。

---

## 三、核心概念

1. **外键 FOREIGN KEY**：规定"这个编号必须是另一张表里真实存在的"。
   - 插一个不存在的班级号 → 数据库报错拒绝（防"孤儿数据"）
   - 类比：招生办不收"填了不存在班级号"的报名表
2. **关系类型**：一个班级 ↔ 多个学生（一对多）；一个学生 ↔ 多门成绩（一对多）。
3. **JOIN 的本质**：把两张表按共同列"对齐拼接"（`ON 表A.外键 = 表B.主键`）。
4. **ORDER BY 列名 DESC**：按某列排序（DESC 降序 / ASC 升序默认）。

---

## 四、今日实操全记录

### 4.1 建三张表

```sql
CREATE TABLE class (                       -- 班级表
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE student3 (                    -- 学生表（带外键）
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(50) NOT NULL,
  age INT CHECK (age >= 0),
  class_id INT,
  FOREIGN KEY (class_id) REFERENCES class(id)
);

CREATE TABLE score (                       -- 成绩表（带外键）
  id INT PRIMARY KEY AUTO_INCREMENT,
  student_id INT NOT NULL,
  subject VARCHAR(50) NOT NULL,
  score DECIMAL(5,2) CHECK (score >= 0 AND score <= 100),
  FOREIGN KEY (student_id) REFERENCES student3(id)
);
```

### 4.2 插入数据

```sql
INSERT INTO class (name) VALUES ('软件1班'), ('软件2班');
INSERT INTO student3 (name, age, class_id) VALUES ('小明', 19, 1), ('小红', 17, 1), ('小华', 16, 2);
INSERT INTO score (student_id, subject, score) VALUES (1, '数学', 90), (1, '英语', 85), (2, '数学', 78), (3, '英语', 92);
```

### 4.3 外键守门演示（预期报错）

```sql
INSERT INTO student3 (name, age, class_id) VALUES ('坏人', 20, 99);
-- ERROR 1452：班级 99 不存在，外键拒绝
```

### 4.4 JOIN 联表查询（最终成果）

```sql
-- 学生 + 班级
SELECT student3.name, class.name
FROM student3
JOIN class ON student3.class_id = class.id;

-- 完整成绩单（三表接力）
SELECT student3.name, class.name, score.subject, score.score
FROM score
JOIN student3 ON score.student_id = student3.id
JOIN class ON student3.class_id = class.id;

-- 成绩单按分数降序
... ORDER BY score.score DESC;
```

**最终成绩单**：

| name | name | subject | score |
|---|---|---|---|
| 小华 | 软件2班 | 英语 | 92.00 |
| 小明 | 软件1班 | 数学 | 90.00 |
| 小明 | 软件1班 | 英语 | 85.00 |
| 小红 | 软件1班 | 数学 | 78.00 |

---

## 五、速查表

| 想干什么 | 命令 |
|---|---|
| 加外键 | 建表里写 `FOREIGN KEY (列) REFERENCES 表(主键)` |
| 两表拼接 | `SELECT 表A.列, 表B.列 FROM 表A JOIN 表B ON 表A.外键 = 表B.主键;` |
| 三表拼接 | 再连一条 `JOIN 表C ON ...`（接力） |
| 排序 | `ORDER BY 列名 DESC;`（降序）/ `ASC`（升序） |

**JOIN 模板（背下来）**：`SELECT A.列, B.列 FROM A JOIN B ON A.外键 = B.主键;`

---

## 六、今日踩坑/要点

1. 外键报错 `ERROR 1452` = 指向了不存在的编号——是保护机制，不是失败。
2. JOIN 的 `ON` 条件写错会导致结果错乱或行数变多——先想清楚"哪两列对齐"。
3. 一个学生考多门 = 成绩表多行（一对多的体现），不是加列。

---

## 七、下一步（Day 4 预告）

1. **聚合查询**：`COUNT` 数人数、`AVG` 算平均分、`GROUP BY` 分组统计（"每个班平均分"这种问题）
2. **Redis 入门**：`SET` / `GET` / `EXPIRE`，理解"缓存"
3. **学生管理系统小项目**：把三天所学全串起来（Python + 多表 + 参数化）

---

## 八、给未来的自己

- 设计表先问"有哪些实体"→ 一张表一个实体 → 用外键挂钩。
- JOIN 是 SQL 最值钱的能力，模板背熟。
- 外键报错、约束报错 = 数据库在保护数据，看懂报错就是懂数据库。
