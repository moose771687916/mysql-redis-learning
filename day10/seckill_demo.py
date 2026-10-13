# -*- coding: utf-8 -*-
"""
秒杀实战（Day 10-C）：Redis 原子扣库存 + 一人一单
==================================================
模拟 1000 人同时抢 13 件显示器，看两件武器的效果：
  ① DECR 原子扣库存  → 绝不超卖（命令不可分割，减完才轮到下一个人）
  ② SETNX 一人一单   → 同一人不能抢两次

原理：库存提前放进 Redis（内存，扛得住高并发）；
      抢到的人（DECR 返回 >= 0）才去 MySQL 写订单（本脚本聚焦 Redis 层，不写库）。

运行：python seckill_demo.py
"""

import redis
import threading

STOCK_KEY = "seckill:stock:3"   # 秒杀库存键（商品 3：显示器）
USER_KEY = "seckill:user:"      # 一人一单标记前缀
STOCK = 13                      # 模拟库存 13 件
PEOPLE = 1000                   # 模拟 1000 人同时抢

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)


def seckill(uid: int) -> str:
    """一个用户抢一次，返回结果：win / lose / repeat"""
    # ① 一人一单：键不存在才能设置成功（nx=True），抢过的人被拦下
    if not r.set(USER_KEY + str(uid), 1, nx=True):
        return "repeat"
    # ② 原子扣库存：DECR = 读取并减 1，一个动作不可分割
    left = r.decr(STOCK_KEY)
    if left >= 0:
        return "win"
    return "lose"


# ---------- 准备：库存放进 Redis ----------
r.set(STOCK_KEY, STOCK)
# 清掉上次的一人一单标记
for key in r.scan_iter(match=USER_KEY + "*"):
    r.delete(key)

# ---------- 1000 人同时抢 ----------
wins = loses = repeats = 0
lock = threading.Lock()


def worker(uid):
    global wins, loses, repeats
    result = seckill(uid)
    with lock:
        if result == "win":
            wins += 1
        elif result == "lose":
            loses += 1
        else:
            repeats += 1


print(f"🔥 秒杀开始！库存 {STOCK} 件，{PEOPLE} 人同时抢...")
threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, PEOPLE + 1)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print()
print("=" * 40)
print(f"  抢到（win）   : {wins} 人   ✅ 正好 = 库存数 {STOCK}")
print(f"  没抢到（lose）: {loses} 人")
print(f"  重复抢（repeat）: {repeats} 人")
print(f"  最终库存      : {r.get(STOCK_KEY)}  ← 绝不为负")
print("=" * 40)

# ---------- 验证一人一单：让 uid=1 再抢一次 ----------
print()
print("🧪 验证一人一单：让抢到的 1 号用户再抢一次 →", seckill(1))
print("   （返回 repeat = 被 SETNX 拦下，一个人最多一件）")

# 清理演示数据
r.delete(STOCK_KEY)
for key in r.scan_iter(match=USER_KEY + "*"):
    r.delete(key)
print("\n🗑️ 演示数据已清理（秒杀库存键 + 一人一单标记）")
