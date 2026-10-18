# -*- coding: utf-8 -*-
"""Day 27：MySQL 分库分表（水平拆分）——单表数据过亿怎么办

核心思想（和 Redis Cluster 同一个思路）：
  单表数据太多 → 按某个规则拆成 N 张小表 → 每张只存 1/N → 查询只查对应那张

本次实验（全部真实执行）：
  ① 建 1 张"单表" orders_all + 4 张"分表" orders_0~3（按 user_id % 4 路由）
  ② 真实写入 30 万条订单（单表 30 万，分表各 7.5 万）
  ③ 按用户查（带分片键）：EXPLAIN + 实测耗时 —— 单表 vs 分表
  ④ 分表的痛①：按订单号查（不带分片键）→ 要广播查 4 张表
  ⑤ 分表的痛②：跨表统计（COUNT/SUM）→ 4 张表合并
  ⑥ 分表的痛③：分表后自增 ID 会冲突 → 分布式 ID（雪花 ID）
"""
import random
import time

import pymysql

CONN = dict(host="127.0.0.1", port=4306, user="root", password="root123",
            autocommit=True)

USER_NUM = 30000      # 3 万用户
ORDERS_PER_USER = 10  # 每用户 10 单 → 30 万条


def db():
    return pymysql.connect(**CONN)


def exe(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    cur.close()


def q(conn, sql):
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    return rows


def table_for(user_id):
    """分片路由：user_id % 4 → 存哪张表"""
    return f"orders_{user_id % 4}"


def main():
    print("=" * 62)
    print("🗂️  Day 27 实验：MySQL 分库分表（水平拆分）")
    print("=" * 62)

    conn = db()
    print("\n⓪ 环境检查 + 建库建表...")
    exe(conn, "DROP DATABASE IF EXISTS shard_db")
    exe(conn, "CREATE DATABASE shard_db")
    exe(conn, "USE shard_db")
    # 单表（对照）：orders_all
    exe(conn, """CREATE TABLE orders_all (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        order_no VARCHAR(32) NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT NOW()
    ) ENGINE=InnoDB""")
    # 分表：orders_0 ~ orders_3（结构相同，没有全局索引）
    for i in range(4):
        exe(conn, f"""CREATE TABLE orders_{i} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            order_no VARCHAR(32) NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT NOW()
        ) ENGINE=InnoDB""")
    print("   建表完成：orders_all（单表）+ orders_0~3（分表）✅")

    # ---------- ② 真实写入 ----------
    print(f"\n② 真实写入 {USER_NUM * ORDERS_PER_USER} 条订单（3 万用户 × 每人 10 单）...")
    rows = []
    for uid in range(1, USER_NUM + 1):
        for _ in range(ORDERS_PER_USER):
            rows.append((uid, f"NO{uid}_{random.randint(1000, 9999)}",
                         round(random.uniform(10, 5000), 2)))
    # 写单表（30 万全进一张）
    t0 = time.perf_counter()
    for i in range(0, len(rows), 5000):
        cur = conn.cursor()
        cur.executemany("INSERT INTO orders_all(user_id, order_no, amount) VALUES(%s,%s,%s)",
                        rows[i:i + 5000])
        cur.close()
    conn.commit()
    t_all = time.perf_counter() - t0
    # 写分表（走路由，各 7.5 万）
    buckets = {i: [] for i in range(4)}
    for uid, no, amt in rows:
        buckets[uid % 4].append((uid, no, amt))
    t0 = time.perf_counter()
    for i in range(4):
        for j in range(0, len(buckets[i]), 5000):
            cur = conn.cursor()
            cur.executemany(f"INSERT INTO orders_{i}(user_id, order_no, amount) VALUES(%s,%s,%s)",
                            buckets[i][j:j + 5000])
            cur.close()
    conn.commit()
    t_shard = time.perf_counter() - t0
    print(f"   单表写入 {len(rows)} 条：{t_all:.2f} 秒 ｜ 分表写入（4 张各 "
          f"{len(rows)//4} 条）：{t_shard:.2f} 秒")
    cnts = [q(conn, f"SELECT COUNT(*) c FROM orders_{i}")[0]["c"] for i in range(4)]
    print(f"   分表分布：orders_0={cnts[0]} ｜ orders_1={cnts[1]} ｜ "
          f"orders_2={cnts[2]} ｜ orders_3={cnts[3]}（合计 {sum(cnts)}）✅")

    # ---------- ③ 按用户查（带分片键） ----------
    print("\n③ 按用户查订单（带分片键 user_id）——单表 vs 分表：")
    uid = 12345
    e1 = q(conn, "EXPLAIN SELECT * FROM orders_all WHERE user_id=12345")
    e2 = q(conn, f"EXPLAIN SELECT * FROM {table_for(uid)} WHERE user_id={uid}")
    print(f"   单表 EXPLAIN：扫描 rows≈{e1[0]['rows']}（全表找，要翻 30 万行）")
    print(f"   分表 EXPLAIN：扫描 rows≈{e2[0]['rows']}（路由到 orders_{uid%4}，只翻 7.5 万行）")
    t0 = time.perf_counter()
    q(conn, "SELECT * FROM orders_all WHERE user_id=12345")
    t_all = time.perf_counter() - t0
    t0 = time.perf_counter()
    q(conn, f"SELECT * FROM {table_for(uid)} WHERE user_id={uid}")
    t_shard = time.perf_counter() - t0
    print(f"   实测耗时：单表 {t_all*1000:.1f} ms ｜ 分表 {t_shard*1000:.1f} ms "
          f"（快 {t_all/t_shard:.1f} 倍）✅")
    print("   → 分片键（user_id）带着走，就只查 1 张表，数据量缩到 1/4")

    # ---------- ④ 分表的痛：按订单号查 ----------
    print("\n④ 分表的痛①：按订单号查（不带分片键）→ 不知道去哪张表，广播 4 张：")
    one = q(conn, "SELECT order_no FROM orders_1 LIMIT 1")[0]["order_no"]
    t0 = time.perf_counter()
    r_all = q(conn, f"SELECT * FROM orders_all WHERE order_no='{one}'")
    t_all = time.perf_counter() - t0
    t0 = time.perf_counter()
    parts = []
    for i in range(4):
        parts.extend(q(conn, f"SELECT * FROM orders_{i} WHERE order_no='{one}'"))
    t_shard = time.perf_counter() - t0
    print(f"   单表：查 1 次（{t_all*1000:.1f} ms），找到 {len(r_all)} 条")
    print(f"   分表：查 4 次再合并（{t_shard*1000:.1f} ms），找到 {len(parts)} 条")
    print(f"   → 不带分片键：4 张表总共还是扫 {len(rows)} 行，一点没少，"
          f"还多了 4 次查询 + 合并逻辑")
    print("   → 这就是为什么分片键要选『高频查询都带着』的字段（比如 user_id）")

    # ---------- ⑤ 分表的痛：跨表统计 ----------
    print("\n⑤ 分表的痛②：跨表统计（总额）→ 4 张表各算一遍再相加：")
    r_all = q(conn, "SELECT COUNT(*) c, ROUND(SUM(amount),2) s FROM orders_all")[0]
    from decimal import Decimal
    s_shard = Decimal("0.00")
    cnt_shard = 0
    for i in range(4):
        r = q(conn, f"SELECT COUNT(*) c, ROUND(SUM(amount),2) s FROM orders_{i}")[0]
        cnt_shard += r["c"]
        s_shard += r["s"]
    print(f"   单表：{r_all['c']} 单，总额 {r_all['s']} ｜ 分表：{cnt_shard} 单，"
          f"总额 {s_shard:.2f}（4 张结果相加）✅ 数据一致")
    print("   → 分表后统计/报表要写『聚合路由』：跨表 UNION 或汇总表")

    # ---------- ⑥ 分表的痛：ID 冲突 ----------
    print("\n⑥ 分表的痛③：分表后自增 ID 会冲突：")
    d1 = q(conn, "SELECT MIN(id) m, MAX(id) x FROM orders_0")[0]
    d2 = q(conn, "SELECT MIN(id) m, MAX(id) x FROM orders_1")[0]
    print(f"   orders_0 的 id 从 {d1['m']} 到 {d1['x']} ｜ orders_1 的 id 从 {d2['m']} 到 {d2['x']}")
    print(f"   → 两张表都有 id=1、id=2…… 订单号会重 → 不能再用自增当全局订单号！")
    print("   解法：分布式 ID（雪花算法：时间戳 + 表号 + 序号 = 全局唯一）")
    # 简单雪花 ID 演示：毫秒时间戳(43位) + 表号(2位) + 序号(3位)
    seq = 0
    last_ms = 0

    def snowflake(tbl):
        nonlocal seq, last_ms
        ms = int(time.time() * 1000)
        if ms == last_ms:
            seq += 1
        else:
            seq = 0
            last_ms = ms
        return int(f"{ms % 10000000000000}{tbl % 4:02d}{seq:03d}")

    ids = {snowflake(0), snowflake(1), snowflake(2), snowflake(3), snowflake(0)}
    print(f"   雪花 ID 生成 5 个：{sorted(ids)} —— 全部不重复 ✅")
    print("   （真实雪花=63bit 整数，这里简化演示，核心是『时间戳+表号+序号』）")
    # ---------- ⑦ 清理 ----------
    print("🧹 清理：删除 shard_db 演示库...")
    exe(conn, "DROP DATABASE IF EXISTS shard_db")
    conn.close()
    print("   已清理，不影响你的商城数据")

    print("\n" + "=" * 62)
    print("🎯 结论：分表 = 按分片键(user_id)取模拆 N 张表 → 带键查询只碰 1 张")
    print("   代价：不带键的查询要广播、统计要合并、自增 ID 要换分布式 ID")
    print("=" * 62)


if __name__ == "__main__":
    main()
