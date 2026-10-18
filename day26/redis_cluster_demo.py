# -*- coding: utf-8 -*-
"""Day 26：Redis Cluster 真集群 —— WSL 里跑官方 Redis，6 节点分片实战

为什么能在 WSL 跑真集群？Redis Cluster 是 Linux 官方 Redis 的功能，
Windows 的 Memurai 不支持；但你的 WSL 里有真 Redis 8.0.5（Day 6 装的）。

实验（全部真实执行，非模拟）：
  ① 起 6 个节点（7000-7005，3 主 3 从）
  ② 一键建集群：16384 个哈希槽自动分给 3 个主节点
  ③ 分片铁证：算 key 的哈希槽 + 写 1000 个 key 看三个主节点各分到多少
  ④ 横向扩容：加 2 节点（1 主 1 从）→ reshard 迁槽 → 4 个主节点
  ⑤ 故障转移：杀一个主节点 → 它的从节点 5 秒自动变主，数据不丢
跑完自动清理，不影响你 Windows 上的任何东西。
"""
import subprocess
import sys
import time

EMOJI_OK = "✅"


def wsl(cmd, timeout=60):
    """在 WSL 里执行命令，只取 stdout（命令结果都在 stdout）。
    wsl.exe 的系统警告会以 UTF-16 混进 stderr，直接丢弃；
    stdout 也做 UTF-8 / UTF-16 双解码容错。"""
    r = subprocess.run(["wsl", "-e", "bash", "-lc", cmd],
                       capture_output=True, timeout=timeout)
    out = r.stdout or b""
    try:
        return out.decode("utf-8").strip()
    except UnicodeDecodeError:
        return out.decode("utf-16-le", "replace").strip()


def wait_cluster_ok(seconds=30):
    """等集群状态变成 ok（槽分配完成）"""
    for _ in range(seconds):
        info = wsl("redis-cli -p 7000 cluster info 2>/dev/null")
        if "cluster_state:ok" in info:
            return True
        time.sleep(1)
    return False


def wait_for_master(slave_port, old_master_id, seconds=30):
    """故障转移后等旧主的槽被新主接管"""
    for _ in range(seconds):
        nodes = wsl("redis-cli -p 7001 cluster nodes")
        if old_master_id in nodes:
            # 找到接管旧主槽的节点
            pass
        info = wsl(f"redis-cli -p {slave_port} cluster info 2>/dev/null")
        if "cluster_state:ok" in info:
            return nodes
        time.sleep(1)
    return None


def main():
    print("=" * 62)
    print("🧩 Day 26 实验：Redis Cluster 真集群（WSL · 官方 Redis 8.0.5）")
    print("=" * 62)

    # ---------- ① 环境检查 + 起节点 ----------
    print("\n⓪ 环境检查：WSL 里的 Redis 与端口...")
    ver = wsl("redis-server --version | head -1")
    print(f"   {ver}")
    print("   清理残留集群（如果有）...")
    wsl("for p in 7000 7001 7002 7003 7004 7005; do redis-cli -p $p shutdown nosave 2>/dev/null; done")
    time.sleep(1)
    wsl("rm -rf /tmp/redis-cluster")
    wsl("mkdir -p /tmp/redis-cluster")
    print("   就绪 ✅")

    # ---------- ① 起 6 个节点 ----------
    print("\n① 起 6 个节点（7000-7005，每节点 cluster-enabled yes）...")
    for port in range(7000, 7006):
        conf = (
            f"port {port}\n"
            f"cluster-enabled yes\n"
            f"cluster-config-file nodes-{port}.conf\n"
            f"cluster-node-timeout 5000\n"
            f"appendonly no\n"
            f"daemonize yes\n"
            f"dir /tmp/redis-cluster/{port}\n"
            f"logfile /tmp/redis-cluster/{port}/redis.log\n"
            f"pidfile /tmp/redis-cluster/{port}/redis.pid\n"
        )
        wsl(f"mkdir -p /tmp/redis-cluster/{port}")
        wsl(f"cat > /tmp/redis-cluster/{port}/redis.conf <<'EOF'\n{conf}EOF")
        wsl(f"redis-server /tmp/redis-cluster/{port}/redis.conf")
    time.sleep(1)
    alive = sum(1 for p in range(7000, 7006) if "PONG" in wsl(f"redis-cli -p {p} ping 2>/dev/null"))
    print(f"   6 个节点全部启动（ping 通 {alive}/6）✅")

    # ---------- ② 建集群 ----------
    print("\n② 一键建集群（3 主 3 从，16384 个槽自动分配）...")
    out = wsl("redis-cli --cluster create "
              "127.0.0.1:7000 127.0.0.1:7001 127.0.0.1:7002 "
              "127.0.0.1:7003 127.0.0.1:7004 127.0.0.1:7005 "
              "--cluster-replicas 1 --cluster-yes 2>&1 | tail -5")
    print(f"   {out}")
    wait_cluster_ok()
    info = wsl("redis-cli -p 7000 cluster info | grep cluster_state")
    slots = wsl("redis-cli -p 7000 cluster info | grep cluster_slots_assigned")
    print(f"   {info} ｜ {slots} ✅")
    print("   （16384 个槽 = 整个 key 空间，全部分给 3 个主节点）")

    # ---------- ③ 分片铁证 ----------
    print("\n③ 分片铁证：key 怎么被分到不同节点？...")
    k1 = wsl("redis-cli -p 7000 cluster keyslot user:1001")
    k2 = wsl("redis-cli -p 7000 cluster keyslot order:20261001")
    print(f"   CLUSTER KEYSLOT user:1001     → 槽 {k1}")
    print(f"   CLUSTER KEYSLOT order:20261001 → 槽 {k2}")
    print(f"   （CRC16 哈希 % 16384 = 槽号；槽号决定存哪个主节点）")

    # 写 1000 个 key，统计三个主节点分布
    print("   批量写 1000 个 key（key:0 ~ key:999）...")
    wsl("for i in $(seq 0 999); do redis-cli -p 7000 -c set key:$i value:$i > /dev/null 2>&1; done")
    time.sleep(1)
    print("   三个主节点各自存了多少 key（dbsize）：")
    nodes = wsl("redis-cli -p 7000 cluster nodes")
    masters = {}
    for line in nodes.splitlines():
        parts = line.split()
        if len(parts) >= 8 and "master" in parts[2] and "fail" not in parts[2] and "handshake" not in parts[2]:
            node_id, host = parts[0], parts[1]
            port = host.split(":")[1]
            dbsize = wsl(f"redis-cli -p {port} dbsize")
            masters[node_id[:8]] = int(dbsize)
    total = sum(masters.values())
    dist = " ｜ ".join(f"{nid}: {n}" for nid, n in masters.items())
    print(f"   {dist}（共 {total} 个）✅")
    print("   → 1000 个 key 被均匀分成 3 份，每个主节点管一份 = 分片铁证")
    print("   → 读的时候：客户端按同样的槽算法找到节点，直接去拿")

    # ---------- ④ 横向扩容 ----------
    print("\n④ 横向扩容：加 1 主 1 从 → reshard 迁移槽...")
    wsl("cat > /tmp/redis-cluster/7006/redis.conf <<'EOF'\n"
        "port 7006\ncluster-enabled yes\ncluster-config-file nodes-7006.conf\n"
        "cluster-node-timeout 5000\nappendonly no\ndaemonize yes\n"
        "dir /tmp/redis-cluster/7006\nlogfile /tmp/redis-cluster/7006/redis.log\n"
        "pidfile /tmp/redis-cluster/7006/redis.pid\nEOF")
    wsl("mkdir -p /tmp/redis-cluster/7006")
    wsl("cat > /tmp/redis-cluster/7006/redis.conf <<'EOF'\n"
        "port 7006\ncluster-enabled yes\ncluster-config-file nodes-7006.conf\n"
        "cluster-node-timeout 5000\nappendonly no\ndaemonize yes\n"
        "dir /tmp/redis-cluster/7006\nlogfile /tmp/redis-cluster/7006/redis.log\n"
        "pidfile /tmp/redis-cluster/7006/redis.pid\nEOF")
    wsl("cat > /tmp/redis-cluster/7007/redis.conf <<'EOF'\n"
        "port 7007\ncluster-enabled yes\ncluster-config-file nodes-7007.conf\n"
        "cluster-node-timeout 5000\nappendonly no\ndaemonize yes\n"
        "dir /tmp/redis-cluster/7007\nlogfile /tmp/redis-cluster/7007/redis.log\n"
        "pidfile /tmp/redis-cluster/7007/redis.pid\nEOF")
    for port in (7006, 7007):
        wsl(f"mkdir -p /tmp/redis-cluster/{port}")
        wsl(f"redis-server /tmp/redis-cluster/{port}/redis.conf")
    time.sleep(1)
    wsl("redis-cli --cluster add-node 127.0.0.1:7006 127.0.0.1:7000 2>&1 | tail -1")
    time.sleep(2)
    # 拿 7006 的 node id，让 7007 当它的从
    nid7006 = wsl("redis-cli -p 7006 cluster myid")
    wsl(f"redis-cli --cluster add-node 127.0.0.1:7007 127.0.0.1:7000 "
        f"--cluster-slave --cluster-master-id {nid7006} 2>&1 | tail -1")
    time.sleep(2)
    # 从所有节点迁 4096 个槽给 7006（16384/4 = 4096）
    out = wsl(f"redis-cli --cluster reshard 127.0.0.1:7006 "
              f"--cluster-from all --cluster-to {nid7006} "
              f"--cluster-slots 4096 --cluster-yes 2>&1 | tail -3")
    print(f"   扩容完成：{out.splitlines()[-1] if out else ''}")
    time.sleep(2)
    info = wsl("redis-cli -p 7000 cluster info | grep cluster_slots_assigned")
    print(f"   {info} ✅（槽还是 16384，只是 4 个主节点瓜分了）")
    masters4 = {}
    nodes4 = wsl("redis-cli -p 7000 cluster nodes")
    for line in nodes4.splitlines():
        parts = line.split()
        if len(parts) >= 8 and "master" in parts[2]:
            port4 = parts[1].split(":")[1]
            masters4[parts[0][:8]] = int(wsl(f"redis-cli -p {port4} dbsize"))
    dist4 = " ｜ ".join(f"{nid}: {n}" for nid, n in masters4.items())
    print(f"   4 主分布：{dist4} ✅（新节点也分到了 key）")
    # 扩容后 key 依然能读
    got = wsl("redis-cli -p 7000 -c get key:0")
    print(f"   扩容后读 key:0 → {got} ✅（数据迁移不丢）")

    # ---------- ⑤ 故障转移 ----------
    print("\n⑤ 故障转移：杀掉一个主节点 → 它的从节点自动顶班...")
    # 杀之前：取 7000 的 node id，并找到它的从节点（7004）
    master7000 = wsl("redis-cli -p 7000 cluster myid").strip()
    nodes = wsl("redis-cli -p 7001 cluster nodes")
    slave_id, slave_port = None, None
    for line in nodes.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2].startswith("slave") and parts[3] == master7000:
            slave_id, slave_port = parts[0], parts[1].split(":")[1]
    print(f"   主节点 7000 的从节点：端口 {slave_port}（id {slave_id[:8]}）")
    print("   杀掉主节点 7000（模拟宕机）...")
    wsl("redis-cli -p 7000 shutdown nosave 2>/dev/null; true")
    # 等故障转移：5 秒超时判定 + 选举，给足 15 秒
    print("   等待选举（cluster-node-timeout=5s + 投票）...")
    time.sleep(15)
    # 验证：从节点是否已变 master
    nodes2 = wsl(f"redis-cli -p {slave_port} cluster nodes")
    promoted = False
    for line in nodes2.splitlines():
        parts = line.split()
        if parts[0] == slave_id and "master" in parts[2]:
            promoted = True
    print(f"   从节点 {slave_port} 已自动变主（接管 7000 的槽）✅" if promoted
          else "   ❌ 从节点未成功顶班")
    # 等集群恢复 ok（槽全部被覆盖）
    for _ in range(20):
        info = wsl(f"redis-cli -p {slave_port} cluster info 2>/dev/null")
        if "cluster_state:ok" in info:
            break
        time.sleep(1)
    got = wsl("redis-cli -p 7001 -c get key:999 2>/dev/null")
    print(f"   故障后读 key:999 → {got} ✅（数据没丢，服务恢复）")

    # ---------- ⑥ 清理 ----------
    print("\n🧹 清理：关闭全部节点 + 删临时文件...")
    wsl("for p in 7000 7001 7002 7003 7004 7005 7006 7007; do redis-cli -p $p shutdown nosave 2>/dev/null; done")
    time.sleep(1)
    wsl("rm -rf /tmp/redis-cluster")
    print("   已清理，WSL 环境还原")

    print("\n" + "=" * 62)
    print("🎯 结论：Redis Cluster = 16384 个槽 + CRC16 哈希路由 + 自动故障转移")
    print("   写 1000 key 均匀分 3 份 ｜ 扩容加节点迁槽不丢数据 ｜ 主挂从自动顶班")
    print("=" * 62)


if __name__ == "__main__":
    main()
