# -*- coding: utf-8 -*-
"""
缓存穿透演示（Day 16）
======================
场景：有人故意刷【不存在的商品】——你的商品只有 id 1/2/3，他狂刷 id=99999

问题：缓存里没有 99999 → 每次都穿透到 MySQL → MySQL 也查不到 → 白忙一场
     刷 1000 次 = MySQL 被白打 1000 次（这就是"穿透"，是攻击）

三种方案对比：
  方案0 无防护     → MySQL 被打 1000 次 ❌
  方案1 缓存空值   → 查不到的也缓存 30 秒 → MySQL 只被打 1 次 ✅
  方案2 布隆过滤器 → 先问"存在吗"，不存在直接挡 → MySQL 0 次 ✅✅

运行：python cache_attack_demo.py
前提：MySQL 和 Redis（Memurai）都已启动
"""

import pymysql
import redis

# ===== 连接 =====
db = pymysql.connect(host="127.0.0.1", port=4306, user="root", password="root123",
                     database="my_first_db", charset="utf8mb4")
r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

MYSQL_HIT = 0   # 计数器：MySQL 被查了多少次


def get_product(product_id):
    """查商品：先缓存，后 MySQL（你商城 /products 的逻辑）"""
    global MYSQL_HIT
    cache_key = f"product:{product_id}"

    # 1. 先查缓存
    cached = r.get(cache_key)
    if cached is not None:
        return cached

    # 2. 缓存没有 → 查 MySQL
    MYSQL_HIT += 1
    with db.cursor() as cur:
        cur.execute("SELECT name, stock FROM product WHERE id=%s", (product_id,))
        row = cur.fetchone()

    if row:
        # 3a. 查到 → 写缓存
        r.set(cache_key, f"{row[0]}|{row[1]}", ex=30)
        return f"{row[0]}|{row[1]}"
    else:
        # 3b. 没查到 → 【穿透了】什么都不缓存，下次还来打 MySQL！
        return None


def get_product_blank_cache(product_id):
    """方案1：空值也缓存——查不到的也缓存 30 秒，下次直接挡在 Redis"""
    global MYSQL_HIT
    cache_key = f"product:{product_id}"

    cached = r.get(cache_key)
    if cached is not None:
        return cached or None   # 缓存的是空字符串 → 返回 None

    MYSQL_HIT += 1
    with db.cursor() as cur:
        cur.execute("SELECT name, stock FROM product WHERE id=%s", (product_id,))
        row = cur.fetchone()

    if row:
        r.set(cache_key, f"{row[0]}|{row[1]}", ex=30)
        return f"{row[0]}|{row[1]}"
    else:
        # 没查到 → 空值也缓存 30 秒！（关键区别）
        r.set(cache_key, "", ex=30)
        return None


def get_product_bloom(product_id, bloom):
    """方案2：布隆过滤器——先问"这东西存在吗"，不存在直接挡（根本不碰 MySQL）"""
    global MYSQL_HIT
    if product_id not in bloom:
        return None    # 布隆说"不存在" → 直接挡！MySQL 一次都不用去

    cache_key = f"product:{product_id}"
    cached = r.get(cache_key)
    if cached is not None:
        return cached or None

    MYSQL_HIT += 1
    with db.cursor() as cur:
        cur.execute("SELECT name, stock FROM product WHERE id=%s", (product_id,))
        row = cur.fetchone()

    if row:
        r.set(cache_key, f"{row[0]}|{row[1]}", ex=30)
        return f"{row[0]}|{row[1]}"
    else:
        r.set(cache_key, "", ex=30)
        return None


ATTACK_ID = 99999   # 攻击者刷的商品（不存在）
TIMES = 1000        # 刷 1000 次

print("=" * 56)
print("缓存穿透演示：刷不存在的商品 id=99999，共 1000 次")
print("=" * 56)

# ===== 方案0：无防护 =====
MYSQL_HIT = 0
for _ in range(TIMES):
    get_product(ATTACK_ID)
print(f"\n【方案0 无防护】    MySQL 被打了 {MYSQL_HIT} 次 ❌   （1000 次请求全打库）")

# ===== 方案1：缓存空值 =====
MYSQL_HIT = 0
for _ in range(TIMES):
    get_product_blank_cache(ATTACK_ID)
print(f"【方案1 缓存空值】  MySQL 被打了 {MYSQL_HIT} 次 ✅   （第 1 次查库，之后全挡在 Redis）")

# ===== 方案2：布隆过滤器 =====
bloom = {1, 2, 3}   # 布隆里登记了真实存在的商品 id（教学用 set 模拟）
MYSQL_HIT = 0
for _ in range(TIMES):
    get_product_bloom(ATTACK_ID, bloom)
print(f"【方案2 布隆过滤】  MySQL 被打了 {MYSQL_HIT} 次 ✅✅ （99999 不在名单里，一次都没进库）")

# ===== 验证正常商品不受影响 =====
print("\n验证：刷【真实存在的商品】id=1 依然正常：")
print(f"  查到商品：{get_product_bloom(1, bloom)}（缓存里应有值）")

db.close()
r.delete("product:99999")   # 清理演示用缓存
print("\n🗑️ 临时缓存已清理（product:99999）")
print("\n结论：布隆过滤器 = 进门先查黑名单，不在名单直接拒之门外，MySQL 零开销")
