# -*- coding: utf-8 -*-
"""
Redis 演示脚本（Day 6 下半场）
================================
用 Python 连接 Redis（Memurai），存中文、设过期、做计数器。
对比命令行：Python 走 UTF-8，中文完美支持，没有命令行那种编码坑。

运行前提：Memurai 服务在跑（Windows 服务，开机自启，不用管它）
运行方式：python redis_demo.py
"""

import redis

# 连接 Redis：地址 127.0.0.1，端口 6379（跟 memurai-cli 连的是同一个）
# decode_responses=True = 返回值自动转成字符串（否则会是 b'xxx' 字节）
r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

print("=" * 40)
print("   Redis 中文演示")
print("=" * 40)

# ---------- 1. 存中文、读中文 ----------
print("\n① 存中文：")
r.set("user:name", "小明")          # 跟 SET user:name 小明 一样
print("   已存入「user:name」")
name = r.get("user:name")           # 跟 GET user:name 一样
print("   读出来：", name)

# ---------- 2. 设过期时间（缓存的核心） ----------
print("\n② 设 30 秒过期：")
r.set("session:token", "abc123", ex=30)   # ex=秒，一步到位（= SET + EXPIRE）
left = r.ttl("session:token")             # 查还剩几秒
print(f"   token 剩余存活：{left} 秒")

# ---------- 3. 计数器（点赞/访问量） ----------
print("\n③ 计数器（incr 原子自增）：")
print("   第 1 次点赞：", r.incr("post:likes"))
print("   第 2 次点赞：", r.incr("post:likes"))

# ---------- 4. 删除演示数据，保持干净 ----------
r.delete("user:name", "session:token", "post:likes")
print("\n✅ 演示结束，临时数据已清理")

# 你还可以自己在下面加命令试试，比如：
# r.set("greeting", "你好，Redis！")
# print(r.get("greeting"))
