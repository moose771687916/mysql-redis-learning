# -*- coding: utf-8 -*-
"""
电商 API 测试脚本（Day 8 下半场）
====================================
对正在运行的 Flask 服务发真实 HTTP 请求：
  注册 → 重名注册 → 下单 → 超量下单（回滚）

前提：app.py 正在运行（另一个窗口，别关）
运行：python api_test.py
"""

import json
import urllib.request
import urllib.error

BASE = "http://localhost:5000"


def post(url, data):
    """发一个 POST 请求，返回 (状态码, 返回的JSON)"""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),      # 把字典变成 JSON 字符串发出去
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:             # 服务器返回错误码时（400/409等）
        return e.code, json.loads(e.read().decode("utf-8"))


print("=" * 46)
print("   电商 API 全家桶测试")
print("=" * 46)

print("\n① 注册新用户 laowang：")
s, r = post(f"{BASE}/register", {"username": "laowang", "password": "123456"})
print(f"   [{s}] {r}")
user_id = r.get("user_id")          # 动态拿注册返回的 ID（别写死！AUTO_INCREMENT 会跳号）

print("\n② 重复注册 laowang（UNIQUE 约束应该拦下）：")
s, r = post(f"{BASE}/register", {"username": "laowang", "password": "111"})
print(f"   [{s}] {r}")

print("\n③ 用新用户下单：无线鼠标 x1（89 元）：")
s, r = post(f"{BASE}/order", {"user_id": user_id, "product_id": 1, "quantity": 1})
print(f"   [{s}] {r}")

print("\n④ 超量下单：显示器 x99999（库存只有 20，应该回滚）：")
s, r = post(f"{BASE}/order", {"user_id": user_id, "product_id": 3, "quantity": 99999})
print(f"   [{s}] {r}")

print("\n✅ 测试完，去 MySQL 查一下：")
print("   SELECT * FROM users;      → 能看到 laowang")
print("   SELECT * FROM orders;     → 能看到那笔 89 元的订单")
print("   SELECT stock FROM product WHERE id=1;  → 鼠标库存少 1 个（99）")
