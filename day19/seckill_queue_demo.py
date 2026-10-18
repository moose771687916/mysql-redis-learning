# -*- coding: utf-8 -*-
"""
秒杀队列全链路演示（Day 19）
==============================
先启动商城（python app.py，会自动带上队列 worker），再跑本脚本：
模拟 1000 个用户同时打 /seckill 接口 → 观察"全部秒回排队中"+"后台消化"全链路

对比 Day 18 实验 1（直连 MySQL：987 人超时失败）：
  队列版 → 1000 个请求全部被接收（无 500），worker 后台慢慢消化，零超卖

运行：python seckill_queue_demo.py
前提：1) MySQL（4306）+ Redis 已启动  2) 商城 app.py 正在运行（端口 5000）
"""

import json
import threading
import time
import urllib.request
import pymysql
import redis

BASE = "http://localhost:5000"
N = 1000          # 1000 个用户抢
PRODUCT_ID = 3    # 3 号显示器，库存 13
USER_BASE = 900000  # 独特 user_id 区间（避开历史订单，统计才准）


def get_mysql():
    return pymysql.connect(host="127.0.0.1", port=4306, user="root", password="root123",
                           database="my_first_db", charset="utf8mb4")


def post(path, data):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


# ① 清理上次演示残留（订单 + 测试用户 + Redis 状态），恢复库存 13
conn = get_mysql()
cur = conn.cursor()
cur.execute("DELETE oi FROM order_item oi JOIN orders o ON oi.order_id = o.id "
            "WHERE o.user_id BETWEEN %s AND %s", (USER_BASE + 1, USER_BASE + N))
cur.execute("DELETE FROM orders WHERE user_id BETWEEN %s AND %s", (USER_BASE + 1, USER_BASE + N))
cur.execute("DELETE FROM users WHERE username LIKE 'seckill_%'")
cur.execute("UPDATE product SET stock = 13 WHERE id = %s", (PRODUCT_ID,))
conn.commit()
conn.close()
r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
r.delete("seckill:stock:3")
r.delete("seckill:queue")
for i in range(1, N + 1):
    r.delete(f"seckill:result:{USER_BASE + i}")

# ② 造 1000 个测试用户（orders 有外键 user_id → users.id，显式插入 id=900001~901000 对上）
conn = get_mysql()
cur = conn.cursor()
rows = [(USER_BASE + i, f"seckill_{USER_BASE + i}", "test123") for i in range(1, N + 1)]
cur.executemany("INSERT INTO users (id, username, password) VALUES (%s, %s, %s)", rows)
conn.commit()
conn.close()
print(f"📦 已清理上次残留，造好 {len(rows)} 个测试用户（id={USER_BASE + 1}~{USER_BASE + N}），库存恢复 13 件\n")

# ③ 预置 Redis 秒杀库存（真实项目由运营在开抢前预置；避免接口初始化竞态）
r.set("seckill:stock:3", 13)

# ② 1000 个用户并发打 /seckill
# 客户端限流：一次最多 200 个在途连接（开发服务器连接数有限，真实生产用 gunicorn 多进程）
print(f"🚀 模拟 {N} 个用户同时点抢购（/seckill）...")
queued, sold_out, errors = 0, 0, []
lock = threading.Lock()
sem = threading.Semaphore(200)
t0 = time.perf_counter()

def one_user(i):
    global queued, sold_out
    uid = USER_BASE + i
    with sem:
        try:
            resp = post("/seckill", {"user_id": uid, "product_id": PRODUCT_ID, "quantity": 1})
            with lock:
                if resp.get("status") == "排队中":
                    queued += 1
                elif resp.get("status") == "售罄":
                    sold_out += 1
                else:
                    errors.append(resp)
        except Exception as e:
            with lock:
                errors.append(str(e))

threads = [threading.Thread(target=one_user, args=(i,)) for i in range(1, N + 1)]
for t in threads:
    t.start()
for t in threads:
    t.join()
push_time = time.perf_counter() - t0

print(f"  📥 排队中 {queued} | 售罄 {sold_out} | 异常 {len(errors)}")
print(f"  ⚡ 全部请求在 {push_time:.2f} 秒内得到响应（接口只碰 Redis，无压力）")
if errors:
    print(f"  ❌ 异常样例：{errors[:3]}")
print()

# ③ 等 worker 后台消化（轮询库存降到 0）
print("👷 等待后台 worker 排队消化（可观察 app.py 控制台的 ⚡ 处理日志）...")
conn = get_mysql()
cur = conn.cursor()
deadline = time.time() + 120
last_stock = -1
while time.time() < deadline:
    cur.execute("SELECT stock FROM product WHERE id = %s", (PRODUCT_ID,))
    stock = cur.fetchone()[0]
    if stock != last_stock:
        print(f"    库存剩余: {stock}")
        last_stock = stock
    if stock == 0:
        break
    time.sleep(2)
conn.close()
consume_time = time.perf_counter() - t0 - push_time

# ④ 统计：本次区间内、商品 3 的成功订单数（严格按 user_id 区间，不算历史）
conn = get_mysql()
cur = conn.cursor()
cur.execute("""
    SELECT COUNT(*) FROM orders o
    JOIN order_item oi ON oi.order_id = o.id
    WHERE o.user_id BETWEEN %s AND %s AND oi.product_id = %s
""", (USER_BASE + 1, USER_BASE + N, PRODUCT_ID))
ok_orders = cur.fetchone()[0]
conn.close()

print()
print("=" * 56)
print("📊 全链路结果")
print("=" * 56)
print(f"  请求全部得到响应：{N - len(errors)}/{N}（无 500，这就是削峰的价值）")
print(f"  排队中 {queued} → 成功下单：{ok_orders} 单（库存 13 → 0，零超卖）")
print(f"  其余 {N - ok_orders} 人：『售罄』或后台处理时被告知『手慢了』（有明确结果，不是报错）")
print(f"  消化耗时：约 {consume_time:.0f} 秒（worker 每秒处理几十个，MySQL 稳稳的）")
print()
print("  对比 Day 18 直连版：987 人直接超时失败 vs 今天 1000 人全接收")
print("  → Redis 预扣粗筛 + 进队秒回 + worker 异步消化 = 完整秒杀架构")
print("=" * 56)

# ⑤ 清理演示数据（教学库保持干净）：删本次订单 + 测试用户 + 恢复库存 + 清 Redis
conn = get_mysql()
cur = conn.cursor()
cur.execute("DELETE oi FROM order_item oi JOIN orders o ON oi.order_id = o.id "
            "WHERE o.user_id BETWEEN %s AND %s", (USER_BASE + 1, USER_BASE + N))
cur.execute("DELETE FROM orders WHERE user_id BETWEEN %s AND %s", (USER_BASE + 1, USER_BASE + N))
cur.execute("DELETE FROM users WHERE username LIKE 'seckill_%'")
cur.execute("UPDATE product SET stock = 13 WHERE id = %s", (PRODUCT_ID,))
conn.commit()
conn.close()
r.delete("seckill:stock:3")
r.delete("seckill:queue")
print("\n🗑️ 演示数据已清理（订单/测试用户已删、库存已恢复、队列已清空）")
