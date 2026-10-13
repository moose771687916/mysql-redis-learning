# Day 6 · Redis 入门：内存数据库与缓存

> 日期：2026-10-11 · 主题：Redis（Memurai）——SET/GET/EXPIRE/TTL/INCR + Python 中文存取
> 前置：Day 1-5 已完成 MySQL 全流程与学生管理系统

---

## 一、今日成果（一句话）

**双通道打通 Redis：命令行（memurai-cli）亲手完成 存/取/过期/倒计时/自增，Python（redis_demo.py）实现中文完美存取——正式拥有"MySQL + Redis"双数据库实操经验。**

---

## 二、核心概念

1. **Redis = 跑在内存里的"超级大字典"**：键值对（key-value），读写比磁盘快几十上百倍。
2. **与 MySQL 的分工**：MySQL 存永久账本（硬盘、可靠、慢一点）；Redis 存热数据/缓存（内存、快、可过期）。应用套路：**先查 Redis，没有再查 MySQL，查到写回 Redis**。
3. **过期 EXPIRE**：给数据设保质期，到期自动消失（不用人删）。类比：牛奶过期下架、登录态 30 分钟失效（安全）、验证码限时有效。
4. **TTL = Time To Live**：查还剩多少秒。
5. **INCR 原子自增**：高并发下点赞/访问量/排队号也不会算错。
6. **Windows 版说明**：Redis 官方无 Windows 版 → 用 Memurai（兼容 Redis 命令）替代，服务名 Memurai 开机自启，监听 127.0.0.1:6379。

---

## 三、今日实操全记录

### 3.1 命令行（memurai-cli）

```
127.0.0.1:6379> SET user:name tom        → OK
127.0.0.1:6379> GET user:name            → "tom"
127.0.0.1:6379> SET user:age 19          → OK
127.0.0.1:6379> EXPIRE user:name 60      → (integer) 1
127.0.0.1:6379> TTL user:name            → (integer) 55（倒计时）
127.0.0.1:6379> INCR counter             → 1
127.0.0.1:6379> INCR counter             → 2
127.0.0.1:6379> INCR counter             → 3
127.0.0.1:6379> exit                     → 退出
```

### 3.2 Python（redis_demo.py）

```python
import redis
r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

r.set("user:name", "小明")          # 存中文（Python 走 UTF-8，无乱码）
name = r.get("user:name")           # 读出：小明
r.set("session:token", "abc123", ex=30)   # 30 秒过期一步到位
left = r.ttl("session:token")             # 剩余秒数
r.incr("post:likes")                      # 原子自增
```

---

## 四、速查表

| 命令/Python | 意思 | 生活类比 |
|---|---|---|
| `SET key value` / `r.set()` | 存 | 往储物柜放东西 |
| `GET key` / `r.get()` | 取 | 报柜号拿东西 |
| `EXPIRE key 秒` / `ex=秒` | 保质期 | 贴生产日期 |
| `TTL key` / `r.ttl()` | 还剩几秒 | 看剩余保质期 |
| `INCR key` / `r.incr()` | +1 自增 | 点赞计数器 |
| `DEL key` / `r.delete()` | 删除 | 扔东西 |

---

## 五、今日踩坑/要点

1. **Memurai 拼写**：`memurai-cli`（mem-u-rai，整体一个词，中间无空格）——不是 memirai。
2. **CLI ≠ clear**：CLI = Command Line **Interface**（命令行接口）；clear 是清屏命令。
3. **Windows 命令行粘贴中文有编码坑**（引号被吃、乱码）——教学阶段键值用英文；中文用 Python（UTF-8）完美。
4. **SET 报错打印用法说明书** = 参数没给全（比如值空着），方括号里都是可选项。
5. Redis 退出命令是 `exit`（和 MySQL 一样）。

---

## 六、下一步（Day 7 预告）

**终极一战：把 Redis 接进学生管理系统做"缓存层"**
- MySQL 存永久数据（账本）+ Redis 存热数据（缓存，30 秒过期自动刷新）
- 实现真实项目的经典套路：先查 Redis → 没有再查 MySQL → 写回 Redis
- 第一次让两个数据库一起干活

---

## 七、给未来的自己

- Redis = 快但会丢（内存），MySQL = 慢但可靠（硬盘）——搭档关系，不是替代关系。
- 过期 = 自动清理 = 缓存系统的灵魂。
- 命令行学的每个命令，Python 里都有对应动作（r.set / r.get / r.ttl / r.incr）。
