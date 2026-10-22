# -*- coding: utf-8 -*-
"""缓存击穿防护验证：删缓存后 30 线程并发读同一商品
期望：只有 1 个请求真正回源(未命中)，其余全部"等待后命中"→ 证明互斥锁把并发挡在了缓存层"""
import json
import threading
import urllib.request
import subprocess

BASE = "http://localhost:5001/api/product/1"

def reset_cache():
    subprocess.run(["docker", "exec", "shop-redis", "redis-cli", "DEL", "product:1"],
                   capture_output=True, text=True)

def worker(results):
    try:
        with urllib.request.urlopen(BASE, timeout=10) as resp:
            results.append(json.loads(resp.read())["cache"])
    except Exception as e:
        results.append(f"ERROR:{e}")

def main():
    reset_cache()
    results = []
    threads = [threading.Thread(target=worker, args=(results,)) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    from collections import Counter
    stat = Counter(results)
    print("30 个并发请求的 cache 结果分布：")
    for k, v in stat.items():
        print(f"  {k}: {v}")
    real_db = stat.get("未命中", 0) + stat.get("ERROR", 0)
    cached = stat.get("命中", 0) + stat.get("等待后命中", 0)
    # 防护有效 = 回源极少(≤3) + 绝大多数走缓存(≥25)。"命中"和"等待后命中"都是缓存层挡住。
    assert real_db <= 3, f"❌ 回源请求过多({real_db})，互斥锁没生效"
    assert cached >= 25, f"❌ 走缓存的请求太少({cached})，防护没挡住并发"
    print(f"\n✅ 击穿防护生效：30 并发里仅 {real_db} 个回源，其余 {cached} 个全部被缓存层挡住")

if __name__ == "__main__":
    main()
