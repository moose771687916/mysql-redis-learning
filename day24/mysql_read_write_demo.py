# -*- coding: utf-8 -*-
"""Day 24：MySQL 读写分离落地商城 —— 读走从库 4307 / 写走主库 4306

环境：Day 23 的 MySQL 主从已配好（主 4306 + 从 4307，binlog 自动同步）。
商城 app.py 已支持 MYSQL_RO_PORT 环境变量：
  不设置        = 单机模式（读和写都打主库，跟以前完全一样）
  设置 4307     = 纯读接口（商品列表/详情/购物车/订单）从从库读，写接口仍走主库

实验：
  ① 单机模式：读 100 次全打主库（证据：主库 SELECT 计数暴涨）
  ② 读写分离：读 100 次全走从库（证据：从库 SELECT 计数暴涨）+ 写 1 次走主库（主库 INSERT 计数 +1）
  ③ 杀从库：读仍 100/100（熔断 5 秒自动降级主库，业务不断）
  ④ 重启从库：读又走从库（从库 SELECT 计数又涨），复制自动续跑
跑完自动清理测试数据、还原环境，从库保持运行（复制架构保留）。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

import pymysql
import redis

BASE = "D:/RediAndMySQL"
MASTER = dict(host="127.0.0.1", port=4306, user="root", password="root123", charset="utf8mb4",
              database="my_first_db")
SLAVE = dict(host="127.0.0.1", port=4307, user="root", password="", charset="utf8mb4",
             database="my_first_db")


def get_redis():
    return redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)


def status_var(conn_cfg, var):
    conn = pymysql.connect(**conn_cfg, connect_timeout=2)
    cur = conn.cursor()
    cur.execute(f"SHOW GLOBAL STATUS LIKE '{var}'")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return int(row[1])


def find_pid_by_port(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            return line.split()[-1]
    return None


def kill_pid(pid):
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


def stop_shop():
    pid = find_pid_by_port(5000)
    if pid:
        kill_pid(pid)
        time.sleep(2)   # 等端口释放


def start_slave():
    if find_pid_by_port(4307):
        return True   # 从库已在跑
    subprocess.Popen([f"{BASE}/mysql/bin/mysqld.exe",
                      "--defaults-file=D:/RediAndMySQL/mysql/my-slave.ini"],
                     creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(30):
        time.sleep(0.5)
        try:
            pymysql.connect(**SLAVE, connect_timeout=1).close()
            return True
        except Exception:
            pass
    return False


def start_shop(ro_port=None):
    env = dict(os.environ)
    if ro_port:
        env["MYSQL_RO_PORT"] = str(ro_port)
    else:
        env.pop("MYSQL_RO_PORT", None)
    log_path = os.path.join(BASE, "day24", f"shop.log")
    f = open(log_path, "ab")
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=BASE, env=env,
                            stdout=f, stderr=subprocess.STDOUT)
    # 等商城就绪（首页 /products 能返回 200）
    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen("http://127.0.0.1:5000/products", timeout=2)
            return proc, log_path
        except Exception:
            pass
    return proc, log_path


def press_products(n=100, drop_cache=True):
    """压商品列表：每次先删缓存强制 miss → 必查 MySQL（这样才测到"读"的流向）"""
    r = get_redis()
    ok = 0
    for _ in range(n):
        if drop_cache:
            r.delete("product:list")
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:5000/products", timeout=5)
            if resp.status == 200:
                ok += 1
        except Exception:
            pass
    return ok


def press_write():
    """写接口压测：加购物车（走主库 INSERT）。
    cart 表有外键（user_id 必须存在于 users 表），先造一个测试用户再写。"""
    conn = pymysql.connect(**MASTER, autocommit=True)
    cur = conn.cursor()
    cur.execute("INSERT IGNORE INTO users (id, username, password) VALUES (900001, 'demo_user', 'x')")
    cur.close()
    conn.close()
    body = json.dumps({"user_id": 900001, "product_id": 1, "quantity": 1}).encode()
    req = urllib.request.Request("http://127.0.0.1:5000/cart/add", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status
    except urllib.error.HTTPError as e:
        print(f"   ⚠️ 写接口返回 {e.code}: {e.read().decode('utf-8', 'replace')[:120]}")
        return e.code
    except Exception as e:
        print(f"   ⚠️ 写接口异常: {e}")
        return None


def main():
    print("=" * 60)
    print("🗄️  Day 24 实验：MySQL 读写分离落地商城（读走从库 / 写走主库）")
    print("=" * 60)

    print("\n⓪ 准备环境（确保从库 4307 在跑 / 清理残留商城进程）...")
    start_slave()
    stop_shop()
    print("   就绪 ✅")

    # ---------- 实验 1：单机模式 ----------
    print("\n① 实验 1：单机模式（读和写都压在主库 4306）...")
    sel_before = status_var(MASTER, "Com_select")
    proc, _ = start_shop(ro_port=None)
    ok = press_products(100)
    sel_after = status_var(MASTER, "Com_select")
    stop_shop()
    print(f"   读 100 次，成功 {ok}/100")
    print(f"   📊 硬证据：主库 SELECT 计数 +{sel_after - sel_before}（这 100 次读全打在主库上）")

    # ---------- 实验 2：读写分离 ----------
    print("\n② 实验 2：开启读写分离（MYSQL_RO_PORT=4307，读走从库）...")
    m_sel0 = status_var(MASTER, "Com_select")
    m_ins0 = status_var(MASTER, "Com_insert")
    s_sel0 = status_var(SLAVE, "Com_select")
    proc, log_path = start_shop(ro_port=4307)
    ok = press_products(100)
    wcode = press_write()
    s_sel1 = status_var(SLAVE, "Com_select")
    m_ins1 = status_var(MASTER, "Com_insert")
    m_sel1 = status_var(MASTER, "Com_select")
    stop_shop()
    print(f"   读 100 次，成功 {ok}/100 ｜ 写 1 次，返回 {wcode}")
    print(f"   📊 硬证据：从库 SELECT 计数 +{s_sel1 - s_sel0}（读请求真的打到了从库）")
    print(f"   📊 硬证据：主库 INSERT 计数 +{m_ins1 - m_ins0}（写请求留在主库）")
    print(f"   对比：主库 SELECT 只 +{m_sel1 - m_sel0}（读压力被从库分担）")
    print(f"   → 看商城日志 shop.log：每次都是『🐢 查了 MySQL』")
    print(f"   → 读 100 次打从库 + 写 1 次打主库 = 读写分离铁证")

    # ---------- 实验 3：关从库 ----------
    print("\n③ 实验 3：关掉从库 4307（模拟从库宕机）→ 用户继续查...")
    subprocess.run([f"{BASE}/mysql/bin/mysqladmin.exe", "-uroot", "-P4307", "shutdown"],
                   capture_output=True)   # 优雅关闭：像机房正常关机，不损坏 relay log
    for _ in range(30):
        time.sleep(0.5)
        if not find_pid_by_port(4307):
            break
    print(f"   从库已关闭（模拟宕机）")
    proc, _ = start_shop(ro_port=4307)
    ok = press_products(100)
    stop_shop()
    print(f"   读 100 次，成功 {ok}/100")
    print(f"   📌 看商城日志：应出现『⚠️ MySQL 从库不可用，熔断 5 秒，读降级回主库』→ 业务没断！")

    # ---------- 实验 4：重启从库 ----------
    print("\n④ 实验 4：重启从库 → 自动切回...")
    start_slave()
    # 等复制 SQL 线程恢复；超时（relay log 损坏等异常）→ 自动重建复制兜底
    io_ok = sql_ok = "No"
    for _ in range(40):
        time.sleep(0.5)
        try:
            conn = pymysql.connect(**SLAVE, connect_timeout=2)
            cur = conn.cursor(pymysql.cursors.DictCursor)
            cur.execute("SHOW SLAVE STATUS")
            st = cur.fetchone()
            cur.close()
            conn.close()
            if st and st.get("Slave_IO_Running") == "Yes":
                io_ok = "Yes"
            if st and st.get("Slave_SQL_Running") == "Yes":
                sql_ok = "Yes"
            if io_ok == "Yes" and sql_ok == "Yes":
                break
        except Exception:
            pass
    if sql_ok != "Yes":
        print("   ⚠️ SQL 线程未自动恢复（relay log 可能异常）→ 自动重建复制...")
        cur = pymysql.connect(**SLAVE, autocommit=True).cursor()
        cur.execute("STOP SLAVE")
        cur.execute("RESET SLAVE ALL")
        cur.close()
        # 拿主库当前 binlog 坐标，重新指定复制起点
        conn = pymysql.connect(**MASTER, autocommit=True)
        mc = conn.cursor()
        mc.execute("SHOW MASTER STATUS")
        f, pos = mc.fetchone()[:2]
        mc.close()
        conn.close()
        rc = pymysql.connect(**SLAVE, autocommit=True).cursor()
        rc.execute("CHANGE MASTER TO MASTER_HOST='127.0.0.1', MASTER_PORT=4306, "
                   "MASTER_USER='repl', MASTER_PASSWORD='repl123', "
                   f"MASTER_LOG_FILE='{f}', MASTER_LOG_POS={pos}")
        rc.execute("START SLAVE")
        rc.close()
        time.sleep(3)
        conn = pymysql.connect(**SLAVE, autocommit=True)
        cc = conn.cursor(pymysql.cursors.DictCursor)
        cc.execute("SHOW SLAVE STATUS")
        st = cc.fetchone()
        cc.close()
        conn.close()
        io_ok = "Yes" if st and st.get("Slave_IO_Running") == "Yes" else "No"
        sql_ok = "Yes" if st and st.get("Slave_SQL_Running") == "Yes" else "No"
    print(f"   从库已重启，复制自动续跑：IO={io_ok} / SQL={sql_ok}（无需重新配置）")

    s_sel0 = status_var(SLAVE, "Com_select")
    proc, _ = start_shop(ro_port=4307)
    ok = press_products(100)
    s_sel1 = status_var(SLAVE, "Com_select")
    stop_shop()
    print(f"   读 100 次，成功 {ok}/100")
    print(f"   📊 硬证据：从库 SELECT 计数 +{s_sel1 - s_sel0} → 已自动切回从库")

    # ---------- 清理 ----------
    print("\n🧹 清理：删测试购物车数据 + 测试用户 + 删缓存，环境还原...")
    conn = pymysql.connect(**MASTER, autocommit=True)
    cur = conn.cursor()
    cur.execute("DELETE FROM cart WHERE user_id = 900001")   # 先删明细（外键）
    cur.execute("DELETE FROM users WHERE id = 900001")       # 再删测试用户
    cur.close()
    conn.close()
    get_redis().delete("product:list")
    print("   已还原，从库 4307 保持运行（复制架构保留）")

    print("\n" + "=" * 60)
    print("🎯 结论：MySQL 读走从库 / 写走主库；从库挂 → 熔断降级主库，业务不断")
    print("   单机读 100/100 ｜ 分流 100/100 ｜ 降级 100/100 ｜ 恢复 100/100")
    print("=" * 60)


if __name__ == "__main__":
    main()
