# -*- coding: utf-8 -*-
"""
MySQL 事务隔离 + 行锁演示（Day 13）
====================================
用两个连接模拟 A、B 两个人同时操作同一条数据：
  演示1：可重复读（MySQL 默认）——A 开事务后，画面全程不变
  演示2：行锁——A 锁住一行，B 想改只能排队等

运行：python isolation_demo.py
前提：MySQL 已启动
"""

import threading
import time
import pymysql


def mkconn():
    return pymysql.connect(host="127.0.0.1", user="root", password="root123",
                           database="my_first_db", charset="utf8mb4", autocommit=True)


# ===== 准备测试表（独立连接，用完即关）=====
cur = mkconn().cursor()
cur.execute("DROP TABLE IF EXISTS demo_lock")
cur.execute("CREATE TABLE demo_lock (id INT PRIMARY KEY, name VARCHAR(50), stock INT)")
cur.execute("INSERT INTO demo_lock VALUES (1, '测试商品', 10)")
cur.execute("SELECT @@transaction_isolation")
print("当前 MySQL 隔离级别:", cur.fetchone()[0])
cur.connection.close()

# ========== 演示 1：可重复读 ==========
print()
print("=" * 50)
print("演示 1：可重复读（A 事务内画面不变）")
print("=" * 50)
A = mkconn()
B = mkconn()
ca = A.cursor()
cb = B.cursor()

A.autocommit(False)                      # A 开启事务
ca.execute("SELECT stock FROM demo_lock WHERE id=1")
print(f"① A 开事务，第一次读 stock = {ca.fetchone()[0]}")

B.autocommit(False)
cb.execute("UPDATE demo_lock SET stock=5 WHERE id=1")
B.commit()                               # B 改了库存并提交
print("② B 把库存改成 5 并提交 ✅")

ca.execute("SELECT stock FROM demo_lock WHERE id=1")
print(f"③ A 再读 stock = {ca.fetchone()[0]}  ← 还是 10！(可重复读：画面不变)")
A.commit()

ca.execute("SELECT stock FROM demo_lock WHERE id=1")
print(f"④ A 提交后再读 stock = {ca.fetchone()[0]}  ← 这时才看到 5")

A.close()
B.close()

# ========== 演示 2：行锁 ==========
print()
print("=" * 50)
print("演示 2：行锁（A 锁住一行，B 只能排队等）")
print("=" * 50)
A2 = mkconn()
B2 = mkconn()
ca2 = A2.cursor()
cb2 = B2.cursor()

A2.autocommit(False)
ca2.execute("UPDATE demo_lock SET stock=stock-1 WHERE id=1")   # A 锁住这一行（未提交）
print("① A 锁住了这一行（改了但没提交）")


def b_update():
    cb2.execute("UPDATE demo_lock SET stock=stock-1 WHERE id=1")  # 会被锁挡住
    B2.commit()
    cb2.execute("SELECT stock FROM demo_lock WHERE id=1")
    print(f"③ B 抢到锁，更新成功！stock = {cb2.fetchone()[0]}")


t = threading.Thread(target=b_update)
t.start()
time.sleep(2)
print("② B 想改同一行 → 被锁挡住，正在排队等…（2 秒了还没动静）")

A2.commit()                              # A 提交，释放锁
print("   A 提交了（释放锁）→ B 立刻继续")
t.join()
B2.commit()
A2.close()
B2.close()

# ===== 清理（独立连接，确保前面连接都关了）=====
clean = mkconn()
clean.cursor().execute("DROP TABLE IF EXISTS demo_lock")
clean.commit()
clean.close()
print()
print("🗑️ 测试表已清理")
