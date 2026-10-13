# -*- coding: utf-8 -*-
"""
商城并发压测（Day 14）
======================
100 人同时抢显示器（库存 13），对比两种扣库存写法：
  BUG 版   : 先查库存 → 检查 → 无条件 UPDATE（app.py 现在的写法）
  修复版   : 一条 UPDATE ... WHERE stock >= 数量（原子防超卖）

跑法：
  python stress_test.py          # 先跑 BUG 版，看超卖
  python stress_test.py fix      # 再跑修复版，看正好 13 人

前提：MySQL 已启动
"""

import sys
import threading
import pymysql

PRODUCT_ID = 3        # 显示器
STOCK = 13            # 库存 13 件
PEOPLE = 100          # 100 人抢


def mkconn():
    return pymysql.connect(host="127.0.0.1", user="root", password="root123",
                           database="my_first_db", charset="utf8mb4", autocommit=True)


def reset():
    """复位：清掉所有 stress 测试数据，库存复位，再造 100 个测试用户"""
    cur = mkconn().cursor()
    # 清场：按 stress 用户删（订单→明细→用户），不依赖订单 id 基准线
    cur.execute("DELETE oi FROM order_item oi JOIN orders o ON oi.order_id=o.id JOIN users u ON o.user_id=u.id WHERE u.username LIKE 'stress_%%'")
    cur.execute("DELETE o FROM orders o JOIN users u ON o.user_id=u.id WHERE u.username LIKE 'stress_%%'")
    cur.execute("DELETE FROM users WHERE username LIKE 'stress_%%'")
    cur.execute("SELECT COALESCE(MAX(id),0) FROM orders")
    global base_order_id
    base_order_id = cur.fetchone()[0]
    cur.execute("UPDATE product SET stock = %s WHERE id = %s", (STOCK, PRODUCT_ID))
    # 造 100 个测试用户（外键约束：订单必须属于真实用户）
    for i in range(PEOPLE):
        cur.execute("INSERT IGNORE INTO users (username, password) VALUES (%s, 'x')",
                    (f"stress_{i}",))
    cur.execute("SELECT id FROM users WHERE username LIKE 'stress_%%' ORDER BY id LIMIT %s", (PEOPLE,))
    ids = [r[0] for r in cur.fetchall()]
    cur.connection.close()
    return ids


base_order_id = 0
success = 0
fail_reason = {"库存不足": 0, "抢光": 0, "异常": 0}
lock = threading.Lock()


def buy(user_id, use_fix):
    """模拟 app.py 的下单核心逻辑：查价查库存 → 写订单 → 写明细 → 扣库存
    必须用真事务（autocommit=False）：写订单和扣库存要么全成要么全回滚
    死锁（1213）是并发常态：生产代码必须捕获后自动重试"""
    global success
    for attempt in range(5):
        conn = pymysql.connect(host="127.0.0.1", user="root", password="root123",
                               database="my_first_db", charset="utf8mb4", autocommit=False)
        cur = conn.cursor()
        try:
            # ① 查价格和库存（跟 app.py 一模一样）
            cur.execute("SELECT price, stock FROM product WHERE id = %s", (PRODUCT_ID,))
            price, stock = cur.fetchone()
            if stock < 1:
                with lock:
                    fail_reason["库存不足"] += 1
                return

            # ② 写订单 + 明细（未提交，等扣库存成功再一起提交）
            cur.execute("INSERT INTO orders (user_id, total) VALUES (%s, %s)", (user_id, price))
            oid = cur.lastrowid
            cur.execute("INSERT INTO order_item (order_id, product_id, quantity, price) VALUES (%s, %s, 1, %s)",
                        (oid, PRODUCT_ID, price))

            # ③ 扣库存（两种写法！）
            if use_fix:
                # 修复版：一条语句 = 行锁 + 条件判断（原子！）
                n = cur.execute(
                    "UPDATE product SET stock = stock - 1 WHERE id = %s AND stock >= 1",
                    (PRODUCT_ID,))
                if n == 0:                      # 0 行受影响 = 没抢到 → 订单一起回滚
                    conn.rollback()
                    with lock:
                        fail_reason["抢光"] += 1
                    return
            else:
                # BUG 版：无条件扣（app.py 现在的写法）
                cur.execute("UPDATE product SET stock = stock - 1 WHERE id = %s", (PRODUCT_ID,))

            conn.commit()                       # 订单+扣库存 一起提交
            with lock:
                success += 1
            return
        except pymysql.err.OperationalError as e:
            conn.rollback()
            if e.args[0] == 1213:              # 死锁：正常现象，重试
                if attempt >= 4:
                    with lock:
                        fail_reason["死锁重试仍失败"] += 1
                continue
            with lock:
                fail_reason["异常"] += 1
            return
        except Exception as e:
            conn.rollback()
            with lock:
                fail_reason["异常"] += 1
            return
        finally:
            conn.close()


def run(use_fix, tag):
    global success
    success = 0
    for k in fail_reason:
        fail_reason[k] = 0
    test_user_ids = reset()
    print()
    print("=" * 52)
    print(f"压测：{PEOPLE} 人同时抢显示器（库存 {STOCK} 件）— {tag}")
    print("=" * 52)

    barrier = threading.Barrier(PEOPLE)     # 100 人全部就位，同时开抢（制造真并发）
    threads = []
    for i in range(PEOPLE):
        t = threading.Thread(target=lambda: (barrier.wait(), buy(test_user_ids[i], use_fix)))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    # 查最终库存
    cur = mkconn().cursor()
    cur.execute("SELECT stock FROM product WHERE id = %s", (PRODUCT_ID,))
    final_stock = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM orders WHERE id > %s", (base_order_id,))
    order_count = cur.fetchone()[0]
    # 清理：按 stress 用户删（订单→明细→用户），保证不残留
    cur.execute("DELETE oi FROM order_item oi JOIN orders o ON oi.order_id=o.id JOIN users u ON o.user_id=u.id WHERE u.username LIKE 'stress_%%'")
    cur.execute("DELETE o FROM orders o JOIN users u ON o.user_id=u.id WHERE u.username LIKE 'stress_%%'")
    cur.execute("DELETE FROM users WHERE username LIKE 'stress_%%'")
    cur.connection.close()

    print(f"✅ 下单成功人数 : {success}")
    print(f"📦 最终库存      : {final_stock}")
    print(f"📋 订单表里订单数 : {order_count}")
    print(f"❌ 失败原因      : {fail_reason}")
    if success > STOCK or final_stock < 0:
        print("⚠️⚠️ 超卖发生了！！卖出数 > 库存，或库存变负数！")
    else:
        print("🎉 没有超卖：卖出 ≤ 库存，库存 ≥ 0")


# ===== 主流程 =====
if len(sys.argv) > 1 and sys.argv[1] == "fix":
    run(True, "修复版：UPDATE ... WHERE stock >= 1")
else:
    run(False, "BUG 版：先查后扣（app.py 现状）")

print()
print("再跑一次：python stress_test.py fix  → 对比修复版")
