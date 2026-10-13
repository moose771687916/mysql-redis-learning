# -*- coding: utf-8 -*-
"""
Redis 分布式锁演示（Day 15）
============================
场景：3 台服务器同时抢『每天 0 点清空过期订单』的任务——
      只允许一台执行，其他放弃

抢锁 = SET key value NX EX 秒数
  NX = 锁不存在才能设置成功（= 抢到资格）
  EX = 过期时间（防止拿锁的人挂了，锁永远解不开）

运行：python dist_lock_demo.py
前提：Redis（Memurai）已启动
"""

import threading
import time
import redis

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
LOCK_KEY = "lock:daily_job"


def do_job(server_name):
    # ① 抢锁：不存在才设置成功，10 秒自动过期（防死锁）
    ok = r.set(LOCK_KEY, server_name, nx=True, ex=10)
    if not ok:
        # 没抢到：看看锁被谁占着
        owner = r.get(LOCK_KEY)
        print(f"[{server_name}] ❌ 没抢到锁（被 {owner} 占着），放弃本次任务")
        return

    # ② 抢到了：开始干活
    print(f"[{server_name}] ✅ 抢到锁！开始清空过期订单…")
    time.sleep(2)                        # 模拟干活 2 秒
    print(f"[{server_name}] 🎉 任务完成")

    # ③ 释放锁：只删自己抢到的（防止误删别人的锁）
    if r.get(LOCK_KEY) == server_name:
        r.delete(LOCK_KEY)
        print(f"[{server_name}] 🔓 释放锁")


# ===== 3 台服务器同时抢 =====
print("=" * 50)
print("3 台服务器同时抢『清空过期订单』任务：")
print("=" * 50)
print(f"锁的钥匙：{LOCK_KEY}（10 秒自动过期）")
print()

threads = [threading.Thread(target=do_job, args=(f"server{i}",)) for i in range(3)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print()
print("✅ 结论：3 台服务器只有 1 台抢到锁执行任务，其余自动放弃")
print("   —— 这就是『多台服务器之间协调』：MySQL 行锁管不了，Redis 管")
