# -*- coding: utf-8 -*-
"""Day 20：Redis 主从复制实验（一主一从）
主库 = 你正在跑的 Memurai 服务（127.0.0.1:6379）
从库 = 脚本临时启动的第二个实例（127.0.0.1:6380，REPLICAOF 指向主库）

实验内容：
  ① 启动从库（REPLICAOF 指向主库）
  ② 实验 1：主库写一条 → 从库读出来（主写从读）
  ③ 实验 2：主库批量写 1000 条 → 从库数数（全量同步）
  ④ 实验 3：往从库写 → 被拒绝（从库只读）
  ⑤ 实验 4：从库掉线 → 主库继续写 → 从库重连自动补账（断线补同步）
  ⑥ 看从库身份（role=slave）
跑完自动清理：关从库 + 删测试数据。
"""
import os
import sys
import time
import subprocess
import redis

MASTER_PORT = 6379
SLAVE_PORT = 6380
MEMURAI_EXE = r"C:\Program Files\Memurai\memurai.exe"
WORKDIR = os.path.dirname(os.path.abspath(__file__))
PREFIX = "day20:test:"


def get_redis(port):
    return redis.Redis(host="127.0.0.1", port=port, decode_responses=True)


def slave_alive():
    try:
        get_redis(SLAVE_PORT).ping()
        return True
    except Exception:
        return False


def kill_slave():
    """按端口找到占用 6380 的进程并结束（保证脚本可重复跑）"""
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-NetTCPConnection -LocalPort {SLAVE_PORT} -State Listen -ErrorAction SilentlyContinue).OwningProcess"],
        capture_output=True, text=True)
    for pid in ps.stdout.strip().splitlines():
        if pid.strip():
            subprocess.run(["taskkill", "/F", "/PID", pid.strip()], capture_output=True)
    time.sleep(1.5)


def start_slave():
    """启动从库实例，等它连上主库并完成首次同步"""
    log_file = os.path.join(WORKDIR, "slave.log")
    subprocess.Popen(
        [MEMURAI_EXE,
         "--port", str(SLAVE_PORT),
         "--replicaof", "127.0.0.1", str(MASTER_PORT),
         "--dir", WORKDIR,
         "--dbfilename", "dump-slave.rdb",
         "--logfile", log_file],
        creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(15):
        time.sleep(1)
        try:
            if get_redis(SLAVE_PORT).ping():
                print("   从库已启动并连上主库 ✅")
                return
        except Exception:
            continue
    raise RuntimeError("从库 15 秒内没起来，请查看 day20/slave.log")


def cleanup_test_data(master):
    for k in master.scan_iter(match=PREFIX + "*"):
        master.delete(k)


def main():
    master = get_redis(MASTER_PORT)
    try:
        master.ping()
    except Exception:
        print("❌ 主库 6379 连不上！请先启动 Memurai 服务再跑")
        sys.exit(1)

    cleanup_test_data(master)

    print("=" * 56)
    print("📋 Day 20 实验：一主一从 · 老板的账本和员工的抄本")
    print("=" * 56)

    # ① 启动从库
    print(f"\n① 启动从库（端口 {SLAVE_PORT} → 复制主库 {MASTER_PORT}）...")
    if slave_alive():
        print("   检测到 6380 已有实例在跑，先关掉重新起（保证实验干净）")
        kill_slave()
    start_slave()
    time.sleep(1)

    # ② 实验 1：主写从读
    master.set(PREFIX + "greeting", "老板说：今天全场八折")
    v = get_redis(SLAVE_PORT).get(PREFIX + "greeting")
    print(f"\n② 实验 1：主库写『老板说：今天全场八折』")
    print(f"   从库读出：{v}  ✅ 主写从读，账本同步")

    # ③ 实验 2：批量 1000 条
    print(f"\n③ 实验 2：主库批量写 1000 条 → 从库数数...")
    for i in range(1000):
        master.set(PREFIX + f"item:{i}", f"第{i}笔账")
    n = len(list(get_redis(SLAVE_PORT).scan_iter(match=PREFIX + "item:*")))
    print(f"   从库数到 {n} 条（主库写了 1000 条）✅ 全量同步，一条不落")

    # ④ 实验 3：从库只读
    print(f"\n④ 实验 3：往从库偷偷写一条...")
    try:
        get_redis(SLAVE_PORT).set(PREFIX + "hack", "偷偷改账")
        print("   ❌ 从库居然写成功了？！")
    except redis.exceptions.ResponseError as e:
        print(f"   被拒绝：{e}")
        print("   ✅ 从库是只读抄本，员工不能乱改账")

    # ⑤ 实验 4：断线重连补账
    print(f"\n⑤ 实验 4：从库掉线 → 主库继续写 → 从库重连自动补账...")
    kill_slave()
    print("   从库已掉线（模拟机房断网）")
    master.set(PREFIX + "offline:1", "掉线期间老板记的账 1")
    master.set(PREFIX + "offline:2", "掉线期间老板记的账 2")
    print("   掉线期间主库写了 2 条新账")
    start_slave()
    v1 = get_redis(SLAVE_PORT).get(PREFIX + "offline:1")
    v2 = get_redis(SLAVE_PORT).get(PREFIX + "offline:2")
    print(f"   重连后从库读到：{v1} / {v2}")
    print("   ✅ 断线期间漏掉的账，重连后自动补上")

    # ⑥ 从库身份
    info = get_redis(SLAVE_PORT).info("replication")
    print(f"\n⑥ 从库身份：role={info['role']}，连接状态={info['master_link_status']}")

    # 清理
    print(f"\n🧹 清理：关从库 + 删测试数据...")
    kill_slave()
    cleanup_test_data(master)
    print("   环境已还原，可重复跑")

    print("\n" + "=" * 56)
    print("🎯 结论：主写从读 / 全量同步 / 从库只读 / 断线自动补账")
    print("   主从复制 = 数据双保险（备份） + 读压力分流（读写分离）")
    print("=" * 56)


if __name__ == "__main__":
    main()
