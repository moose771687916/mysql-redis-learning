# -*- coding: utf-8 -*-
"""Day 21：主库挂了怎么办 —— 哨兵自动故障转移实战

故事线：开了一家店（主库 6390），员工抄本（从库 6391），门口请了哨兵（26379）。
老板突然倒下（杀主库）→ 哨兵自动把员工扶正成新老板 → 店照常营业（新主能写）。

三个实例全部由脚本临时启动，跑完自动清理，完全不碰你日常用的 6379 服务。

实验：
  ① 一主一从 + 哨兵全部就位
  ② 实验 1：主写从读，哨兵确认当前主库是 6390
  ③ 实验 2：杀掉主库 6390（老板倒下）→ 哨兵自动切换
  ④ 实验 3：新主 6391 能读旧数据（备份没丢）且能写（业务恢复）
  ⑤ 哨兵眼中的新主库地址
跑完自动清理：关从库 + 关哨兵 + 删测试文件。
"""
import os
import sys
import time
import subprocess
import redis

MASTER_PORT = 6390
REPLICA_PORT = 6391
SENTINEL_PORT = 26379
MEMURAI_EXE = r"C:\Program Files\Memurai\memurai.exe"
WORKDIR = os.path.dirname(os.path.abspath(__file__))
PREFIX = "day21:test:"
SENTINEL_CONF = os.path.join(WORKDIR, "sentinel.conf")


def get_redis(port):
    return redis.Redis(host="127.0.0.1", port=port, decode_responses=True)


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


def wait_ping(port, seconds=15):
    for _ in range(seconds):
        time.sleep(1)
        try:
            if get_redis(port).ping():
                return True
        except Exception:
            continue
    return False


def start_instance(port, extra_args=None):
    args = [MEMURAI_EXE, "--port", str(port), "--dir", WORKDIR,
            "--dbfilename", f"dump-{port}.rdb", "--logfile", os.path.join(WORKDIR, f"instance-{port}.log")]
    if extra_args:
        args += extra_args
    subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)


def write_sentinel_conf():
    """哨兵配置文件（无 BOM！Memurai 遇到 BOM 会报 Bad directive）"""
    content = "\n".join([
        f"port {SENTINEL_PORT}",
        f"sentinel monitor mymaster 127.0.0.1 {MASTER_PORT} 1",
        "sentinel down-after-milliseconds mymaster 5000",
        "sentinel failover-timeout mymaster 15000",
        "sentinel parallel-syncs mymaster 1",
        "",
    ])
    with open(SENTINEL_CONF, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def sentinel_master_addr():
    r = get_redis(SENTINEL_PORT)
    return r.execute_command("SENTINEL", "get-master-addr-by-name", "mymaster")


def main():
    print("=" * 56)
    print("🏥 Day 21 实验：老板倒下，哨兵自动扶正新老板")
    print("=" * 56)

    # 0. 清理残留（保证可重复跑）
    print("\n⓪ 清理残留实例（如果上一轮没跑完）...")
    for port in (SENTINEL_PORT, REPLICA_PORT, MASTER_PORT):
        kill_port(port)
    print("   干净了 ✅")

    # 1. 起一主一从
    print(f"\n① 启动临时主库 {MASTER_PORT} + 从库 {REPLICA_PORT}（复制主库）...")
    start_instance(MASTER_PORT)
    wait_ping(MASTER_PORT)
    start_instance(REPLICA_PORT, ["--replicaof", "127.0.0.1", str(MASTER_PORT)])
    wait_ping(REPLICA_PORT)
    time.sleep(2)  # 等首次同步完成
    print("   主从就位 ✅")

    # 2. 起哨兵
    print(f"   启动哨兵 {SENTINEL_PORT}（监控 mymaster = 主库 {MASTER_PORT}）...")
    write_sentinel_conf()
    subprocess.Popen([MEMURAI_EXE, SENTINEL_CONF, "--sentinel", "--dir", WORKDIR],
                     creationflags=subprocess.CREATE_NO_WINDOW)
    if not wait_ping(SENTINEL_PORT):
        raise RuntimeError("哨兵没起来，请查看 day21 目录日志")
    time.sleep(3)
    print("   哨兵就位 ✅")

    # 3. 实验 1：主写从读
    master = get_redis(MASTER_PORT)
    master.set(PREFIX + "greeting", "老板说：今天全场八折")
    v = get_redis(REPLICA_PORT).get(PREFIX + "greeting")
    print(f"\n② 实验 1：主库写『老板说：今天全场八折』")
    print(f"   从库读出：{v}  ✅ 复制正常")
    addr = sentinel_master_addr()
    print(f"   哨兵眼中的主库：{addr[0]}:{addr[1]}  ✅ 监控中")

    # 4. 实验 2：杀主库，等自动切换
    print(f"\n③ 实验 2：杀掉主库 {MASTER_PORT}（老板突然倒下！）...")
    kill_port(MASTER_PORT)
    print("   主库已倒下，哨兵开始判定（约 15~20 秒）...")
    for i in range(30):
        time.sleep(1)
        addr = sentinel_master_addr()
        if addr[1] == str(REPLICA_PORT):
            print(f"   ⏱ {i+1} 秒后，哨兵宣布新主库：{addr[0]}:{addr[1]} ✅ 自动扶正！")
            break
    else:
        raise RuntimeError("30 秒内哨兵没切换，请查看哨兵日志")

    # 5. 实验 3：新主读旧数据 + 能写
    new_master = get_redis(REPLICA_PORT)
    v = new_master.get(PREFIX + "greeting")
    print(f"\n④ 实验 3：新主读旧数据：{v}  ✅ 账本没丢")
    new_master.set(PREFIX + "newboss", "新老板上任")
    v2 = new_master.get(PREFIX + "newboss")
    print(f"   新主写新账：{v2}  ✅ 业务恢复（店继续营业）")
    info = new_master.info("replication")
    print(f"   新主身份：role={info['role']}")

    # 6. 清理
    print(f"\n🧹 清理：关从库（新主）+ 关哨兵 + 删测试文件...")
    kill_port(REPLICA_PORT)
    kill_port(SENTINEL_PORT)
    for fname in ("sentinel.conf", "dump-6390.rdb", "dump-6391.rdb",
                  "instance-6390.log", "instance-6391.log"):
        fp = os.path.join(WORKDIR, fname)
        if os.path.exists(fp):
            os.remove(fp)
    print("   环境已还原，可重复跑")

    print("\n" + "=" * 56)
    print("🎯 结论：哨兵 = 自动盯梢 + 自动扶正，业务无感切换")
    print("   主库挂 → 哨兵自动把从库扶正 → 数据不丢、服务不停")
    print("=" * 56)


if __name__ == "__main__":
    main()
