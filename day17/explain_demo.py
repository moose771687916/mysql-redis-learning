# -*- coding: utf-8 -*-
"""
MySQL 执行计划 EXPLAIN 演示（Day 17）
=====================================
EXPLAIN = MySQL 的"攻略书"：每条 SQL 执行前，先看它打算怎么干
  type    = 查找方式（好→坏：const > ref > range > index > ALL）
  rows    = 估算要翻多少行
  key     = 实际用到的索引
  Extra   = 额外信息（Using index = 索引全覆盖，最爽）

演示 6 个场景 + 真实耗时：
  A. 无索引查询   → type=ALL  全表翻 10 万行（慢！）
  B. 建索引再查   → type=ref   走索引目录
  C. 主键直查     → type=const 直接定位 1 行（最快）
  D. 唯一索引     → type=const
  E. 范围查询     → type=range
  F. 覆盖索引     → Extra: Using index（不用回表，最爽）
  G. 索引失效     → 函数包裹 / 模糊搜索 → 又变全表扫！

运行：python explain_demo.py
前提：MySQL 已启动
"""

import time
import random
import pymysql

N = 100000        # 造 10 万条（够看出差距，又不至于等太久）

conn = pymysql.connect(host="127.0.0.1", user="root", password="root123",
                       database="my_first_db", charset="utf8mb4")
cur = conn.cursor()

# ① 建表 + 造 10 万条
cur.execute("DROP TABLE IF EXISTS demo_user")
cur.execute("""
    CREATE TABLE demo_user (
        id INT PRIMARY KEY AUTO_INCREMENT,
        username VARCHAR(50),
        age INT,            -- 一开始【没有】索引
        email VARCHAR(80),  -- 唯一索引
        note VARCHAR(100)
    )
""")
print(f"📦 批量造 {N} 条数据中...")
random.seed(42)
rows = [(f"user_{i}", random.randint(1, 100), f"u{i}@test.com", "测试") for i in range(1, N + 1)]
cur.executemany("INSERT INTO demo_user (username, age, email, note) VALUES (%s, %s, %s, %s)", rows)
conn.commit()
print(f"   ✅ 造完 {N} 条\n")


def explain(sql):
    """跑 EXPLAIN 并格式化输出关键字段"""
    cur.execute("EXPLAIN " + sql)
    r = cur.fetchone()
    # MySQL 8.0 列序: id, select_type, table, partitions, type, possible_keys, key, key_len, ref, rows, filtered, Extra
    return {
        "type": r[4], "key": r[6], "rows": r[9], "extra": r[11]
    }


def timed(sql, repeat=3):
    """测真实耗时（毫秒）"""
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        cur.execute(sql)
        cur.fetchall()
        times.append((time.perf_counter() - t0) * 1000)
    return sum(times) / len(times)


def show(title, sql):
    e = explain(sql)
    ms = timed(sql)
    print(f"{title}")
    print(f"   EXPLAIN → type={e['type']:<7} key={str(e['key']):<10} 估算翻 {e['rows']} 行"
          f"  Extra={e['extra']}")
    print(f"   真实耗时：{ms:8.2f} 毫秒")
    print()
    return ms

print("=" * 64)
print("场景 A：无索引查询  WHERE age = 77（普通列，没建索引）")
print("=" * 64)
a_ms = show("🔍 A", "SELECT * FROM demo_user WHERE age = 77")

print("🔨 给 age 建索引：CREATE INDEX idx_age ON demo_user(age)")
cur.execute("CREATE INDEX idx_age ON demo_user(age)")
conn.commit()
print("   建完索引，同样的查询再看：\n")

print("=" * 64)
print("场景 B：有索引查询  WHERE age = 77（走索引目录）")
print("=" * 64)
b_ms = show("⚡ B", "SELECT * FROM demo_user WHERE age = 77")

print("=" * 64)
print("场景 C：主键直查  WHERE id = 50000（主键自带索引）")
print("=" * 64)
show("🎯 C", "SELECT * FROM demo_user WHERE id = 50000")

print("=" * 64)
print("场景 D：唯一索引  WHERE email = 'u50000@test.com'")
print("=" * 64)
print("🔨 先建唯一索引：CREATE UNIQUE INDEX idx_email ON demo_user(email)")
cur.execute("CREATE UNIQUE INDEX idx_email ON demo_user(email)")
conn.commit()
print("   建完，再 EXPLAIN：\n")
show("📌 D", "SELECT * FROM demo_user WHERE email = 'u50000@test.com'")

print("=" * 64)
print("场景 E：范围查询  WHERE age BETWEEN 70 AND 80（索引范围扫）")
print("=" * 64)
show("📐 E", "SELECT * FROM demo_user WHERE age BETWEEN 70 AND 80")

print("=" * 64)
print("场景 F：覆盖索引  SELECT age WHERE age=77（只查索引列，不用回表）")
print("=" * 64)
show("🚀 F", "SELECT age FROM demo_user WHERE age = 77")

print("=" * 64)
print("场景 G：索引失效 ①  WHERE age + 1 = 78（函数包裹索引列）")
print("=" * 64)
show("💥 G1", "SELECT * FROM demo_user WHERE age + 1 = 78")

print("=" * 64)
print("场景 H：索引失效 ②  WHERE username LIKE '%user_5%'（前后模糊）")
print("=" * 64)
show("💥 H", "SELECT * FROM demo_user WHERE username LIKE '%user_5%'")

# ===== 汇总 =====
print("=" * 64)
print("📊 汇总：type 从好到坏排序")
print("=" * 64)
print("""
  const  直接定位（主键/唯一）      —— 最快，翻 1 行
  ref    普通索引等值               —— 翻一小撮
  range  索引范围查询               —— 翻一段
  index  全索引扫描                 —— 也翻很多
  ALL    全表扫描                   —— 最慢，翻 10 万行
""")
print(f"真实对比：A 无索引 {a_ms:.1f} 毫秒（翻 10 万行）"
      f" vs B 有索引 {b_ms:.1f} 毫秒（翻 975 行）—— 快 {a_ms/b_ms:.0f} 倍")
print()
print("索引失效三兄弟：函数包裹（age+1）、前模糊（LIKE '%xx'）、隐式转换")

# 清理
cur.execute("DROP TABLE IF EXISTS demo_user")
conn.commit()
conn.close()
print("🗑️ 测试表已删除（教学库保持干净）")
