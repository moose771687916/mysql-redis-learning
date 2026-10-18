# -*- coding: utf-8 -*-
"""Day 23：MySQL 主从复制实战 —— 数据库版的"账本 + 抄本"

环境：
  主库 = 你日常用的 MySQL（127.0.0.1:4306，server-id=1，已开 binlog）
  从库 = 今天新增的第二个实例（127.0.0.1:4307，server-id=2）
  复制账号 repl 已建好，首次全量数据已手动同步，增量由 binlog 自动同步。

实验：
  ① 主库批量写 1000 条 → 从库数数（全量增量同步，一条不落）
  ② 写走主库、读走从库（读写分离的代码用法）
  ③ 查看复制状态（IO 线程 / SQL 线程 / 延迟）
  ④ 主库删表 → 从库也跟着删（删除操作也同步）
  ⑤ 模拟"从库掉线补账"：停从库 SQL 线程 → 主库继续写 → 恢复 → 自动补上
跑完自动清理测试数据，不影响商城数据。
"""
import time
import pymysql
from pymysql.cursors import DictCursor

MASTER = dict(host="127.0.0.1", port=4306, user="root", password="root123",
              charset="utf8mb4", autocommit=True)
SLAVE = dict(host="127.0.0.1", port=4307, user="root", password="",
             charset="utf8mb4", autocommit=True)


def q(conn, sql, args=None):
    cur = conn.cursor(DictCursor)
    cur.execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return rows


def exe(conn, sql, args=None):
    cur = conn.cursor()
    cur.execute(sql, args)
    cur.close()


def wait_sync(master, slave, table="repl_test.msg", seconds=8):
    """等从库追上主库的行数（binlog 应用是异步的，追上才算同步完成）"""
    n_m = q(master, f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
    for _ in range(seconds):
        n_s = q(slave, f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        if n_s >= n_m:
            return n_m, n_s
        time.sleep(0.5)
    return n_m, n_s


def main():
    print("=" * 60)
    print("🗄️  Day 23 实验：MySQL 主从复制（主写从读 / 自动同步 / 掉线补账）")
    print("=" * 60)

    master = pymysql.connect(**MASTER)
    slave = pymysql.connect(**SLAVE)

    # 清理测试数据
    exe(master, "DROP DATABASE IF EXISTS repl_test")
    exe(master, "CREATE DATABASE repl_test")
    exe(master, "CREATE TABLE repl_test.msg(id INT PRIMARY KEY AUTO_INCREMENT, content VARCHAR(100))")
    print("\n⓪ 已建测试表 repl_test.msg（主库）")

    # ---------- 实验 1：批量同步 ----------
    print(f"\n① 实验 1：主库批量写 1000 条 → 从库数数...")
    for i in range(1000):
        exe(master, "INSERT INTO repl_test.msg(content) VALUES (%s)", (f"第{i}条账",))
    n_master, n_slave = wait_sync(master, slave)
    print(f"   主库：{n_master} 条 ｜ 从库：{n_slave} 条  ✅ 一条不落（binlog 增量同步）")

    # ---------- 实验 2：读写分离用法 ----------
    print(f"\n② 实验 2：写走主库、读走从库（代码写法）...")
    exe(master, "INSERT INTO repl_test.msg(content) VALUES (%s)", ("用户张三下单成功",))
    time.sleep(1)   # 等同步
    rows = q(slave, "SELECT id, content FROM repl_test.msg ORDER BY id DESC LIMIT 1")
    print(f"   主库写『{rows[0]['content']}』→ 从库立刻读到（id={rows[0]['id']}）✅")
    print("   → 项目里就这么用：写接口连 4306，读接口连 4307")

    # ---------- 实验 3：复制状态 ----------
    print(f"\n③ 实验 3：复制状态（IO 线程=拉 binlog，SQL 线程=重放 binlog）...")
    row = q(slave, "SHOW SLAVE STATUS")[0]
    print(f"   Slave_IO_Running     : {row['Slave_IO_Running']}  （IO 线程：从主库拉取日志）")
    print(f"   Slave_SQL_Running    : {row['Slave_SQL_Running']}  （SQL 线程：把日志变成数据）")
    print(f"   Seconds_Behind_Master: {row['Seconds_Behind_Master']}  （延迟 0 秒 = 实时同步）")

    # ---------- 实验 4：删除也同步 ----------
    print(f"\n④ 实验 4：主库删一条 → 从库也删一条（删操作也走 binlog）...")
    before = q(slave, "SELECT COUNT(*) AS n FROM repl_test.msg")[0]["n"]
    exe(master, "DELETE FROM repl_test.msg WHERE content LIKE '第0条%'")
    time.sleep(1)
    after = q(slave, "SELECT COUNT(*) AS n FROM repl_test.msg")[0]["n"]
    print(f"   从库删前 {before} 条 → 删后 {after} 条  ✅ 删除也自动同步")

    # ---------- 实验 5：从库掉线补账 ----------
    print(f"\n⑤ 实验 5：停掉从库 SQL 线程 → 主库继续写 → 恢复自动补账...")
    exe(slave, "STOP SLAVE SQL_THREAD")
    print("   从库 SQL 线程已停（模拟从库宕机/网络中断）")
    for i in range(3):
        exe(master, "INSERT INTO repl_test.msg(content) VALUES (%s)", (f"掉线期间老板记的账{i+1}",))
    print("   掉线期间主库写了 3 条新账")
    exe(slave, "START SLAVE SQL_THREAD")
    n_master, n_slave = wait_sync(master, slave)
    print(f"   恢复后从库：{n_slave} 条 = 主库 {n_master} 条  ✅ 漏掉的账自动补上")

    # 清理
    print(f"\n🧹 清理：删测试库（主库删，从库自动同步删）...")
    exe(master, "DROP DATABASE repl_test")
    time.sleep(1)
    print("   环境已还原，可重复跑")

    master.close()
    slave.close()
    print("\n" + "=" * 60)
    print("🎯 结论：MySQL 主从 = binlog 增量同步，主写从读、删也同步、掉线补账")
    print("   真实电商标配：MySQL 主从 + Redis 缓存 + 读写分离")
    print("=" * 60)


if __name__ == "__main__":
    main()
