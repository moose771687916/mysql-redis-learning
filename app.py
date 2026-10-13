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

app = Flask(__name__)

# 项目根目录（无论从哪个目录启动都能找到 static 文件夹）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_mysql():
    return pymysql.connect(
        host="127.0.0.1", user="root", password="root123",
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

    # ③ 写回 Redis（30 秒过期）
    r.set("product:list", json.dumps(data, ensure_ascii=False), ex=30)
    print("🐢 查了 MySQL，已写入缓存")

    return jsonify(data)


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


if __name__ == "__main__":
    # debug=True：改代码后自动重启；port=5000：浏览器访问的端口
    app.run(debug=True, port=5000)
