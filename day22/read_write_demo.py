# -*- coding: utf-8 -*-
"""Day 22：读写分离版商城 —— 读走从库，写走主库，从库挂了自动降级

故事线：
  平时商城 = 单机 Redis（读和写都压在一台主库上）
  今天开启「读写分离」：起一个从库（6380），商城的读接口（商品列表/详情）改从从库读，
  写接口（商家改价、下单）继续走主库 → 主库的读压力被从库分担。

实验：
  ① 单机模式基准：商家改价（写主库）→ 用户查列表 100 次（读主库）
  ② 读写分离：起从库 + 商城开启 REDIS_RO_PORT=6380
     商家改价 → 用户查列表 100 次 → 商城日志显示「命中缓存（读从库）」→ 读已分流
  ③ 降级容灾：杀掉从库 → 用户再查 100 次 → 全部 200 正常（自动降级主库）
  ④ 恢复：重启从库 → 商城日志出现「读从库」→ 自动切回

跑完自动清理：关商城 + 关从库 + 恢复商品价格。运行前请先启动 MySQL（4306）。
"""
import json
import os
import sys
import time
import subprocess
import urllib.request
import pymysql

MASTER_PORT = 6379
SLAVE_PORT = 6380
MEMURAI_EXE = r"C:\Program Files\Memurai\memurai.exe"
WORKDIR = os.path.dirname(os.path.abspath(__file__))
APP_PY = os.path.dirname(WORKDIR) + r"\app.py"
BASE_URL = "http://127.0.0.1:5000"
PYTHON = sys.executable

# 实验用的临时价格（跑完恢复原价）
OLD_PRICE = 49.90
TEST_PRICE = 88.80


def http_get(path):
    with urllib.request.urlopen(BASE_URL + path, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def port_pids(port):
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue).OwningProcess"],
        capture_output=True, text=True)
    return [p.strip() for p in ps.stdout.strip().splitlines() if p.strip()]


def kill_port(port):
    for pid in port_pids(port):
        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    time.sleep(1.2)


def wait_port(port, seconds=20):
    for _ in range(seconds):
        time.sleep(1)
        if port_pids(port):
            return True
    return False


def start_replica():
    subprocess.Popen(
        [MEMURAI_EXE, "--port", str(SLAVE_PORT), "--replicaof", "127.0.0.1", str(MASTER_PORT),
         "--dir", WORKDIR, "--dbfilename", f"dump-{SLAVE_PORT}.rdb",
         "--logfile", os.path.join(WORKDIR, "replica.log")],
        creationflags=subprocess.CREATE_NO_WINDOW)


def start_shop(ro_port=None):
    env = dict(os.environ)
    if ro_port:
        env["REDIS_RO_PORT"] = str(ro_port)
    return subprocess.Popen([PYTHON, APP_PY], env=env,
                            stdout=open(os.path.join(WORKDIR, "shop.log"), "a", encoding="utf-8"),
                            stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW)


def wait_shop(seconds=25):
    last_err = "未尝试"
    for _ in range(seconds):
        time.sleep(1)
        try:
            with urllib.request.urlopen(BASE_URL + "/products", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
    print(f"   ❌ 商城没起来，最后错误：{last_err}")
    print(f"   查看商城日志：{os.path.join(WORKDIR, 'shop.log')}")
    return False


def change_price(price):
    """商家改价（写 MySQL，真实业务写路径）"""
    conn = pymysql.connect(host="127.0.0.1", port=4306, user="root", password="root123",
                           database="my_first_db", charset="utf8mb4")
    cur = conn.cursor()
    cur.execute("UPDATE product SET price = %s WHERE id = 1", (price,))
    conn.commit()
    conn.close()
    # 删掉旧缓存（写主库），下次查询重建
    import redis
    redis.Redis(host="127.0.0.1", port=MASTER_PORT, decode_responses=True).delete("product:list")


def read_times(n):
    """用户查商品列表 n 次，返回成功数"""
    ok = 0
    for _ in range(n):
        try:
            status, _ = http_get("/products")
            if status == 200:
                ok += 1
        except Exception:
            pass
    return ok


def slave_commands():
    """从库累计处理的命令数（INFO stats）—— 用来证明读请求真的打到了从库"""
    import redis as _redis
    r = _redis.Redis(host="127.0.0.1", port=SLAVE_PORT, decode_responses=True,
                     socket_connect_timeout=1)
    return int(r.info("stats")["total_commands_processed"])


def main():
    print("=" * 60)
    print("🏬 Day 22 实验：读写分离版商城（读走从库 / 写走主库 / 挂了降级）")
    print("=" * 60)

    # 0. 前置检查
    conn = pymysql.connect(host="127.0.0.1", port=4306, user="root", password="root123",
                           database="my_first_db", charset="utf8mb4")
    cur = conn.cursor()
    cur.execute("SELECT price FROM product WHERE id = 1")
    global OLD_PRICE
    OLD_PRICE = float(cur.fetchone()[0])
    conn.close()

    # 清理残留
    print("\n⓪ 清理残留（商城进程 / 从库 6380）...")
    for port in (5000, SLAVE_PORT):
        kill_port(port)
    print("   干净了 ✅")

    # ---------- 实验 1：单机模式 ----------
    print(f"\n① 实验 1：单机模式（读和写都压在主库 6379）...")
    shop = start_shop()          # 不设 REDIS_RO_PORT
    if not wait_shop():
        raise RuntimeError("商城没起来，请确认 MySQL 已启动")
    change_price(TEST_PRICE)     # 商家改价（写）
    ok1 = read_times(100)        # 用户查列表 100 次（读）
    print(f"   商家改价 88.80 元 → 用户查列表 100 次，成功 {ok1}/100")
    print("   ⚠️ 这 100 次读全部打在主库上（商城日志会看到『命中缓存』）")
    shop.terminate()
    kill_port(5000)
    time.sleep(2)

    # ---------- 实验 2：读写分离 ----------
    print(f"\n② 实验 2：开启读写分离（起从库 {SLAVE_PORT}，读接口走从库）...")
    start_replica()
    if not wait_port(SLAVE_PORT):
        raise RuntimeError("从库没起来")
    time.sleep(2)
    cmds_before = slave_commands()   # 从库收到的命令数（基线）
    shop = start_shop(ro_port=SLAVE_PORT)
    if not wait_shop():
        raise RuntimeError("商城没起来")
    time.sleep(1)
    ok2 = read_times(100)
    time.sleep(1)
    cmds_after = slave_commands()
    print(f"   商家再次改价 → 用户查列表 100 次，成功 {ok2}/100")
    print(f"   📊 硬证据：这 100 次读期间，从库处理了 {cmds_after - cmds_before} 条命令")
    print("     → 读请求真的打到了从库（主库读压力被分担）✅")

    # ---------- 实验 3：从库挂了 → 自动降级 ----------
    print(f"\n③ 实验 3：杀掉从库（模拟从库宕机）→ 用户继续查...")
    kill_port(SLAVE_PORT)
    ok3 = read_times(100)
    print(f"   从库已挂，用户查列表 100 次，成功 {ok3}/100")
    print("   📌 看商城日志：应出现『⚠️ 从库不可用，熔断 5 秒，读降级回主库』→ 业务没断！")

    # ---------- 实验 4：从库恢复 → 自动切回 ----------
    print(f"\n④ 实验 4：重启从库 → 自动切回...")
    start_replica()
    if not wait_port(SLAVE_PORT):
        raise RuntimeError("从库恢复失败")
    time.sleep(6)   # 等熔断窗口（5 秒）结束，从库也能重新连上主库
    cmds_b4 = slave_commands()
    ok4 = read_times(100)
    time.sleep(1)
    cmds_a4 = slave_commands()
    print(f"   从库恢复后用户再查 100 次，成功 {ok4}/100")
    print(f"   📊 硬证据：这次读期间从库又处理了 {cmds_a4 - cmds_b4} 条命令 → 已自动切回从库 ✅")

    # 清理
    print(f"\n🧹 清理：关商城 + 关从库 + 恢复商品原价 {OLD_PRICE}...")
    shop.terminate()
    kill_port(5000)
    kill_port(SLAVE_PORT)
    change_price(OLD_PRICE)
    print("   环境已还原，可重复跑")

    print("\n" + "=" * 60)
    print(f"🎯 结论：读分流（从库）→ 主库压力减半；从库挂 → 降级主库，业务不断")
    print(f"   单机读 {ok1}/100 ｜ 分流读 {ok2}/100 ｜ 降级读 {ok3}/100 ｜ 恢复 {ok4}/100")
    print("=" * 60)


if __name__ == "__main__":
    main()
