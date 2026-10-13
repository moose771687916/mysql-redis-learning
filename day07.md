# Day 7 · 电商系统：五张表 + 事务下单 + Redis 缓存

> 日期：2026-10-11 · 主题：从学生管理系统升级为电商系统——多表设计终极版、事务、双库联手
> 前置：Day 1-6 全部（MySQL 核心 + Redis 入门 + 学生管理系统）

---

## 一、今日成果（一句话）

**电商系统"地基"完成：五张表建好、事务下单（commit/rollback）实测通过、Redis 缓存商品列表（命中比查库快 24 倍）——MySQL 与 Redis 第一次联手干活。**

---

## 二、核心概念

1. **电商五张表**：users（用户）/ product（商品）/ cart（购物车）/ orders（订单）/ order_item（订单明细）。
   - 外键挂钩：购物车行 = "某人把某商品放购物车"；订单 1→N 明细。
   - **price 快照**：明细存下单时价格，商品涨价不影响历史订单（真实电商做法）。
   - orders 不叫 order：ORDER 是数据库关键字，加 s 避开。
2. **事务 Transaction**：一组操作"要么全成、要么全不成"。
   - 下单三件套：①写订单 ②写明细 ③扣库存。
   - **commit** = 签字确认（全部成功才提交）；**rollback** = 整页作废（任何一步失败全回滚）。
   - 不这样做会出事：订单写了库存没扣 → 超卖；库存扣了订单没写 → 丢单。
3. **缓存套路（双库联手）**：先查 Redis → 没有再查 MySQL → 写回 Redis（30 秒过期）。
   - 实测：未命中 33.32 毫秒 vs 命中 1.38 毫秒（快 24 倍）。
   - 商品数据更新 → 删缓存 → 下次自动重新加载。

---

## 三、今日实操全记录

### 3.1 五张表 DDL（要点节选）

```sql
CREATE TABLE cart (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT NOT NULL DEFAULT 1,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (product_id) REFERENCES product(id)
);

CREATE TABLE orders (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  total DECIMAL(10,2) NOT NULL,
  status VARCHAR(20) DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE order_item (
  id INT PRIMARY KEY AUTO_INCREMENT,
  order_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT NOT NULL,
  price DECIMAL(10,2) NOT NULL,          -- 价格快照！
  FOREIGN KEY (order_id) REFERENCES orders(id),
  FOREIGN KEY (product_id) REFERENCES product(id)
);
```

### 3.2 事务下单（create_order.py 核心）

```python
try:
    # 查购物车 + 价格 + 库存（JOIN）
    # ① 库存不足 → conn.rollback() 直接取消
    # ② INSERT INTO orders → order_id
    # ③ INSERT INTO order_item（每件一行，价格快照）
    # ④ UPDATE product SET stock = stock - n
    conn.commit()        # 全部成功 → 提交
except Exception as e:
    conn.rollback()      # 任何一步失败 → 全回滚
```

**实测结果**：正常下单 → 订单 6、总额 477.00、三步全成；超买显示器 x9999（库存 20）→ 库存不足、整个订单回滚、orders 表无脏数据。

### 3.3 缓存商品列表（cache_demo.py 核心）

```python
cached = r.get("product:list")              # ① 先问 Redis
if cached: 直接返回                          #    命中 → 不碰 MySQL
查 MySQL → 组装数据                          # ② 未命中 → 查库
r.set("product:list", json.dumps(data), ex=30)  # ③ 写回，30 秒过期
```

**实测结果**：未命中 33.32ms → 命中 1.38ms / 1.01ms；删缓存后再查又变未命中并重新写入。

---

## 四、今日踩坑/要点

1. **DECIMAL 不能直接 JSON 序列化**：MySQL 的 DECIMAL 列在 Python 是 `Decimal` 对象，要 `float(r[2])` 转一下才能 `json.dumps`（新手必踩）。
2. **AUTO_INCREMENT 删了不回退**：测试删掉的订单号不回收，订单号继续往下长（真实系统要的就是"永不重复"）。
3. **超买演示会污染购物车**：往购物车塞了"显示器 x9999"，想再正常下单需先 `DELETE FROM cart WHERE product_id = 3;`。
4. 缓存命中的前提是缓存没过期（30 秒）——过了就自动失效，重新查库。

---

## 五、速查表

| 想干什么 | 方法 |
|---|---|
| 下单（三件事捆绑） | try: 三步操作 → `conn.commit()`；except: `conn.rollback()` |
| 缓存优先读取 | `r.get(键)` 有→返回；无→查库→`r.set(键, 数据, ex=秒)` |
| 数据更新后清缓存 | `r.delete(键)` |
| DECIMAL 转 JSON | `float(值)` |

---

## 六、下一步（Day 8 预告）

**给电商系统加 API 接口（Flask）**——让浏览器能访问你的商品列表：
- `http://localhost:5000/products` → 网页显示商品（数据走 MySQL + Redis 缓存）
- 学会"后端"最标志性的一块：**对外提供服务的接口**
- 之后：注册登录（密码加密）、购物车接口、下单接口

---

## 七、给未来的自己

- 事务 = 全有或全无，"commit 签字 / rollback 作废"。
- 缓存 = 先问 Redis，没有再问 MySQL，写回 Redis，删缓存即刷新。
- 五张表结构（用户/商品/购物车/订单/明细）是电商的通用骨架——大厂电商也是这个逻辑的放大版。
