# -*- coding: utf-8 -*-
"""Day 31 验收脚本：真实压测 Docker 版商城（零外部依赖，只用标准库）

流程：商品读取(缓存命中) → 1000 人并发抢 5 件 → 验证零超卖 → 熔断演练(停从库)
"""
import json
import subprocess
import threading
import time
import urllib.request

BASE = "http://localhost:5001"
STOCK, USERS = 5, 1000


def http(method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def reset():
    print("① 重置环境（清订单/库存回5/清队列）...")
    print("   ", http("POST", "/api/admin/reset"))


def read_chain():
    print("\n② 读链路：连续查 3 次商品详情...")
    for i in range(3):
        r = http("GET", "/api/product/1")
        print(f"   第{i+1}次：缓存={r['cache']}  源={r.get('source','-')}")
        time.sleep(0.3)


def seckill_stress():
    print(f"\n③ 秒杀压测：{USERS} 人并发抢 {STOCK} 件...")
    ok = [0]
    err = [0]

    def one(uid):
        try:
            http("POST", "/api/seckill", {"uid": uid})
            ok[0] += 1
        except Exception:
            err[0] += 1

    t0 = time.perf_counter()
    threads = []
    # 50 个线程 × 20 轮 = 1000 次请求（真并发）
    for uid in range(1001, 1001 + USERS):
        t = threading.Thread(target=one, args=(uid,))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    dt = time.perf_counter() - t0
    print(f"   1000 请求全部发出：{ok[0]} 成功 / {err[0]} 失败，耗时 {dt:.2f}s（接口 0 阻塞）")


def wait_digest():
    print("\n④ 等 3 个消费者消化队列（每 2 秒看一次）...")
    for _ in range(30):
        s = http("GET", "/api/stats")
        print(f"   库存={s['stock']} 订单={s['orders']} 队列={s['queue']} 参与={s['bought']} 读源={s['read_source']}")
        if s["queue"] == 0:
            return s
        time.sleep(2)
    raise SystemExit("❌ 消费者 60 秒没消化完队列，检查 app 日志")


def verify(s):
    print("\n⑤ 验收：")
    assert s["stock"] == 0, f"❌ 库存应为 0，实际 {s['stock']}"
    assert s["orders"] == STOCK, f"❌ 订单应为 {STOCK}，实际 {s['orders']}"
    # bought=SADD 集合=参与尝试人数（1000），orders=成功下单（5）
    # 一人一单由 SADD 幂等保证；不能断言 bought==orders
    assert s["bought"] >= s["orders"], f"❌ 参与人数应≥订单数，{s['bought']} vs {s['orders']}"
    print(f"   ✅ 库存 {s['stock']} = 订单 {s['orders']} → 零超卖零重复")
    print(f"   （参与尝试 {s['bought']} 人：抢到 {s['orders']} 人 + 未抢到 {s['bought']-s['orders']} 人）")


def failover():
    print("\n⑥ 熔断演练：停掉从库容器，读应自动切主库...")
    http("POST", "/api/admin/reset")   # 先清缓存+重置，强制走读源（否则缓存命中看不到切库）
    r = subprocess.run(["docker", "stop", "shop-mysql-slave"],
                       capture_output=True, text=True)
    print(f"   docker stop → {r.stdout.strip()}")
    time.sleep(3)
    try:
        r = http("GET", "/api/product/1")
        src = r.get("source", "?")
        print(f"   停从库后读商品：源={src}")
        assert "熔断" in str(src), "❌ 没切主库"
        print("   ✅ 熔断生效：从库挂了读自动切主库，服务没断")
    finally:
        subprocess.run(["docker", "start", "shop-mysql-slave"],
                       capture_output=True, text=True)
        time.sleep(8)
        s = http("GET", "/api/stats")
        print(f"   恢复从库后读源={s['read_source']}")
        assert s["read_source"] == "从库", "❌ 没切回从库"
        print("   ✅ 恢复自动切回从库")


def main():
    print("=" * 62)
    print("🛍️  Day 31 验收：Docker 版终极商城（4 容器全家桶）")
    print("=" * 62)
    reset()
    read_chain()
    seckill_stress()
    s = wait_digest()
    verify(s)
    failover()
    print("\n" + "=" * 62)
    print("🎯 结论：docker compose up 一条命令，MySQL主从+Redis+商城全部上线")
    print("   1000 人抢 5 件：0 超卖 0 重复 0 阻塞；从库挂了自动切主库")
    print("=" * 62)


if __name__ == "__main__":
    main()
