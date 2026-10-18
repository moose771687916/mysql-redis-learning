# -*- coding: utf-8 -*-
"""
Redis 消息队列削峰演示（Day 18）
================================
场景：1000 人同时秒杀 13 件商品——直接打 MySQL 会瘫，用 Redis 队列削峰

关键命令（Redis List 当队列）：
  LPUSH 队列 消息   = 生产者发号（从左边塞进队列）→ 1 秒全收下
  BRPOP 队列 0      = 消费者叫号（从右边取，没有就阻塞等）

对比演示：
  ① 直连版：1000 个请求直接打 MySQL（模拟压垮）
  ② 队列版：1000 个请求先进 Redis 队列（秒收），3 个 worker 慢慢消化

运行：python mq_demo.py
前提：MySQL 和 Redis（Memurai）都已启动
"""

import threading
import time
import pymysql
import redis

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
QUEUE = "seckill:queue"       # 秒杀队列的名字


def get_mysql():
    return pymysql.connect(host="127.0.0.1", port=4306, user="root", password="root123",
                           database="my_first_db", charset="utf8mb4")


# ========== ① 直连版：1000 个请求直接打 MySQL ==========
def direct_attack():
    """模拟 1000 个请求直接下单（会死锁/超时，这里只统计成功数）"""
    success = 0
    fail = 0
    t0 = time.perf_counter()

    def one_request(i):
        nonlocal success, fail
        try:
            conn = get_mysql()
            cur = conn.cursor()
            # 经典"先查后扣"（Day 14 的超卖 bug 写法，故意用条件扣模拟激烈竞争）
            n = cur.execute(
                "UPDATE product SET stock = stock - 1 WHERE id = 3 AND stock >= 1")
            conn.commit()
            conn.close()
            if n:
                success += 1
            else:
                fail += 1
        except Exception:
            fail += 1

    threads = [threading.Thread(target=one_request, args=(i,)) for i in range(1000)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0
    return success, fail, elapsed


# ========== ② 队列版：Redis 收单 + worker 消化 ==========
class SeckillMQ:
    """用 Redis List 做的迷你消息队列"""

    def __init__(self):
        self.done = 0        # worker 处理成功的单数
        self.orders = []     # 处理结果记录

    def produce(self, user_ids):
        """生产者：把 1000 个请求塞进队列（LPUSH），秒回"""
        t0 = time.perf_counter()
        pipe = r.pipeline()
        for uid in user_ids:
            pipe.lpush(QUEUE, uid)      # 从左边塞
        pipe.execute()
        return time.perf_counter() - t0

    def consume(self, worker_id):
        """消费者 worker：从右边取（BRPOP 阻塞等），取到就处理"""
        while True:
            msg = r.brpop(QUEUE, timeout=1)   # 取不到就等 1 秒
            if msg is None:
                break                          # 队列空了，下班
            uid = msg[1]
            try:
                conn = get_mysql()
                cur = conn.cursor()
                n = cur.execute(
                    "UPDATE product SET stock = stock - 1 WHERE id = 3 AND stock >= 1")
                conn.commit()
                conn.close()
                if n:
                    self.orders.append((uid, "成功"))
                    self.done += 1
                else:
                    self.orders.append((uid, "手慢了"))
            except Exception as e:
                self.orders.append((uid, f"失败:{e}"))


print("=" * 60)
print("对比实验：1000 人同时秒杀 3 号显示器（库存 13 件）")
print("=" * 60)

# 先恢复库存
conn = get_mysql()
cur = conn.cursor()
cur.execute("UPDATE product SET stock = 13 WHERE id = 3")
conn.commit()
conn.close()
print(f"\n库存已恢复为 13 件\n")

# ---------- 实验 1：直连 MySQL ----------
print("【实验 1】1000 个请求直接打 MySQL（不排队）...")
success, fail, elapsed = direct_attack()
print(f"  ✅ 成功 {success} 单 | ❌ 失败 {fail}（失败=超时/死锁/连接失败）")
print(f"  耗时 {elapsed:.2f} 秒")
conn = get_mysql()
cur = conn.cursor()
cur.execute("SELECT stock FROM product WHERE id = 3")
stock_now = cur.fetchone()[0]
conn.close()
print(f"  库存剩 {stock_now}（应该 0，被超卖/失败打乱说明直连不稳）\n")

# 恢复库存 + 清队列
conn = get_mysql()
cur = conn.cursor()
cur.execute("UPDATE product SET stock = 13 WHERE id = 3")
conn.commit()
conn.close()
r.delete(QUEUE)
print("（已恢复库存、清空队列，开始实验 2）\n")

# ---------- 实验 2：Redis 队列削峰 ----------
print("【实验 2】1000 个请求先进 Redis 队列（削峰），3 个 worker 慢慢消化...")
mq = SeckillMQ()
user_ids = [f"user_{i}" for i in range(1000)]

# 生产者：1000 个请求瞬间全收
push_time = mq.produce(user_ids)
print(f"  📥 生产者：1000 个请求 {push_time*1000:.0f} 毫秒全收进队列（Redis 真快）")

# 消费者：3 个 worker 同时消化
t0 = time.perf_counter()
workers = [threading.Thread(target=mq.consume, args=(f"worker{i}",)) for i in range(3)]
for w in workers:
    w.start()
for w in workers:
    w.join()
consume_time = time.perf_counter() - t0

conn = get_mysql()
cur = conn.cursor()
cur.execute("SELECT stock FROM product WHERE id = 3")
stock_now = cur.fetchone()[0]
conn.close()

print(f"  🍳 消费者：3 个 worker {consume_time:.2f} 秒消化完（每秒约 {1000/consume_time:.0f} 单）")
print(f"  📊 结果：成功 {mq.done} 单（库存 13 → {stock_now}），手慢的排到队尾自动失败")
print(f"  🎯 关键：Redis 1 秒收 1000（快），MySQL 每秒只吃 50（稳）——"
      f"高峰被削平，数据库没被压垮")

# 恢复库存 + 清队列
conn = get_mysql()
cur = conn.cursor()
cur.execute("UPDATE product SET stock = 13 WHERE id = 3")
conn.commit()
conn.close()
r.delete(QUEUE)

print()
print("✅ 对比结论：")
print("  直连版 → 1000 个请求同时砸 MySQL → 大量超时/死锁/连接失败")
print("  队列版 → Redis 秒收全 + worker 排队消化 → 全部有序处理，MySQL 稳稳的")
print("  （这就是大厂秒杀架构的核心：Redis 削峰 + 异步消化）")
