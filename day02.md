# Day 2・建表的正确姿势：主键、约束、数据类型

> 日期：2026-10-10~11・主题：让数据库 "有规矩"—— 拒绝坏数据
> 前置：Day 1 已完成（建库建表增删改查 + Python 读写）



***

## 一、今日成果（一句话）

**从 "能存数据的表" 升级到 "有规矩的表"—— 数据库学会了拒绝重复、负数、空值等坏数据，并亲手验证了 SQL 注入防护。**



***

## 二、为什么昨天的表不行



| 毛病          | 后果                   |
| ----------- | -------------------- |
| id 没有主键     | 可以插两条 id=1 的数据，系统分不清 |
| 没有 CHECK    | 年龄可以是 -5 岁           |
| 没有 NOT NULL | 姓名可以空着               |

数据库解决这些问题靠三样武器：**主键、约束、数据类型**。



***

## 三、今天学到的核心概念



1. **主键 PRIMARY KEY** = 每行数据的身份证号：不能重复、不能为空、一张表只能有一个。

* 黄金搭档：`AUTO_INCREMENT` 自动发号（1、2、3...），id 不用自己填。

1. **约束（给列立规矩）**：

* `NOT NULL`：必须有值

* `UNIQUE`：不能重复（如邮箱）

* `DEFAULT 值`：没填就用默认（如 `CURRENT_TIMESTAMP` = 当前时间）

* `CHECK (条件)`：值必须满足条件（如 `age >= 0`）

1. **常用数据类型**：`INT` 整数 / `VARCHAR(n)` 短文本 / `DECIMAL(10,2)` 精确小数（钱）/ `DATETIME` 日期时间 / `TEXT` 长文本 / `BOOLEAN` 真假。

2. **参数化（防 SQL 注入）**：用 `%s` 占位符 + 元组传值，数据库把用户输入永远当 "值" 处理，不当 "命令"—— 后端最重要的安全习惯。

3. **AUTO\_INCREMENT 的坑**：发号机在 "尝试插入" 时就消耗号码，插入失败号也不回收（所以被拒的小李耗掉了 3，下一条是 4）。



***

## 四、今日实操全记录（照着可复现）

### 4.1 建一张正规表



```
USE my_first_db;

CREATE TABLE student2 (
  id INT PRIMARY KEY AUTO_INCREMENT,      -- 主键 + 自动编号
  name VARCHAR(50) NOT NULL,              -- 姓名必须有
  age INT CHECK (age >= 0),               -- 年龄不能为负
  email VARCHAR(100) UNIQUE,              -- 邮箱不能重复
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP  -- 不填自动记时间
);
```

### 4.2 插入数据，看数据库怎么拒绝坏数据



```
INSERT INTO student2 (name, age, email) VALUES ('小明', 19, 'ming@test.com');  -- 成功
INSERT INTO student2 (name, age) VALUES ('小红', 17);                          -- 成功（email 允许空）
INSERT INTO student2 (name, age, email) VALUES ('小明', 20, 'ming@test.com');  -- ERROR 1062：邮箱重复，拒绝
INSERT INTO student2 (name, age, email) VALUES ('小李', -5, 'li@test.com');    -- ERROR 3819：年龄为负，拒绝
```

**两种报错是 "保护机制在工作" 的证明，不是失败。**

### 4.3 Python 参数化插入（insert\_student2.py）



```
cursor.execute(
    "INSERT INTO student2 (name, age, email) VALUES (%s, %s, %s)",
    (name, age, email if email else None)
)
conn.commit()
```

### 4.4 最终数据（2026-10-11 定格）



| id | name | age | email         | created\_at         |
| -- | ---- | --- | ------------- | ------------------- |
| 1  | 小明   | 19  | ming@test.com | 2026-10-11 08:40:47 |
| 2  | 小红   | 17  | NULL          | 2026-10-11 08:40:51 |
| 4  | 小华   | 16  | hua@test.com  | 2026-10-11 08:44:24 |

（id=3 被被拒的小李消耗掉了 —— 发号不回收）



***

## 五、Day 2 速查表



| 想干什么         | 命令                                                          |
| ------------ | ----------------------------------------------------------- |
| 建带主键的表       | `CREATE TABLE 表名 (id INT PRIMARY KEY AUTO_INCREMENT, ...);` |
| 加非空          | `列名 类型 NOT NULL`                                            |
| 加唯一          | `列名 类型 UNIQUE`                                              |
| 加默认值         | `列名 类型 DEFAULT 值`                                           |
| 加检查          | `列名 类型 CHECK (条件)`                                          |
| Python 防注入插入 | `execute("...VALUES (%s,...)", (值,...))` + `conn.commit()`  |



***

## 六、今日踩坑记录



1. **ERROR 2003 (10061)**：MySQL 没启动（重启电脑后不会自启）→ 双击 `start_mysql.bat`。

2. **ERROR 1046 No database selected**：建表前忘了 `USE my_first_db;` → 先选库再操作。

3. **id 跳号**：被 CHECK 拒绝的插入也会消耗 AUTO\_INCREMENT 号码 → 正常现象，不用管。



***

## 七、下一步（Day 3 预告）



1. **多表设计**：学会把数据拆到多张表（比如：学生表 + 班级表 + 成绩表），理解 "一对一 / 一对多" 关系。

2. **JOIN 联表查询**：一张 SELECT 把多张表的数据拼起来 —— 这是 SQL 最有用的能力。

3. 或者先来 **Redis 入门**：`SET` / `GET` / `EXPIRE`，理解 "缓存"。

4. 之后做**学生管理系统小项目**，把三天学的全串起来。



***

## 八、给未来的自己



* 每张表都要有主键（身份证）。

* 写 Python SQL 永远用参数化（% s），不要字符串拼接 —— 防 SQL 注入。

* 数据库的 "报错" 很多时候是保护机制，读懂报错 = 学会和数据库对话。

* id 跳号是正常的，别纠结。