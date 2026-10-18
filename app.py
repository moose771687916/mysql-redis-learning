# -*- coding: utf-8 -*-
"""
电商 API 接口（Day 8：Flask 入门）
====================================
后端程序 = 一直开着的"餐厅前台"：
  浏览器访问 http://localhost:5000/products
  → 程序（代码）按"菜单"（URL）给"菜"（数据）

运行：python app.py
然后浏览器打开 http://localhost:5000/products 就能看到商品列表

知识点：
  @app.route("/products")  = 菜单牌：有人访问 /products 就执行下面这个函数
  jsonify(...)             = 把 Python 数据变成 JSON 格式返回给浏览器
"""

from flask import Flask, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import redis
import json
import os
import time
import threading

app = Flask(__name__)

# 项目根目录（无论从哪个目录启动都能找到 static 文件夹）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 秒杀队列（Day 18/19：Redis List 削峰）
SECKILL_QUEUE = "seckill:queue"


def get_mysql():
    return pymysql.connect(
        host="127.0.0.1", port=4306, user="root", password="root123",
        database="my_first_db", charset="utf8mb4"
    )


def get_redis():
    return redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)


# ---------- 接口 1：商城首页（返回网页） ----------
@app.route("/")
def home():
    """首页：把 shop.html 网页端给浏览器"""
    with open(os.path.join(BASE_DIR, "static", "shop.html"), encoding="utf-8") as f:
        return f.read()


# ---------- 接口 2：商品列表（MySQL + Redis 缓存） ----------
@app.route("/products")
def products():
    """商品列表接口：先问缓存，没有再查数据库并写回缓存"""
    r = get_redis()

    # ① 先问 Redis
    cached = r.get("product:list")
    if cached is not None:
        print("⚡ 命中缓存（没碰数据库）")
        return jsonify(json.loads(cached))

    # ② 没有 → 查 MySQL
    conn = get_mysql()
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, stock FROM product")
    rows = cur.fetchall()
    conn.close()

    data = [{"id": r[0], "name": r[1], "price": float(r[2]), "stock": r[3]} for r in rows]

    # ③ 写回 Redis（30 秒过期；列表为空也缓存，防空表穿透）
    r.set("product:list", json.dumps(data, ensure_ascii=False), ex=30)
    print("🐢 查了 MySQL，已写入缓存")

    return jsonify(data)


# ---------- 接口：商品详情（Day 16 升级：布隆过滤 + 缓存空值 + 互斥锁） ----------
# 布隆过滤器名单：真实存在的商品 id（教学用 set 模拟；真实项目用 Redis 布隆结构）
PRODUCT_BLOOM = {1, 2, 3}


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    """商品详情接口：
    ① 布隆过滤     → 不存在的 id 直接 404（0 次 MySQL）防穿透
    ② 缓存空值     → 查不到的也缓存 30 秒，防穿透
    ③ SET NX 互斥锁 → 缓存 miss 瞬间只让 1 个请求查库，防击穿
    """
    # ① 布隆过滤：不在名单的假 id 直接挡（根本不碰缓存和 MySQL）
    if product_id not in PRODUCT_BLOOM:
        print(f"🛡️ 布隆拦截：id={product_id} 不在名单，直接 404")
        return jsonify({"error": "商品不存在"}), 404

    r = get_redis()
    cache_key = f"product:{product_id}"

    # ② 查缓存（可能是空值：查不到的也缓存了 30 秒）
    cached = r.get(cache_key)
    if cached is not None:
        if cached:
            return jsonify(json.loads(cached))          # 有值 → 直接返回
        return jsonify({"error": "商品不存在"}), 404    # 空值缓存 → 还是不存在

    # ③ 缓存 miss → 抢"重建缓存"的锁（防击穿：只让 1 个请求进 MySQL）
    lock_key = f"lock:product:{product_id}"
    got_lock = r.set(lock_key, "rebuilding", nx=True, ex=5)
    if not got_lock:
        # 有人正在查库重建，等 50 毫秒再看缓存（别人马上写好了）
        time.sleep(0.05)
        cached = r.get(cache_key)
        if cached:
            return jsonify(json.loads(cached))
        return jsonify({"error": "商品不存在"}), 404

    # ④ 抢到锁的人查 MySQL（只有这一个请求打库）
    try:
        conn = get_mysql()
        cur = conn.cursor()
        cur.execute("SELECT id, name, price, stock FROM product WHERE id = %s", (product_id,))
        row = cur.fetchone()
        conn.close()

        if row:
            data = {"id": row[0], "name": row[1], "price": float(row[2]), "stock": row[3]}
            r.set(cache_key, json.dumps(data, ensure_ascii=False), ex=30)
            print(f"🐢 查了 MySQL（{product_id}），已写缓存")
            return jsonify(data)
        else:
            # ⑤ 查不到 → 空值也缓存 30 秒（防穿透：下次直接命中空缓存）
            r.set(cache_key, "", ex=30)
            print(f"🛡️ 缓存空值：{product_id} 不存在，已记住 30 秒")
            return jsonify({"error": "商品不存在"}), 404
    finally:
        r.delete(lock_key)   # 释放重建锁


# ---------- 接口 3：注册用户（POST = 向服务器"提交数据"） ----------
@app.route("/register", methods=["POST"])
def register():
    """注册接口：接收 用户名+密码，写入 users 表"""
    data = request.get_json()              # 拿 POST 过来的 JSON 数据
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    conn = get_mysql()
    cur = conn.cursor()
    try:
        # 参数化插入，重名会被 UNIQUE 约束拦下
        # 密码绝不存明文！生成一个"加密后的密码"再存（真实系统的底线）
        hashed = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hashed)
        )
        conn.commit()
        return jsonify({"success": True, "user_id": cur.lastrowid,
                        "message": f"用户 {username} 注册成功（密码已加密存储）"})
    except pymysql.err.IntegrityError:
        conn.rollback()
        return jsonify({"error": "用户名已存在"}), 409
    finally:
        conn.close()


# ---------- 接口：登录 ----------
@app.route("/login", methods=["POST"])
def login():
    """登录接口：校验密码，成功返回 user_id"""
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    conn = get_mysql()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, password FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "用户名不存在"}), 404
        user_id, stored = row

        # 正常校验：比对加密后的密码
        if check_password_hash(stored, password):
            return jsonify({"success": True, "user_id": user_id,
                            "message": f"欢迎回来，{username}！"})

        # 兼容教学期存的明文密码，登录成功顺手升级成加密存储（真实项目叫"密码迁移"）
        if stored == password:
            cur.execute("UPDATE users SET password = %s WHERE id = %s",
                        (generate_password_hash(password), user_id))
            conn.commit()
            return jsonify({"success": True, "user_id": user_id,
                            "message": f"欢迎回来，{username}！（密码已自动升级为加密存储）"})

        return jsonify({"error": "密码错误"}), 401
    finally:
        conn.close()


# ---------- 接口：加购物车 ----------
@app.route("/cart/add", methods=["POST"])
def cart_add():
    """加购：已存在的商品数量累加，同时检查库存"""
    data = request.get_json()
    user_id = data.get("user_id")
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)

    conn = get_mysql()
    cur = conn.cursor()
    try:
        cur.execute("SELECT stock FROM product WHERE id = %s", (product_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "商品不存在"}), 404
        stock = row[0]

        cur.execute("SELECT id, quantity FROM cart WHERE user_id = %s AND product_id = %s",
                    (user_id, product_id))
        exists = cur.fetchone()
        if exists:
            new_qty = exists[1] + quantity
            if new_qty > stock:
                return jsonify({"error": f"加购后数量 {new_qty} 超过库存 {stock}"}), 400
            cur.execute("UPDATE cart SET quantity = %s WHERE id = %s", (new_qty, exists[0]))
        else:
            if quantity > stock:
                return jsonify({"error": f"库存不足，只剩 {stock} 件"}), 400
            cur.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (%s, %s, %s)",
                        (user_id, product_id, quantity))
        conn.commit()
        return jsonify({"success": True, "message": "已加入购物车"})
    finally:
        conn.close()


# ---------- 接口：查看购物车 ----------
@app.route("/cart")
def cart_list():
    """查看某用户的购物车（JOIN 商品，算小计和合计）"""
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400

    conn = get_mysql()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT c.id, p.name, p.price, c.quantity, p.price * c.quantity AS subtotal
            FROM cart c JOIN product p ON c.product_id = p.id
            WHERE c.user_id = %s ORDER BY c.id
        """, (user_id,))
        rows = cur.fetchall()
        items = [{"cart_id": r[0], "name": r[1], "price": float(r[2]),
                  "quantity": r[3], "subtotal": float(r[4])} for r in rows]
        total = sum(i["subtotal"] for i in items)
        return jsonify({"items": items, "total": total})
    finally:
        conn.close()


# ---------- 接口：删除购物车的一项 ----------
@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    data = request.get_json()
    cart_id = data.get("cart_id")
    conn = get_mysql()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM cart WHERE id = %s", (cart_id,))
        conn.commit()
        return jsonify({"success": True, "message": "已删除"})
    finally:
        conn.close()


# ---------- 接口：结算购物车（事务：校验库存→写订单→写明细→扣库存→清空购物车） ----------
@app.route("/checkout", methods=["POST"])
def checkout():
    """整单结算：把购物车里所有商品一次性下单"""
    data = request.get_json()
    user_id = data.get("user_id")

    conn = get_mysql()
    cur = conn.cursor()
    try:
        # ① 查购物车全部商品（带价格）
        cur.execute("""
            SELECT c.product_id, p.price, p.stock, c.quantity
            FROM cart c JOIN product p ON c.product_id = p.id
            WHERE c.user_id = %s
        """, (user_id,))
        cart_rows = cur.fetchall()
        if not cart_rows:
            return jsonify({"error": "购物车是空的"}), 400

        # ② 校验每件库存，不足 → 整单回滚
        for product_id, price, stock, qty in cart_rows:
            if qty > stock:
                conn.rollback()
                return jsonify({"error": f"商品 {product_id} 库存不足（要 {qty}，只剩 {stock}）"}), 400

        # ③ 写订单（总额 = 所有商品合计）
        total = sum(price * qty for _, price, _, qty in cart_rows)
        cur.execute("INSERT INTO orders (user_id, total) VALUES (%s, %s)", (user_id, total))
        order_id = cur.lastrowid

        # ④ 写每件商品为订单明细（价格快照）
        for product_id, price, _, qty in cart_rows:
            cur.execute(
                "INSERT INTO order_item (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                (order_id, product_id, qty, price)
            )
            # ⑤ 扣库存（原子防超卖：WHERE stock >= 数量；0 行 = 手慢了 → 整单回滚）
            n = cur.execute(
                "UPDATE product SET stock = stock - %s WHERE id = %s AND stock >= %s",
                (qty, product_id, qty))
            if n == 0:
                conn.rollback()
                return jsonify({"error": f"商品 {product_id} 手慢了，库存不足"}), 400

        # ⑥ 清空购物车
        cur.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))

        conn.commit()
        get_redis().delete("product:list")   # 库存变了，缓存失效
        return jsonify({"success": True, "order_id": order_id, "total": total})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
@app.route("/myorders")
def my_orders():
    """按 user_id 查该用户的订单 + 明细（JOIN 商品名）"""
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400

    conn = get_mysql()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, total, created_at FROM orders WHERE user_id = %s ORDER BY id DESC", (user_id,))
        orders = cur.fetchall()
        result = []
        for o in orders:
            cur.execute("""
                SELECT p.name, oi.quantity, oi.price
                FROM order_item oi JOIN product p ON oi.product_id = p.id
                WHERE oi.order_id = %s
            """, (o[0],))
            items = cur.fetchall()
            result.append({
                "order_id": o[0],
                "total": float(o[1]),
                "created_at": str(o[2]),
                "items": [{"name": i[0], "quantity": i[1], "price": float(i[2])} for i in items]
            })
        return jsonify(result)
    finally:
        conn.close()


# ---------- 接口 4：下单（POST + 事务） ----------
@app.route("/order", methods=["POST"])
def order():
    """下单接口：接收 用户ID + 商品ID + 数量，事务下单"""
    data = request.get_json()
    user_id = data.get("user_id")
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)

    conn = get_mysql()
    cur = conn.cursor()
    try:
        # ① 查商品价格和库存
        cur.execute("SELECT price, stock FROM product WHERE id = %s", (product_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "商品不存在"}), 404
        price, stock = row
        if stock < quantity:
            return jsonify({"error": f"库存不足，只剩 {stock} 件"}), 400

        # ② 写订单
        total = price * quantity
        cur.execute("INSERT INTO orders (user_id, total) VALUES (%s, %s)", (user_id, total))
        order_id = cur.lastrowid

        # ③ 写明细（价格快照）
        cur.execute(
            "INSERT INTO order_item (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
            (order_id, product_id, quantity, price)
        )

        # ④ 扣库存（原子防超卖：条件 WHERE stock >= 数量，0 行 = 没抢到）
        n = cur.execute(
            "UPDATE product SET stock = stock - %s WHERE id = %s AND stock >= %s",
            (quantity, product_id, quantity))
        if n == 0:
            conn.rollback()
            return jsonify({"error": "手慢了，库存不足"}), 400

        conn.commit()                       # 全成 → 提交
        # 关键一步：数据变了，删掉旧缓存（缓存失效），下次查询重新从 MySQL 加载
        get_redis().delete("product:list")
        return jsonify({"success": True, "order_id": order_id, "total": total})
    except Exception as e:
        conn.rollback()                     # 失败 → 全回滚
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ---------- 秒杀队列（Day 18/19：Redis 削峰 + 异步消化） ----------
def process_seckill(msg):
    """后台 worker 真正执行秒杀：原子扣库存 + 写订单（就是 Day 14 防超卖那套）"""
    data = json.loads(msg)
    user_id, product_id, quantity = data["user_id"], data["product_id"], data["quantity"]
    conn = get_mysql()
    cur = conn.cursor()

    def give_back():
        """处理失败 → 把 Redis 预扣的库存还回去（闭环）"""
        get_redis().incr(f"seckill:stock:{product_id}", quantity)

    try:
        # ① 查商品价格和库存
        cur.execute("SELECT price, stock FROM product WHERE id = %s", (product_id,))
        row = cur.fetchone()
        if not row:
            give_back()
            return {"status": "失败", "error": "商品不存在"}
        price, stock = row
        if stock < quantity:
            give_back()
            return {"status": "手慢了", "error": f"库存不足，只剩 {stock} 件"}

        # ② 写订单 + 明细
        total = price * quantity
        cur.execute("INSERT INTO orders (user_id, total) VALUES (%s, %s)", (user_id, total))
        order_id = cur.lastrowid
        cur.execute(
            "INSERT INTO order_item (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
            (order_id, product_id, quantity, price)
        )
        # ③ 原子扣库存（0 行 = 手慢了 → 回滚 + 回补）
        n = cur.execute(
            "UPDATE product SET stock = stock - %s WHERE id = %s AND stock >= %s",
            (quantity, product_id, quantity))
        if n == 0:
            conn.rollback()
            give_back()
            return {"status": "手慢了", "error": "库存不足"}

        conn.commit()
        get_redis().delete("product:list")   # 库存变了，缓存失效
        return {"status": "成功", "order_id": order_id, "total": float(total)}
    except Exception as e:
        conn.rollback()
        give_back()
        return {"status": "失败", "error": str(e)}
    finally:
        conn.close()


def seckill_worker():
    """后台消费者：BRPOP 从队列叫号，叫到一个处理一个（削峰填谷）
    带 try 保护：单条消息处理失败不影响 worker 继续跑（真实架构底线）"""
    r = get_redis()
    print("👷 秒杀 worker 已启动，开始排队消化...")
    while True:
        try:
            msg = r.brpop(SECKILL_QUEUE, timeout=5)   # 队列空就等 5 秒
            if msg is None:
                continue
            body = msg[1]
            result = process_seckill(body)
            data = json.loads(body)
            # 结果写回 Redis，用户通过 /seckill/result 查询
            r.set(f"seckill:result:{data['user_id']}", json.dumps(result, ensure_ascii=False), ex=600)
            print(f"⚡ 处理 {data['user_id']} 抢 {data['product_id']}：{result['status']}")
        except Exception as e:
            print(f"⚠️ worker 遇到异常继续跑：{e}")


@app.route("/seckill", methods=["POST"])
def seckill():
    """秒杀接口（削峰版）：Redis 预扣库存粗筛 → 进队秒回；worker 后台消化写 MySQL
    接口层只碰 Redis（1000 并发无压力），MySQL 只被 worker 慢吞吞地访问"""
    data = request.get_json()
    user_id = data.get("user_id")
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)

    r = get_redis()
    stock_key = f"seckill:stock:{product_id}"

    # ① 预扣库存（原子 DECR）。首次秒杀时 key 不存在 → 从 MySQL 读一次初始化
    if not r.exists(stock_key):
        conn = get_mysql()
        cur = conn.cursor()
        cur.execute("SELECT stock FROM product WHERE id = %s", (product_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "商品不存在"}), 404
        r.set(stock_key, row[0])

    left = r.decr(stock_key, quantity)
    if left < 0:
        r.incr(stock_key, quantity)          # 扣过头了，还回去
        return jsonify({"status": "售罄", "message": "手慢了，商品已被抢光"}), 200

    # ② 预扣成功 → 进队（LPUSH）→ 秒回。真正下单由后台 worker 异步做
    msg = json.dumps({"user_id": user_id, "product_id": product_id, "quantity": quantity},
                     ensure_ascii=False)
    r.lpush(SECKILL_QUEUE, msg)
    queue_len = r.llen(SECKILL_QUEUE)
    return jsonify({"status": "排队中", "queue_len": queue_len,
                    "message": f"已收到你的抢购请求（{user_id} 抢商品 {product_id}），排队中..."})


@app.route("/seckill/result")
def seckill_result():
    """查抢购结果：排队中 / 成功 / 手慢了 / 失败"""
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400
    r = get_redis()
    cached = r.get(f"seckill:result:{user_id}")
    if cached is None:
        return jsonify({"status": "排队中", "message": "还在排队，稍后再查"})
    return jsonify(json.loads(cached))


if __name__ == "__main__":
    from werkzeug.serving import run_simple
    # 先启动后台 worker（消费秒杀队列），再启动 Flask
    threading.Thread(target=seckill_worker, daemon=True).start()
    # threaded=True：多线程处理并发请求（秒杀必需；开发服务器连接数有限，
    # 真实生产用 gunicorn 等多进程 WSGI 服务器扛百万连接）
    run_simple("127.0.0.1", 5000, app,
               use_debugger=True, use_reloader=False, threaded=True)
