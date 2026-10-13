# -*- coding: utf-8 -*-
"""
Redis 发布订阅演示（Day 15）
============================
场景：商城秒杀广播——1 个发布者喊话，2 个订阅者同时收到

类比：微信群/对讲机
  PUBLISH 频道 消息  = 群主喊话
  SUBSCRIBE 频道     = 成员挂机收听（一直等消息）

运行：python pubsub_demo.py
前提：Redis（Memurai）已启动
"""

import threading
import time
import redis

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# ===== 两个订阅者（模拟两个在线用户，挂机收听） =====
def listener(name):
    ps = r.pubsub()
    ps.subscribe("shop:seckill")          # 订阅秒杀频道
    print(f"[{name}] 已进入频道，等待广播…")
    for msg in ps.listen():
        if msg["type"] == "message":      # 收到消息
            print(f"[{name}] 📢 收到广播：{msg['data']}")

t1 = threading.Thread(target=listener, args=("用户A",), daemon=True)
t2 = threading.Thread(target=listener, args=("用户B",), daemon=True)
t1.start()
t2.start()
time.sleep(0.5)                            # 等两个人都"挂上机"

# ===== 发布者喊话（商城运营） =====
print()
print("=" * 50)
print("运营开始广播：")
print("=" * 50)
time.sleep(0.3)
r.publish("shop:seckill", "⚡ 3号显示器 19:00 开抢，库存 13 件！")
time.sleep(0.8)
r.publish("shop:seckill", "⚡ 手快有手慢无！")
time.sleep(1.0)
r.publish("shop:seckill", "🏁 抢购开始！")

time.sleep(1)
print()
print("✅ 广播结束——所有在线订阅者都收到了同一条消息")
print("关键：发布者（运营）根本不知道谁在听、有几个在听")
print("      这就是『一个发，N 个收』的广播模式")
