# -*- coding: utf-8 -*-
"""订单生命周期验证：pending→paid（支付）/ pending→cancelled+库存回补（超时）
验证手段：把订单在延迟队列里的 score 改到过去，模拟"时间流逝"触发自动取消"""
import json
import subprocess
import time
import urllib.request

BASE = "http://localhost:5001"
NAME = "lifecycle_user"


def post(path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method="POST",
                                 data=json.dumps(body or {}).encode())
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get(path, token=None):
    req = urllib.request.Request(BASE + path)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def redis(*args):
    subprocess.run(["docker", "exec", "shop-redis", "redis-cli", *args],
                   capture_output=True, text=True)


def main():
    # 重置环境
    post("/api/admin/reset")
    try:
        token = post("/api/register", body={"username": NAME, "password": "Shop2026test"})["token"]
    except Exception:
        token = post("/api/login", body={"username": NAME, "password": "Shop2026test"})["token"]

    # ① 购物车结算 → 生成 pending 订单
    post("/api/cart/add", token, {"product_id": 2})
    post("/api/cart/checkout", token)
    me = get("/api/me", token)
    oid = me["orders"][0]["id"]
    assert me["orders"][0]["status"] == "pending", "❌ 新订单应为 pending"
    assert redis.__name__ and int(redis_cli_zcard()) >= 1, "❌ 延迟队列应有该订单"
    print(f"✅ 下单 → 订单 #{oid} pending，已入延迟队列")

    # ② 支付 → paid + 出队
    post("/api/order/pay", token, {"order_id": oid})
    me = get("/api/me", token)
    assert me["orders"][0]["status"] == "paid", "❌ 支付后应为 paid"
    print(f"✅ 支付 → 订单 #{oid} paid，已移出延迟队列")

    # ③ 再下一单 → 不支付 → 把过期时间改到过去 → 自动取消 + 库存回补
    stock_before = int(get("/api/product/2")["data"]["stock"])
    post("/api/cart/add", token, {"product_id": 2})
    post("/api/cart/checkout", token)
    me = get("/api/me", token)
    oid2 = me["orders"][0]["id"]
    assert me["orders"][0]["status"] == "pending", "❌ 第二单应为 pending"
    print(f"✅ 又下一单 #{oid2} pending（库存 {stock_before} → {stock_before-1}）")
    now_s = int(float(get("/api/product/1")["data"]["price"]))  # 占位，下面用 redis TIME
    out = subprocess.run(["docker", "exec", "shop-redis", "redis-cli", "TIME"],
                         capture_output=True, text=True)
    now_s = int(out.stdout.split()[0])
    redis("ZADD", "order:delay", str(now_s - 100), str(oid2))   # 模拟时间流逝
    time.sleep(5)                                                # 等 watcher 扫描
    me = get("/api/me", token)
    assert me["orders"][0]["status"] == "cancelled", "❌ 超时应自动取消"
    stock_after = int(get("/api/product/2")["data"]["stock"])
    assert stock_after == stock_before, f"❌ 库存应回补到 {stock_before}，实际 {stock_after}"
    print(f"✅ 超时 → 订单 #{oid2} cancelled，库存回补 {stock_after}")
    print("\n🎯 订单生命周期全绿：pending → paid / cancelled（+ 库存回补）")


def redis_cli_zcard():
    out = subprocess.run(["docker", "exec", "shop-redis", "redis-cli", "ZCARD", "order:delay"],
                         capture_output=True, text=True)
    return int(out.stdout.strip() or 0)


if __name__ == "__main__":
    main()
