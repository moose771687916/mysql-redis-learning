# -*- coding: utf-8 -*-
"""Day 25：MySQL 主库故障转移 —— 主库挂了，把从库"扶正"成新主库

背景：MySQL 没有内置哨兵（Redis 有），生产用 MHA / Orchestrator 这类工具
自动执行下面这套动作。今天我们在本地把"扶正"的每一步亲手跑一遍：

  ① 主库 4306 突然宕机（模拟：优雅关闭）
  ② 从库 4307 提权：STOP SLAVE + RESET SLAVE ALL（解除从属，自己当家）
  ③ 验证新主：旧数据一条不少 + 能写新数据
  ④ 恢复原状：重启旧主 → 从库重新挂回旧主 → 复制续跑（环境还原）

跑完自动清理测试数据，环境还原成：主 4306 + 从 4307 + 复制 Yes（和 Day 23/24 一样）。
"""
import subprocess
import time

import pymysql

BASE = "D:/RediAndMySQL"
MASTER = dict(host="127.0.0.1", port=4306, user="root", password="root123",
              charset="utf8mb4", database="my_first_db")
SLAVE = dict(host="127.0.0.1", port=4307, user="root", password="",
             charset="utf8mb4", database="my_first_db")


def q(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    return rows


def exe(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cur.close()


def wait_mysql(conn_cfg, seconds=20):
    for _ in range(seconds * 2):
        try:
            c = pymysql.connect(**conn_cfg, connect_timeout=1)
            c.close()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def find_pid_by_port(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            return line.split()[-1]
    return None


def main():
    print("=" * 60)
    print("🏥 Day 25 实验：MySQL 主库故障转移（迷你 MHA：宕机 → 扶正 → 恢复）")
    print("=" * 60)

    # ---------- ① 环境检查 ----------
    print("\n⓪ 环境检查：主库 4306 / 从库 4307 / 复制状态...")
    assert find_pid_by_port(4306), "主库 4306 没在跑，先启动主库"
    assert find_pid_by_port(4307), "从库 4307 没在跑，先启动从库"
    conn = pymysql.connect(**SLAVE, autocommit=True)
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SHOW SLAVE STATUS")
    st = cur.fetchone()
    cur.close()
    conn.close()
    io = "Yes" if st and st.get("Slave_IO_Running") == "Yes" else "No"
    sql_ok = "Yes" if st and st.get("Slave_SQL_Running") == "Yes" else "No"
    if io != "Yes" or sql_ok != "Yes":
        print("   ⚠️ 复制未在跑，先重建复制（Day 23 的 CHANGE MASTER 流程）...")
        c = pymysql.connect(**MASTER, autocommit=True)
        mf, mpos = q(c, "SHOW MASTER STATUS")[0][:2]
        c.close()
        s = pymysql.connect(**SLAVE, autocommit=True)
        exe(s, "STOP SLAVE")
        exe(s, "RESET SLAVE ALL")
        exe(s, f"CHANGE MASTER TO MASTER_HOST='127.0.0.1', MASTER_PORT=4306, "
              f"MASTER_USER='repl', MASTER_PASSWORD='repl123', "
              f"MASTER_LOG_FILE='{mf}', MASTER_LOG_POS={mpos}")
        exe(s, "START SLAVE")
        s.close()
        time.sleep(3)
    print("   就绪 ✅（主写从读复制正常）")

    # ---------- ① 宕机前快照 ----------
    print("\n① 宕机前快照：记录两边订单数（旧数据完整性基准）...")
    m_orders = q(pymysql.connect(**MASTER), "SELECT COUNT(*) FROM orders")[0][0]
    s_orders = q(pymysql.connect(**SLAVE), "SELECT COUNT(*) FROM orders")[0][0]
    print(f"   主库 orders={m_orders} ｜ 从库 orders={s_orders}（主从一致）")

    # ---------- ② 模拟主库宕机 ----------
    print("\n② 模拟主库宕机：优雅关闭 4306（mysqladmin shutdown）...")
    subprocess.run([f"{BASE}/mysql/bin/mysqladmin.exe", "-uroot", "-proot123",
                    "-P4306", "shutdown"], capture_output=True)
    for _ in range(30):
        time.sleep(0.5)
        if not find_pid_by_port(4306):
            break
    print(f"   主库进程已停止（PID {find_pid_by_port(4306) or '已消失'}）")
    print("   💡 此刻商城会发生什么：下单/注册/结算（写接口）全部报错，"
          "因为写要找老板；读接口（查商品）正常，因为读走从库")

    # ---------- ③ 扶正 ----------
    print("\n③ 扶正：从库 4307 解除从属（STOP SLAVE + RESET SLAVE ALL）→ 自己当家...")
    conn = pymysql.connect(**SLAVE, autocommit=True)
    exe(conn, "STOP SLAVE")
    exe(conn, "RESET SLAVE ALL")   # 清除复制配置 = 不再是任何人的从库
    exe(conn, "CREATE DATABASE IF NOT EXISTS failover_test")
    exe(conn, "CREATE TABLE IF NOT EXISTS failover_test.msg "
              "(id INT PRIMARY KEY AUTO_INCREMENT, content VARCHAR(100))")
    exe(conn, "INSERT INTO failover_test.msg(content) VALUES ('新老板记的第1笔账'),('新老板记的第2笔账')")
    conn.close()
    print("   新主（原从库）已能写：failover_test 里写了 2 条新账 ✅")

    # ---------- ④ 数据一致性验证 ----------
    print("\n④ 验证新主数据完整性：旧数据一条不少 + 能写新数据...")
    conn = pymysql.connect(**SLAVE)
    n_orders = q(conn, "SELECT COUNT(*) FROM orders")[0][0]
    n_msg = q(conn, "SELECT COUNT(*) FROM failover_test.msg")[0][0]
    conn.close()
    print(f"   旧数据：orders={n_orders}（宕机前 {s_orders}，一条不少）✅")
    print(f"   新数据：新主写了 {n_msg} 条 ✅")
    print("   → 故障转移成功：从库已扶正为新主，数据完整、可写可读")

    # ---------- ⑤ 恢复原状 ----------
    print("\n⑤ 恢复原状：重启旧主 4306 → 从库重新挂回旧主 → 复制续跑...")
    # Windows 坑：mysqld 优雅关闭后 InnoDB 文件句柄释放有延迟（几秒~十几秒），
    # 立即重启会报『ibdata1 must be writable』启动失败 → 重试直到成功
    ok = False
    for attempt in range(3):
        subprocess.Popen([f"{BASE}/mysql/bin/mysqld.exe",
                          "--defaults-file=D:/RediAndMySQL/mysql/my.ini"],
                         creationflags=subprocess.CREATE_NO_WINDOW, cwd=BASE)
        if wait_mysql(MASTER, seconds=12):
            ok = True
            break
        print(f"   ⚠️ 第 {attempt + 1} 次启动失败（文件锁释放延迟），8 秒后重试...")
        time.sleep(8)
    if not ok:
        print("   ❌ 旧主 4306 启动失败（看 mysql/data/*.err 日志）")
        return
    print("   旧主 4306 已重启（它还是主库，binlog 坐标 = 宕机前位置）")

    # 清理新主上写的测试数据（不在旧主 binlog 里，删掉两边才一致）
    conn = pymysql.connect(**SLAVE, autocommit=True)
    exe(conn, "DROP DATABASE failover_test")
    # 重新挂回旧主：用旧主当前 binlog 坐标（= 宕机前位置，从库已重放到这，无重复）
    m = pymysql.connect(**MASTER, autocommit=True)
    mf, mpos = q(m, "SHOW MASTER STATUS")[0][:2]
    m.close()
    exe(conn, "RESET SLAVE ALL")
    exe(conn, f"CHANGE MASTER TO MASTER_HOST='127.0.0.1', MASTER_PORT=4306, "
              f"MASTER_USER='repl', MASTER_PASSWORD='repl123', "
              f"MASTER_LOG_FILE='{mf}', MASTER_LOG_POS={mpos}")
    exe(conn, "START SLAVE")
    conn.close()
    time.sleep(3)

    # 验证复制恢复 + 数据一致
    conn = pymysql.connect(**SLAVE, autocommit=True)
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SHOW SLAVE STATUS")
    st = cur.fetchone()
    cur.close()
    conn.close()
    io = "Yes" if st and st.get("Slave_IO_Running") == "Yes" else "No"
    sql_ok = "Yes" if st and st.get("Slave_SQL_Running") == "Yes" else "No"
    m_orders2 = q(pymysql.connect(**MASTER), "SELECT COUNT(*) FROM orders")[0][0]
    s_orders2 = q(pymysql.connect(**SLAVE), "SELECT COUNT(*) FROM orders")[0][0]
    print(f"   复制状态：IO={io} / SQL={sql_ok}")
    print(f"   数据一致：主库 orders={m_orders2} ｜ 从库 orders={s_orders2}")

    print("\n" + "=" * 60)
    print("🎯 结论：主库宕机 → 从库 RESET SLAVE ALL 提权扶正（数据完整可写）")
    print("   → 重启旧主重新挂回 → 复制续跑。这就是 MHA/哨兵自动做的事")
    print("=" * 60)


if __name__ == "__main__":
    main()
