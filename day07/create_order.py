# -*- coding: utf-8 -*-
"""
电商下单演示（Day 7 核心：事务 Transaction）
==============================================
一次下单 = 三件事必须"全成或全不成"：
  ① 写订单表 orders        （生成订单号）
  ② 写订单明细 order_item  （每件商品一行，价格快照）
  ③ 扣库存 product         （stock 减掉购买数量）

如果只成一半（比如订单写了但库存没扣）→ 超卖，电商事故！
所以三件事包在"事务"里：全部成功 → commit 提交；任何一步失败 → rollback 回滚。
就像转账：A 扣钱 + B 加钱，不能只扣不加。

运行前提：MySQL 已启动；五张表已建好
运行方式：python create_order.py
"""

import pymysql


def connect():
    return pymysql.connect(
        host="127.0.0.1", port=4306,
        user="root",
        password="root123",
        database="my_first_db",
        charset="utf8mb4"
    )


# ---------- 查看购物车（JOIN 展示） ----------
def show_cart(conn, user_id=1):
    cur = conn.cursor()
    cur.execute("""
        SELECT product.name, cart.quantity, product.price,
               cart.quantity * product.price
        FROM cart
        JOIN product ON cart.product_id = product.id
        WHERE cart.user_id = %s
    """, (user_id,))
    rows = cur.fetchall()
    if not rows:
        print("（购物车是空的）")
        return [], 0
    total = sum(r[3] for r in rows)
    print(f"===== 用户 {user_id} 的购物车 =====")
    for r in rows:
        print(f"  {r[0]}  x{r[1]}  单价 {r[2]:.2f}元  小计 {r[3]:.2f}元")
    print(f"  合计：{total:.2f} 元")
    return rows, total


# ---------- 下单（事务核心） ----------
def checkout(conn, user_id=1):
    cur = conn.cursor()
    try:
        # 第 0 步：从购物车取商品 + 价格 + 库存（JOIN 三张表）
        cur.execute("""
            SELECT cart.product_id, cart.quantity, product.price, product.stock
            FROM cart
            JOIN product ON cart.product_id = product.id
            WHERE cart.user_id = %s
        """, (user_id,))
        items = cur.fetchall()
        if not items:
            print("购物车是空的，先加商品！")
            return

        # 第 1 步：先查库存，任何一个不够 → 整个订单取消
        for item in items:
            if item[3] < item[1]:
                print(f"❌ 库存不足：商品ID {item[0]} 只剩 {item[3]} 件，你要买 {item[1]} 件")
                print("   整个订单取消（回滚，啥也没发生）")
                conn.rollback()     # 反悔，全都不做
                return

        # 第 2 步：算总价，插入订单表
        total = sum(i[1] * i[2] for i in items)
        cur.execute("INSERT INTO orders (user_id, total) VALUES (%s, %s)", (user_id, total))
        order_id = cur.lastrowid
        print(f"① 订单已创建：订单号 {order_id}，总额 {total:.2f} 元")

        # 第 3 步：写订单明细（每件商品一行，价格快照）
        for item in items:
            cur.execute("""
                INSERT INTO order_item (order_id, product_id, quantity, price)
                VALUES (%s, %s, %s, %s)
            """, (order_id, item[0], item[1], item[2]))
        print(f"② 明细已写入：{len(items)} 件商品")

        # 第 4 步：扣库存
        for item in items:
            cur.execute(
                "UPDATE product SET stock = stock - %s WHERE id = %s",
                (item[1], item[0])
            )
        print("③ 库存已扣减")

        conn.commit()               # 全部成功 → 提交生效！
        print(f"✅ 下单成功！订单号 {order_id}，总额 {total:.2f} 元")

    except Exception as e:
        conn.rollback()             # 任何一步出错 → 全部回滚
        print(f"❌ 下单失败，已全部回滚：{e}")


# ---------- 故意超买：演示回滚 ----------
def checkout_too_much(conn):
    """把显示器（库存 20）塞进购物车买 9999 个，必失败"""
    cur = conn.cursor()
    cur.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (1, 3, 9999)")
    conn.commit()
    print("\n（已把『显示器 x9999』加入购物车——库存只有 20，等着看回滚）\n")
    checkout(conn, 1)


# ---------- 主菜单 ----------
def main():
    print("=" * 44)
    print("   🛒 电商下单演示（事务专场）")
    print("=" * 44)
    try:
        conn = connect()
        print("✅ 数据库连接成功！\n")
    except Exception as e:
        print(f"❌ 连不上数据库：{e}")
        print("请先启动 MySQL 再运行")
        return

    while True:
        print("请选择：")
        print("  1. 查看购物车")
        print("  2. 正常下单（用户1的购物车）")
        print("  3. 故意超买（显示器x9999，演示回滚）")
        print("  4. 退出")
        choice = input(">>> 输入数字：").strip()

        if choice == "1":
            show_cart(conn)
        elif choice == "2":
            checkout(conn, 1)
        elif choice == "3":
            checkout_too_much(conn)
        elif choice == "4":
            print("👋 拜拜！")
            conn.close()
            break
        else:
            print("❌ 无效选择，请输入 1-4\n")


if __name__ == "__main__":
    main()
