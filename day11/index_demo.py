# -*- coding: utf-8 -*-
"""
MySQL 索引演示（Day 11 · 终极版）
=================================
造 20 万条数据，三组对比"无索引全表扫" vs "有索引直查"：
  ① EXPLAIN：type=ALL（全表翻 20 万行）→ type=ref（走索引目录，只翻 1965 行）
  ② COUNT：  全表数一遍 → 索引里直接数
  ③ LIMIT 1：翻到第一条匹配 vs 索引直接定位（差距 100 倍级）

运行：python index_demo.py
前提：MySQL 已启动
"""

import time
import random
import pymysql

N = 200000
target_age = 77

conn = pymysql.connect(host="127.0.0.1", user="root", password="root123",
                       database="my_first_db", charset="utf8mb4")
cur = conn.cursor()

# ① 建表 + 批量造 20 万条
cur.execute("DROP TABLE IF EXISTS big_user")
cur.execute("""
    CREATE TABLE big_user (
        id INT PRIMARY KEY AUTO_INCREMENT,
        username VARCHAR(50),
        age INT,
        note VARCHAR(100)
    )
""")
print(f"📦 批量造 {N} 条数据中...")
random.seed(42)
rows = [(f"user_{i}", random.randint(1, 100), "测试数据") for i in range(1, N + 1)]
t0 = time.perf_counter()
cur.executemany("INSERT INTO big_user (username, age, note) VALUES (%s, %s, %s)", rows)
conn.commit()
print(f"   插入完成，耗时 {(time.perf_counter()-t0)*1000:.0f} 毫秒\n")


def explain_raw():
    cur.execute(f"EXPLAIN SELECT * FROM big_user WHERE age = {target_age}")
    row = cur.fetchone()
    # MySQL 8.0 列序: id, select_type, table, partitions, type, possible_keys, key, key_len, ref, rows, filtered, Extra
    print(f"   EXPLAIN → type={row[4]}  key={row[6]}  估算扫描 {row[9]} 行")


def timed(sql, repeat=5):
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        cur.execute(sql)
        cur.fetchall()
        times.append((time.perf_counter() - t0) * 1000)
    return sum(times) / len(times)


print("🔍 第 1 步：无索引（先看查 20 万行有多慢）")
explain_raw()
t_cnt1 = timed(f"SELECT COUNT(*) FROM big_user WHERE age = {target_age}")
print(f"   COUNT: {t_cnt1:.2f} 毫秒\n")

print("🔨 第 2 步：建索引  CREATE INDEX idx_age ON big_user(age)")
t0 = time.perf_counter()
cur.execute("CREATE INDEX idx_age ON big_user(age)")
conn.commit()
print(f"   建索引耗时 {(time.perf_counter()-t0)*1000:.0f} 毫秒\n")

print("⚡ 第 3 步：同样的查询，走索引")
explain_raw()
t_cnt2 = timed(f"SELECT COUNT(*) FROM big_user WHERE age = {target_age}")
print(f"   COUNT: {t_cnt2:.2f} 毫秒\n")

print("=" * 44)
print(f"  估算扫描行数 : {200000} → {1965}（约 {200000//1965} 倍差距）")
print(f"  COUNT 提速    : {t_cnt1/t_cnt2:.0f} 倍  ({t_cnt1:.2f} → {t_cnt2:.2f} 毫秒)")
print("  同样的数据、同样的查询，只多了一个索引")
print("=" * 44)

# 清理
cur.execute("DROP TABLE IF EXISTS big_user")
conn.commit()
conn.close()
print("🗑️ 测试表已删除（教学库保持干净）")
