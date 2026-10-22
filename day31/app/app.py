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
ORDER_TTL = int(os.getenv("ORDER_TTL", "600"))   # 订单支付时限（秒）：超时自动取消
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
        # 坑：熔断中(src=MASTER)再读，src 是 MASTER，直接 raise 会把"从库探测失败"
        # 误判成"主库也挂了"→ 返回 503。正确做法：熔断中照样读主库。
        try:
            rows = fetch(mysql(MASTER), "SELECT * FROM final_shop.products WHERE id=%s", pid)
            slave_ok = False         # 从库没恢复 → 保持熔断
            return rows, "主库(熔断)"
        except Exception:
            raise                    # 主库也挂了 → 真的挂了


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
                exe(conn, "INSERT INTO final_shop.orders(user_id, product_id, amount, status) "
                          "VALUES(%s, 1, 2999.00, 'pending')", (uid,))
                oid = fetch(conn, "SELECT LAST_INSERT_ID() AS id")[0]["id"]
                R.zadd("order:delay", {oid: time.time() + ORDER_TTL})   # ⑤ 延迟队列：超时未支付自动取消
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
    """我的信息：token → 用户 + 我的订单（JOIN 出商品名）"""
    uid = payload["uid"]
    orders = fetch(mysql(MASTER),
                   "SELECT o.id, o.product_id, p.name, o.amount, o.status, o.created_at "
                   "FROM final_shop.orders o "
                   "LEFT JOIN final_shop.products p ON o.product_id=p.id "
                   "WHERE o.user_id=%s ORDER BY o.id DESC", uid)
    return jsonify({"username": payload["username"], "uid": uid, "orders": orders})


@app.get("/api/product/<int:pid>")
def get_product(pid):
    hit = R.get(f"product:{pid}")                  # ① 先问缓存
    if hit:
        if hit == "EMPTY":
            # 穿透防护：空值缓存命中，直接挡掉，不再打 DB
            return jsonify({"cache": "命中(空值缓存)", "error": "商品不存在"}), 404
        # 坑：缓存里存的是 JSON 字符串，必须解析回对象，否则前端取字段全是 undefined
        return jsonify({"cache": "命中", "data": json.loads(hit)})

    # ② 击穿防护：缓存失效瞬间只放 1 个请求回源（SET NX EX 互斥锁），
    #    其余请求等 50ms 后重读缓存，避免同一时刻 N 个请求一起打 DB
    if not R.set(f"lock:product:{pid}", "1", nx=True, ex=5):
        time.sleep(0.05)
        hit = R.get(f"product:{pid}")
        if hit:
            if hit == "EMPTY":
                return jsonify({"cache": "等待后命中(空值缓存)", "error": "商品不存在"}), 404
            return jsonify({"cache": "等待后命中", "data": json.loads(hit)})
        # 极端：锁还没释放（DB 慢），直接读库兜底
        try:
            rows, tag = read_row(pid)
        except Exception as e:
            return jsonify({"error": "db 不可用", "detail": str(e)}), 503
        if not rows:
            return jsonify({"cache": "未命中", "source": tag, "error": "商品不存在"}), 404
        return jsonify({"cache": "未命中", "source": tag, "data": rows[0]})

    try:
        rows, tag = read_row(pid)                  # ③ 拿到锁：从库优先+熔断+半开恢复
    except Exception as e:
        R.delete(f"lock:product:{pid}")
        return jsonify({"error": "db 不可用", "detail": str(e)}), 503
    R.delete(f"lock:product:{pid}")
    if not rows:
        # 穿透防护：商品不存在也缓存 30s（空值），防恶意请求反复打 DB
        R.setex(f"product:{pid}", 30, "EMPTY")
        return jsonify({"cache": "未命中(已写空值缓存)", "source": tag, "error": "商品不存在"}), 404
    R.setex(f"product:{pid}", 60,
            json.dumps(rows[0], ensure_ascii=False, default=str))
    return jsonify({"cache": "未命中", "source": tag, "data": rows[0]})


def read_all():
    """读全表商品：和 read_row 同款 从库优先+熔断+半开恢复"""
    global slave_ok
    src = SLAVE if slave_ok else MASTER
    tag = "从库" if slave_ok else "主库(熔断)"
    try:
        if not slave_ok:
            probe = pymysql.connect(connect_timeout=2, **SLAVE)
            probe.close()
            src, tag, slave_ok = SLAVE, "从库", True
        rows = fetch(mysql(src), "SELECT * FROM final_shop.products ORDER BY id")
        if src is SLAVE:
            slave_ok = True
        return rows, tag
    except Exception:
        # 同 read_row 的坑：熔断中探测失败 ≠ 主库挂了，继续读主库
        try:
            rows = fetch(mysql(MASTER), "SELECT * FROM final_shop.products ORDER BY id")
            slave_ok = False
            return rows, "主库(熔断)"
        except Exception:
            raise


@app.get("/api/products")
def list_products():
    """商品列表（首页用）：整表缓存 30 秒 + 从库读取 + 击穿互斥锁"""
    hit = R.get("products:list")
    if hit:
        return jsonify({"cache": "命中", "data": json.loads(hit)})
    # 击穿防护：缓存失效瞬间只放 1 个请求回源
    if not R.set("lock:products:list", "1", nx=True, ex=5):
        time.sleep(0.05)
        hit = R.get("products:list")
        if hit:
            return jsonify({"cache": "等待后命中", "data": json.loads(hit)})
    try:
        rows, tag = read_all()
    except Exception as e:
        R.delete("lock:products:list")
        return jsonify({"error": "db 不可用", "detail": str(e)}), 503
    R.delete("lock:products:list")
    R.setex("products:list", 30, json.dumps(rows, ensure_ascii=False, default=str))
    return jsonify({"cache": "未命中", "source": tag, "data": rows})


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
    """实验重置：清空订单 + 3 个商品库存回满 + 清队列/缓存（跑多轮压测/演示用）"""
    exe(mysql(MASTER), "TRUNCATE TABLE final_shop.orders")
    exe(mysql(MASTER), "UPDATE final_shop.products SET stock=5   WHERE id=1")
    exe(mysql(MASTER), "UPDATE final_shop.products SET stock=50  WHERE id=2")
    exe(mysql(MASTER), "UPDATE final_shop.products SET stock=200 WHERE id=3")
    R.delete("seckill:queue", "seckill:bought", "seckill:lock",
             "product:1", "product:2", "product:3", "products:list")
    return jsonify({"ok": True, "msg": "已重置：订单清空，库存回满(5/50/200)，队列与缓存清空"})


# ---------- 购物车（Redis Hash：cart:{uid} → field=商品id, value=数量） ----------
@app.post("/api/cart/add")
@require_auth
def cart_add(payload):
    """加入购物车：body {product_id}，数量累加"""
    uid = payload["uid"]
    pid = (request.json or {}).get("product_id")
    if not pid:
        return jsonify({"error": "需要 product_id"}), 400
    rows = fetch(mysql(MASTER), "SELECT stock FROM final_shop.products WHERE id=%s", pid)
    if not rows:
        return jsonify({"error": "商品不存在"}), 404
    R.hincrby(f"cart:{uid}", pid, 1)
    return jsonify({"ok": True, "msg": f"已加入购物车（商品 #{pid}）"})


@app.get("/api/cart")
@require_auth
def cart_list(payload):
    """我的购物车：Redis 数量 + JOIN 商品价格，返回小计和总价"""
    uid = payload["uid"]
    items = R.hgetall(f"cart:{uid}")          # {商品id: 数量}
    if not items:
        return jsonify({"items": [], "total": "0.00", "msg": "购物车是空的"})
    rows = fetch(mysql(MASTER), "SELECT id, name, price FROM final_shop.products "
                                "WHERE id IN (%s)" % ",".join(["%s"] * len(items)),
                 tuple(int(k) for k in items.keys()))
    out, total = [], 0
    for r in rows:
        qty = int(items[str(r["id"])])
        sub = float(r["price"]) * qty
        total += sub
        out.append({"id": r["id"], "name": r["name"], "price": r["price"],
                    "qty": qty, "subtotal": f"{sub:.2f}"})
    return jsonify({"items": out, "total": f"{total:.2f}"})


@app.post("/api/cart/update")
@require_auth
def cart_update(payload):
    """增减数量：body {product_id, delta}，delta=+1/-1，减到 0 自动移除"""
    uid = payload["uid"]
    body = request.json or {}
    pid, delta = body.get("product_id"), int(body.get("delta", 0))
    if not pid or delta == 0:
        return jsonify({"error": "需要 product_id 和 delta(±1)"}), 400
    key = f"cart:{uid}"
    new = int(R.hget(key, pid) or 0) + delta
    if new <= 0:
        R.hdel(key, pid)
        return jsonify({"ok": True, "msg": "数量减到 0，已从购物车移除"})
    R.hset(key, pid, new)
    return jsonify({"ok": True, "msg": f"数量 → {new}"})


@app.post("/api/cart/remove")
@require_auth
def cart_remove(payload):
    """删除购物车中的商品：body {product_id}"""
    uid = payload["uid"]
    pid = (request.json or {}).get("product_id")
    R.hdel(f"cart:{uid}", pid)
    return jsonify({"ok": True, "msg": "已从购物车删除"})


@app.post("/api/cart/checkout")
@require_auth
def cart_checkout(payload):
    """结算：事务逐件扣库存(stock>0原子) + 生成订单，失败全回滚，清空购物车"""
    uid = payload["uid"]
    items = R.hgetall(f"cart:{uid}")
    if not items:
        return jsonify({"error": "购物车是空的"}), 400
    conn = mysql(MASTER)
    try:
        cur = conn.cursor()
        total = 0
        for pid, qty in items.items():
            pid, qty = int(pid), int(qty)
            for _ in range(qty):
                cur.execute("UPDATE final_shop.products SET stock=stock-1 "
                            "WHERE id=%s AND stock>0", pid)
                if cur.rowcount == 0:
                    raise Exception(f"商品 #{pid} 库存不足")
                price = fetch(conn, "SELECT price FROM final_shop.products WHERE id=%s", pid)[0]["price"]
                cur.execute("INSERT INTO final_shop.orders(user_id, product_id, amount, status) "
                            "VALUES(%s, %s, %s, 'pending')", (uid, pid, price))
                # 坑：扣了库存必须删缓存，否则页面/首页列表显示旧库存（用户实测踩过）
                R.delete(f"product:{pid}")
                R.delete("products:list")
                total += float(price)
        conn.commit()
        # 延迟队列：每笔订单超时未支付自动取消（ZSET score=过期时间戳）
        for pid, qty in items.items():
            rows = fetch(conn, "SELECT id FROM final_shop.orders "
                               "WHERE user_id=%s AND product_id=%s AND status='pending' "
                               "ORDER BY id DESC LIMIT 1", (uid, int(pid)))
            if rows:
                R.zadd("order:delay", {rows[0]["id"]: time.time() + ORDER_TTL})
        cur.close()
        R.delete(f"cart:{uid}")
        return jsonify({"ok": True, "msg": f"结算成功，共 {len(items)} 种商品，合计 ¥{total:.2f}",
                        "total": f"{total:.2f}"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": "结算失败：" + str(e)}), 409


@app.post("/api/order/pay")
@require_auth
def order_pay(payload):
    """模拟支付：订单 pending → paid（并移出延迟队列，不再被自动取消）"""
    uid = payload["uid"]
    oid = (request.json or {}).get("order_id")
    if not oid:
        return jsonify({"error": "需要 order_id"}), 400
    conn = mysql(MASTER)
    cur = conn.cursor()
    n = cur.execute("UPDATE final_shop.orders SET status='paid' "
                    "WHERE id=%s AND user_id=%s AND status='pending'", (oid, uid))
    conn.commit()
    cur.close()
    if n == 0:
        return jsonify({"error": "订单不存在或不是待支付状态"}), 409
    R.zrem("order:delay", oid)
    return jsonify({"ok": True, "msg": f"支付成功，订单 #{oid} 已成交"})


def order_watcher():
    """订单超时自动取消：ZSET 延迟队列，每 2 秒扫到期订单 → 取消 + 库存回补"""
    while True:
        try:
            now = time.time()
            expired = R.zrangebyscore("order:delay", 0, now, start=0, num=50)
            for oid in expired:
                rows = fetch(mysql(MASTER), "SELECT status, product_id FROM final_shop.orders "
                                            "WHERE id=%s", int(oid))
                if not rows:
                    R.zrem("order:delay", oid)
                    continue
                if rows[0]["status"] != "pending":
                    R.zrem("order:delay", oid)     # 已支付/已取消：从队列摘掉
                    continue
                exe(mysql(MASTER), "UPDATE final_shop.orders SET status='cancelled' WHERE id=%s", int(oid))
                # 库存回补：超时未支付 → 把扣掉的库存加回来 + 删缓存
                exe(mysql(MASTER), "UPDATE final_shop.products SET stock=stock+1 "
                                   "WHERE id=%s", rows[0]["product_id"])
                R.delete(f"product:{rows[0]['product_id']}")
                R.delete("products:list")
                R.zrem("order:delay", oid)
        except Exception:
            time.sleep(1)      # 任何异常都别让线程死
        time.sleep(2)


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


@app.get("/cart")
def page_cart():
    return render_template("cart.html")


@app.get("/admin")
def page_admin():
    return render_template("admin.html")


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
    threading.Thread(target=order_watcher, daemon=True).start()   # 订单超时自动取消
    app.run(host="0.0.0.0", port=5001)
