# -*- coding: utf-8 -*-
"""Day 31：Docker 版终极商城 —— 一条命令 docker compose up 起全套

4 个容器：
  shop-mysql-master : MySQL 主库（开 binlog + GTID，建复制用户）
  shop-mysql-slave  : MySQL 从库（自动 CHANGE MASTER + START SLAVE）
  shop-redis        : Redis 缓存/队列/锁
  shop-app          : Flask 商城 API + 3 个消费者线程（削峰/幂等/锁/原子扣库存）

本机已有 MySQL 4306/4307 和 Memurai 6379，容器端口避开：
  对外映射 4308→容器3306(主)  4309→容器3306(从)  6380→容器6379(redis)
  容器之间用服务名互通：mysql-master:3306 / mysql-slave:3306 / redis:6379
"""
import json
import os
import threading
import time

from flask import Flask, jsonify, request
import pymysql
import redis

# ---------- 连接配置：容器内用服务名 + 3306 ----------
MASTER = dict(host=os.getenv("DB_MASTER_HOST", "127.0.0.1"),
              port=3306, user="root", password="root123", autocommit=True)
SLAVE = dict(host=os.getenv("DB_SLAVE_HOST", "127.0.0.1"),
             port=3306, user="root", password="root123", autocommit=True)
R = redis.Redis(host=os.getenv("REDIS_HOST", "127.0.0.1"),
                port=6379, decode_responses=True)

CONSUMERS = 3        # 消费者线程数
slave_ok = True      # 熔断开关：True=读从库，False=读主库
success_cnt = 0
lock = threading.Lock()

app = Flask(__name__)


def mysql(cfg):
    return pymysql.connect(**cfg)


def exe(conn, sql, args=None):
    cur = conn.cursor()
    cur.execute(sql, args)
    conn.commit()
    cur.close()


def fetch(conn, sql, args=None):
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return rows


def read_source():
    global slave_ok
    if slave_ok:
        return SLAVE, "从库"
    return MASTER, "主库(熔断)"


def read_row(pid):
    """读商品行：从库优先 + 自动熔断 + 半开恢复（一个函数管好读源）"""
    global slave_ok
    src = SLAVE if slave_ok else MASTER
    tag = "从库" if slave_ok else "主库(熔断)"
    try:
        if not slave_ok:
            # 半开探测：从库恢复了没？短超时(2s)试一次，通了才切回
            probe = pymysql.connect(connect_timeout=2, **SLAVE)
            probe.close()
            src, tag, slave_ok = SLAVE, "从库", True
        rows = fetch(mysql(src), "SELECT * FROM final_shop.products WHERE id=%s", pid)
        if src is SLAVE:
            slave_ok = True          # 从库读成功 → 保持/恢复
        return rows, tag
    except Exception:
        if src is MASTER:
            raise                    # 主库也挂了 → 真的挂了
        slave_ok = False             # 从库挂了 → 熔断
        rows = fetch(mysql(MASTER), "SELECT * FROM final_shop.products WHERE id=%s", pid)
        return rows, "主库(熔断)"


# ---------- 消费者：从队列取请求，真正处理下单（同 day28 逻辑） ----------
def consumer(worker_id):
    global success_cnt
    # 坑：容器启动瞬间 MySQL 可能没就绪，必须重试连接，否则线程一启动就死（daemon 线程异常无日志）
    while True:
        try:
            conn = mysql(MASTER)
            break
        except Exception:
            time.sleep(2)
    while True:
        try:
            item = R.brpop("seckill:queue", timeout=1)
            if not item:
                continue        # 队列空：继续等，不要 break（测试脚本重置后再抢还能处理）
            uid = int(item[1])
            if not R.sadd("seckill:bought", uid):      # ① 幂等：一人一单
                continue
            got = False
            for _ in range(20):                        # ② 分布式锁 SET NX EX
                if R.set("seckill:lock", "1", nx=True, ex=5):
                    got = True
                    break
                time.sleep(0.02)
            if not got:
                R.srem("seckill:bought", uid)
                continue
            try:
                rows = fetch(conn, "SELECT stock FROM final_shop.products WHERE id=1")
                if not rows or rows[0]["stock"] <= 0:
                    continue
                cur = conn.cursor()                    # ③ 原子扣库存：不超卖
                n = cur.execute("UPDATE final_shop.products SET stock=stock-1 "
                                "WHERE id=1 AND stock>0")
                conn.commit()
                cur.close()
                if n == 0:
                    continue
                exe(conn, "INSERT INTO final_shop.orders(user_id, product_id, amount) "
                          "VALUES(%s, 1, 2999.00)", (uid,))
                with lock:
                    success_cnt += 1
            finally:
                R.delete("seckill:lock")
        except Exception as e:
            time.sleep(1)      # 兜底：任何异常都别让线程死，睡 1 秒重来
    conn.close()


# ---------- API ----------
@app.get("/api/product/<int:pid>")
def get_product(pid):
    hit = R.get(f"product:{pid}")                  # ① 先问缓存
    if hit:
        return jsonify({"cache": "命中", "data": hit})
    try:
        rows, tag = read_row(pid)                  # ② 从库优先+熔断+半开恢复
    except Exception as e:
        return jsonify({"error": "db 不可用", "detail": str(e)}), 503
    if not rows:
        return jsonify({"error": "商品不存在"}), 404
    R.setex(f"product:{pid}", 60,
            json.dumps(rows[0], ensure_ascii=False, default=str))
    return jsonify({"cache": "未命中", "source": tag, "data": rows[0]})


@app.post("/api/seckill")
def seckill():
    uid = (request.json or {}).get("uid")
    if not uid:
        return jsonify({"error": "需要 uid"}), 400
    R.lpush("seckill:queue", uid)                  # ③ 请求先进队列（0 阻塞）
    return jsonify({"ok": True, "msg": f"uid={uid} 已进队列"})


@app.get("/api/stats")
def stats():
    try:
        rows, tag = read_row(1)                    # 读源统一走 read_row（熔断+半开）
        stock = rows[0]["stock"]
        orders = fetch(mysql(MASTER), "SELECT COUNT(*) c FROM final_shop.orders")[0]["c"]
        return jsonify({
            "stock": stock, "orders": orders,
            "queue": R.llen("seckill:queue"), "bought": R.scard("seckill:bought"),
            "read_source": tag,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.post("/api/admin/reset")
def reset():
    """实验重置：清空订单 + 库存回 5（跑多轮压测用）"""
    exe(mysql(MASTER), "TRUNCATE TABLE final_shop.orders")
    exe(mysql(MASTER), "UPDATE final_shop.products SET stock=5 WHERE id=1")
    R.delete("seckill:queue", "seckill:bought", "seckill:lock", "product:1")
    return jsonify({"ok": True, "msg": "已重置：订单清空，库存=5，队列清空"})


if __name__ == "__main__":
    # 等 MySQL 就绪（compose depends_on 已挡一道，这里兜底）
    for i in range(30):
        try:
            mysql(MASTER).close()
            break
        except Exception:
            time.sleep(2)
    for i in range(CONSUMERS):
        threading.Thread(target=consumer, args=(i,), daemon=True).start()
    app.run(host="0.0.0.0", port=5001)
