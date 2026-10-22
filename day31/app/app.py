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
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import Flask, jsonify, render_template, request
from werkzeug.security import check_password_hash, generate_password_hash
import pymysql
import redis

# ---------- 连接配置：容器内用服务名 + 3306 ----------
MASTER = dict(host=os.getenv("DB_MASTER_HOST", "127.0.0.1"),
              port=3306, user="root", password="root123",
              autocommit=True, charset="utf8mb4")
SLAVE = dict(host=os.getenv("DB_SLAVE_HOST", "127.0.0.1"),
             port=3306, user="root", password="root123",
             autocommit=True, charset="utf8mb4")
R = redis.Redis(host=os.getenv("REDIS_HOST", "127.0.0.1"),
                port=6379, decode_responses=True)

CONSUMERS = 3        # 消费者线程数
slave_ok = True      # 熔断开关：True=读从库，False=读主库
success_cnt = 0
lock = threading.Lock()

app = Flask(__name__)

# ---------- 用户系统：JWT ----------
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-in-prod")
JWT_EXPIRES = 24 * 3600          # token 有效期 24 小时


def make_token(uid, username):
    """签发 JWT：头部(算法) + 载荷(uid/名字/过期时间) + 签名(HMAC-SHA256)"""
    payload = {"uid": uid, "username": username,
               "exp": int(time.time()) + JWT_EXPIRES}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def require_auth(fn):
    """鉴权装饰器：从 Authorization: Bearer <token> 取用户，失败返回 401"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "请先登录（缺少 token）"}), 401
        try:
            payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "登录已过期，请重新登录"}), 401
        except Exception:
            return jsonify({"error": "token 无效，请重新登录"}), 401
        return fn(payload, *args, **kwargs)
    return wrapper


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
                R.delete("product:1")              # ④ 扣库存成功 → 删缓存（Cache Aside：先改DB再删缓存，否则页面看到旧库存）
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
@app.post("/api/register")
def register():
    """注册：username + password → 创建用户（密码哈希存储）"""
    body = request.json or {}
    name = (body.get("username") or "").strip()
    pwd = body.get("password") or ""
    if not (3 <= len(name) <= 32) or len(pwd) < 6:
        return jsonify({"error": "用户名 3-32 字符，密码至少 6 位"}), 400
    try:
        exe(mysql(MASTER),
            "INSERT INTO final_shop.users(username, password_hash) VALUES(%s, %s)",
            (name, generate_password_hash(pwd)))
    except pymysql.err.IntegrityError:
        return jsonify({"error": "用户名已被注册"}), 409
    row = fetch(mysql(MASTER), "SELECT id FROM final_shop.users WHERE username=%s", name)[0]
    return jsonify({"ok": True, "token": make_token(row["id"], name),
                    "msg": f"注册成功，欢迎 {name}"})


@app.post("/api/login")
def login():
    """登录：username + password → 校验密码 → 发 token"""
    body = request.json or {}
    name = (body.get("username") or "").strip()
    pwd = body.get("password") or ""
    rows = fetch(mysql(MASTER), "SELECT * FROM final_shop.users WHERE username=%s", name)
    if not rows or not check_password_hash(rows[0]["password_hash"], pwd):
        return jsonify({"error": "用户名或密码错误"}), 401
    return jsonify({"ok": True, "token": make_token(rows[0]["id"], name),
                    "msg": f"登录成功，欢迎 {name}"})


@app.get("/api/me")
@require_auth
def me(payload):
    """我的信息：token → 用户 + 我的订单"""
    uid = payload["uid"]
    orders = fetch(mysql(MASTER),
                   "SELECT product_id, amount, created_at FROM final_shop.orders "
                   "WHERE user_id=%s ORDER BY id DESC", uid)
    return jsonify({"username": payload["username"], "uid": uid, "orders": orders})


@app.get("/api/product/<int:pid>")
def get_product(pid):
    hit = R.get(f"product:{pid}")                  # ① 先问缓存
    if hit:
        # 坑：缓存里存的是 JSON 字符串，必须解析回对象，否则前端取字段全是 undefined
        return jsonify({"cache": "命中", "data": json.loads(hit)})
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
    """秒杀入口：前端带 token（页面用户），压测带 uid（内部通道）"""
    body = request.json or {}
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
            uid = payload["uid"]
        except Exception:
            return jsonify({"error": "token 无效，请重新登录"}), 401
    else:
        uid = body.get("uid")
    if not uid:
        return jsonify({"error": "需要登录后抢购（或压测传 uid）"}), 400
    # 幂等预检：一人一单（别等消费者才拦，前端要看得见结果）
    if R.sismember("seckill:bought", uid):
        return jsonify({"ok": False, "error": "一人一单，你已经抢过啦"}), 409
    R.lpush("seckill:queue", uid)                  # ③ 请求先进队列（0 阻塞）
    return jsonify({"ok": True, "msg": "已进入抢购队列，排队中…"})


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


# ---------- 页面（完整作品：打开浏览器就能用） ----------
@app.get("/")
def page_index():
    return render_template("index.html")


@app.get("/login")
def page_login():
    return render_template("login.html")


@app.get("/register")
def page_register():
    return render_template("register.html")


@app.get("/me")
def page_me():
    return render_template("me.html")


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
