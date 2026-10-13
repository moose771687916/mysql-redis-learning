# -*- coding: utf-8 -*-
"""
MySQL 乐观锁演示（Day 13）
==========================
A、B 同时读到 version=1，都去改库存——A 先提交成功，B 提交时发现
版本已变成 2，WHERE version=1 匹配 0 行 → 被拒绝。

对比悲观锁（isolation_demo 演示2）：悲观锁是"排队等"，
乐观锁是"不排队，直接对账，对不上就失败"。

运行：python optimistic_lock_demo.py
前提：MySQL 已启动
"""

import pymysql


def mkconn():
    return pymysql.connect(host="127.0.0.1", user="root", password="root123",
                           database="my_first_db", charset="utf8mb4", autocommit=True)


# ===== 准备：商品 stock=10, version=1 =====
cur = mkconn().cursor()
cur.execute("DROP TABLE IF EXISTS demo_opt")
cur.execute("CREATE TABLE demo_opt (id INT PRIMARY KEY, stock INT, version INT)")
cur.execute("INSERT INTO demo_opt VALUES (1, 10, 1)")
print("初始状态：stock=10, version=1")
cur.connection.close()

# ===== A、B 两个连接 =====
A = mkconn()
B = mkconn()
ca = A.cursor()
cb = B.cursor()

# ① A、B 都读到当前版本（version=1）——像两个人同时点购买
print()
print("① A、B 同时读：stock=10, version=1（两个人都看到了这一版）")

# ② A 提交：带着 version=1 去改，成功
n = ca.execute("UPDATE demo_opt SET stock=9, version=2 WHERE id=1 AND version=1")
print(f"② A 提交：UPDATE ... WHERE version=1 → 影响 {n} 行 → A 下单成功 ✅（库存 10→9，版本 1→2）")

# ③ B 提交：还带着老的 version=1 去改 → 对不上
n2 = cb.execute("UPDATE demo_opt SET stock=9, version=2 WHERE id=1 AND version=1")
print(f"③ B 提交：UPDATE ... WHERE version=1 → 影响 {n2} 行 → B 被拒绝 ❌（版本已经是 2，不是 1）")

# ④ 业务层怎么处理 B？—— 提示失败或自动重试
print()
if n2 == 0:
    print("④ B 的处理（业务代码）: 匹配 0 行 → 返回『商品已被抢光，请重试』")
    print("   → B 的订单【从未生成】，库存没有被 B 动过（是 A 买走的）")
else:
    print("④ B 竟然成功了？？不可能，除非 version 没变")

# ⑤ 查最终状态
c2 = mkconn()
cur2 = c2.cursor()
cur2.execute("SELECT stock, version FROM demo_opt WHERE id=1")
stock, version = cur2.fetchone()
print()
print(f"最终：stock={stock}, version={version} —— 只有 A 的改动生效")

# ===== 清理 =====
cur2.execute("DROP TABLE IF EXISTS demo_opt")
c2.commit()
c2.close()
A.close()
B.close()
print()
print("🗑️ 测试表已清理")
