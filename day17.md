# Day 17 · MySQL 执行计划 EXPLAIN + 索引失效

> 日期：2026-10-17 · 主题：看 MySQL 内部怎么执行 SQL（它的"攻略书"）
> 前置：Day 11 索引（目录提速 53 倍）· Day 14 并发压测

---

## 一、今日成果（一句话）

**学会用 EXPLAIN 看 MySQL 的"攻略书"——每条 SQL 执行前，先看它打算怎么干（type 查找方式、rows 估算翻多少行、key 用没用索引、Extra 额外信息），并用 10 万条数据实测 8 个场景：const/ref/range 走索引快 5 倍，索引失效三兄弟（函数包裹、前模糊、隐式转换）变回全表扫。**

---

## 二、核心概念

### A. EXPLAIN 是什么
- `EXPLAIN SELECT ...` = 让 MySQL 告诉你"这条 SQL 我打算怎么执行"
- **关键 4 字段**：
  - `type`：查找方式（好→坏：`const > ref > range > index > ALL`）
  - `rows`：估算要翻多少行（越少越快）
  - `key`：实际用到的索引（`None` = 没走索引，危险）
  - `Extra`：额外信息（`Using index` = 覆盖索引，最爽）

### B. type 五档（面试必背）
| type | 含义 | 翻多少 | 场景 |
|---|---|---|---|
| const | 直接定位 | 1 行 | 主键/唯一索引等值 |
| ref | 普通索引等值 | 一小撮 | 普通索引 WHERE 等值 |
| range | 索引范围扫 | 一段 | BETWEEN / > / < |
| index | 全索引扫描 | 很多 | 覆盖索引查询 |
| ALL | 全表扫描 | 全表 | 没索引 / 索引失效 |

### C. 索引失效三兄弟（写了就白建索引）
1. **函数包裹索引列**：`WHERE age + 1 = 78` → 索引报废
2. **前模糊搜索**：`LIKE '%user_5%'` → 索引报废（`user_5%` 后模糊没事）
3. **隐式转换**：字符串列 `WHERE phone = 123456`（数字）→ 索引报废

### D. 覆盖索引（最爽的 Extra）
只查索引列（如 `SELECT age WHERE age=77`）→ 数据全在索引目录里，**不用回表**查原数据 → 比普通索引查询还快。

---

## 三、今日实操全记录（10 万条数据实测）

| 场景 | type | key | 估算翻 | 实测耗时 |
|---|---|---|---|---|
| A 无索引 WHERE age=77 | ALL | None | 100000 行 | ~27ms ❌ |
| B 建索引后同样查询 | ref | idx_age | 975 行 | ~5ms ✅ 快 5 倍 |
| C 主键直查 WHERE id=50000 | const | PRIMARY | 1 行 | ~0.24ms 🚀 |
| D 唯一索引查 email | const | idx_email | 1 行 | ~0.31ms 🚀 |
| E 范围 BETWEEN 70 AND 80 | range | idx_age | 19678 行 | ~46ms |
| F 覆盖索引 SELECT age | ref | idx_age | 975 行 | ~1.65ms ⚡ Using index |
| G 函数包裹 age+1=78 | ALL | None | 100000 行 | ~26ms 💥 索引失效 |
| H 前模糊 LIKE '%xx%' | ALL | None | 100000 行 | ~62ms 💥 索引失效 |

---

## 四、今日踩坑/要点

1. **建了索引但没用上**：场景 D 一开始 type=ALL——因为建表时注释写着"唯一索引"但**没真建**！MySQL 只看实际的索引，不看注释。教训：`SHOW INDEX FROM 表` 确认索引真的存在。
2. **rows 是估算**：MySQL 按索引统计"猜"的，不是实际执行结果——所以 EXPLAIN 叫"计划"，不是"结果"。
3. **const > ref > range**：主键/唯一索引最猛（1 行定位）；普通索引要翻一小撮；范围查询翻一段——加索引位置很讲究。
4. **覆盖索引比普通索引还快**：`SELECT age`（只查索引列）1.65ms vs `SELECT *` 5ms——不用回表取全行。
5. **索引失效 ≠ 查询报错**：只是变回全表扫（慢），结果照样对——所以不 EXPLAIN 根本发现不了。

---

## 五、速查表

| 想干什么 | 命令/代码 |
|---|---|
| 看 SQL 执行计划 | `EXPLAIN SELECT ...`（前面加 EXPLAIN 就行） |
| 看表有哪些索引 | `SHOW INDEX FROM 表名` |
| 建普通索引 | `CREATE INDEX idx_age ON demo_user(age)` |
| 建唯一索引 | `CREATE UNIQUE INDEX idx_email ON demo_user(email)` |
| 排查 SQL 慢 | EXPLAIN → 看 `type` 是不是 ALL、`key` 是不是 None |
| 防索引失效 | 别写：`age+1`、`LIKE '%xx'`、隐式转换 |

---

## 六、一句话总结

**SQL 慢就 EXPLAIN：type=ALL 或 key=None = MySQL 在翻全表——加索引 / 改写法让它走 const/ref/range；索引失效三兄弟（函数、前模糊、隐式转换）是排查时第一个要查的坑。Day 11 教你"索引是目录"，今天教你"MySQL 怎么选目录、为什么有时不选"。**
