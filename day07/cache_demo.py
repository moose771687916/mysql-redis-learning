# -*- coding: utf-8 -*-
"""
商品列表 + Redis 缓存（Day 7 下半场）
========================================
经典缓存套路（高并发"第 2 层"亲手实现）：
    查商品列表 → 先问 Redis（有？秒回"命中缓存"）
              → 没有？查 MySQL（"未命中"）→ 写回 Redis（30 秒过期）

下次再来查 → 直接命中缓存，不用碰数据库 → MySQL 轻松一大截。

运行前提：MySQL 已启动 + Memurai 服务在跑（都是现成的）
运行方式：python cache_demo.py
"""

import json
import time
import pymysql
import redis


def connect_mysql():
    return pymysql.connect(
        host="127.0.0.1", port=4306, user="root", password="root123",
        database="my_first_db", charset="utf8mb4"
    )


# 缓存键（Redis 里约定俗成的命名：模块:业务）
CACHE_KEY = "product:list"


def get_products():
    """查商品列表：缓存优先，未命中则查库并写回缓存"""
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
    t0 = time.perf_counter()           # 开始计时（秒）

    # ---------- 第 1 步：先问 Redis ----------
    cached = r.get(CACHE_KEY)
    if cached is not None:
        dt = (time.perf_counter() - t0) * 1000      # 换算成毫秒
        products = json.loads(cached)               # 缓存里存的是 JSON 字符串
        print(f"⚡ 命中缓存！耗时 {dt:.2f} 毫秒")
        print_products(products)
        return

    # ---------- 第 2 步：缓存没有 → 查 MySQL ----------
    conn = connect_mysql()
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, stock FROM product")
    rows = cur.fetchall()
    conn.close()

    # 注意：price 是 DECIMAL 列，Python 里是 Decimal 对象，要转成 float 才能 JSON 序列化
    products = [{"id": r[0], "name": r[1], "price": float(r[2]), "stock": r[3]} for r in rows]

    # ---------- 第 3 步：写回 Redis，30 秒过期 ----------
    r.set(CACHE_KEY, json.dumps(products, ensure_ascii=False), ex=30)

    dt = (time.perf_counter() - t0) * 1000
    print(f"🐢 缓存未命中 → 查了 MySQL，耗时 {dt:.2f} 毫秒，已写入缓存（30 秒后过期）")
    print_products(products)


def print_products(products):
    print(f"   {'商品':<12}{'价格':<12}{'库存'}")
    for p in products:
        print(f"   {p['name']:<12}{p['price']:.2f}元     {p['stock']}")


def delete_cache():
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
    r.delete(CACHE_KEY)
    print("🗑️ 缓存已删除（模拟：商品数据更新了，清掉旧缓存）")


def main():
    print("=" * 46)
    print("   🛒 商品列表 + Redis 缓存（双库联手）")
    print("=" * 46)
    while True:
        print("请选择：")
        print("  1. 查看商品（缓存优先）")
        print("  2. 删除缓存（模拟数据更新）")
        print("  3. 连续查 3 次（体验缓存命中）")
        print("  4. 退出")
        choice = input(">>> 输入数字：").strip()

        if choice == "1":
            get_products()
        elif choice == "2":
            delete_cache()
        elif choice == "3":
            print()
            for i in range(3):
                print(f"第 {i+1} 次查询：")
                get_products()
                print()
        elif choice == "4":
            print("👋 拜拜！")
            break
        else:
            print("❌ 无效选择，请输入 1-4\n")


if __name__ == "__main__":
    main()
