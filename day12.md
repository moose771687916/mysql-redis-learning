# Day 12 · Redis 五种数据结构全通关（上篇：数据类型）

> 日期：2026-10-12~13 · 主题：把 Redis 从"只会一种 String"升级成"五种结构全掌握"
> 前置：Day 6 Redis 入门（String）· Day 10 秒杀（DECR/SETNX）

---

## 一、今日成果（一句话）

**Redis 官方五种数据结构全部通关：String（复习）＋ Hash（购物车）＋ List（消息队列）＋ Set（一人一单去重）＋ ZSet（排行榜）——每种都配了商城真实场景并亲手敲命令验证。**

---

## 二、五种数据结构全景

| 结构 | 一句话 | 长啥样 | 商城场景 | 核心命令 |
|---|---|---|---|---|
| **String** | 一个值 | `"cart:9" → "鼠标"` | 缓存、库存、登录态 | SET / GET / INCR |
| **Hash** | 一个对象 | `"cart:9" → {product:1→2, product:2→1}` | 购物车、用户信息 | HSET / HGETALL / HINCRBY / HLEN |
| **List** | 排队队列 | `order:notify → [order8, order7, order6]` | 订单通知、消息队列 | LPUSH / RPOP / LRANGE / LLEN |
| **Set** | 去重名单 | `seckill:users:3 → {user1, user2, user3}` | 秒杀一人一单 | SADD / SMEMBERS / SCARD / SISMEMBER |
| **ZSet** | 带分排序 | `rank:hot → {mouse:370, monitor:245, ...}` | 销量榜、热搜榜、战力榜 | ZADD / ZINCRBY / ZREVRANGE |

---

## 三、核心概念（大白话版）

### Hash = 一个键下挂一堆"字段:值"
- 购物车一个键装完：`HSET cart:9 product:1 2` → 加数量 `HINCRBY`（原子）。
- 对比 String：String 一键一值，3 个商品要 3 个键；Hash 一个键全装下，**一个用户一个键，天然隔离**。

### List = 排队的人（先进先出）
- `LPUSH` 左边塞人，`RPOP` 右边放人走 = **先来的先走**。
- **消息队列**：下单的人不等，通知排队后台慢慢处理（发短信/记日志）——大厂削峰填谷基本功。
- 注意：List **允许重复**（去重不是它的活）。

### Set = 自动去重名单
- `SADD` 返回 **1 = 第一次加入（抢到）**，**0 = 已经在（重复，拒绝）**。
- 狂点 10 次只有第一次返回 1——**不用写查重代码，去重是出厂设置**。
- 对比 SETNX（一人一个键）：SADD **一个集合装所有人**，更省 + 能看名单（SMEMBERS）。

### ZSet = 带分数的 Set（排行榜专用）
- `ZADD 键 分数 成员`：分数一变，**自动重排**。
- `ZREVRANGE 0 9` 一条命令拿前十；`ZINCRBY +1` 卖一单加一分。
- 为什么不用 MySQL 做排行榜：MySQL 每查一次重新排序全表（慢）；ZSet 加分即重排（毫秒级）。

---

## 四、今日实操全记录

### Hash（购物车）
- HSET cart:9 三件商品 → HGETALL 显示 {product:1:2, product:2:1, product:3:5} → HINCRBY 商品1 +1 → HLEN 3 ✅

### List（订单通知队列）
- LPUSH ×3 → LRANGE 显示 [order8, order7, order6] → RPOP 弹出 order6（先来的先走）✅
- 踩坑：**命令敲错地方**——在 mysql> 里敲 LPUSH 被当成 SQL 挂起（`->`），要先 exit 再 memurai-cli 进 Redis（提示符 `127.0.0.1:6379>`）

### Set（秒杀名单）
- 踩坑：Python 演示残留 3 个成员 → 自己 SADD 全返回 0（不是 bug，是去重生效！）→ DEL 清场 → SADD user4 返回 **1**（亲眼看到第一次加入）✅

### ZSet（排行榜）
- 踩坑：Python 演示的中文成员 + 自己敲的英文成员混在同一个键（8 个成员）→ **不同演示要用不同键名或先 DEL** → 清场重来 → ZADD ×4 全返回 1 → ZINCRBY +50 → ZREVRANGE 干净排序 mouse370 > monitor245 > keyboard120 > chair98 ✅

---

## 五、今日踩坑/要点

1. **命令敲错地方**：`mysql>` 是 MySQL 地盘，Redis 命令要在 `memurai-cli` 的 `127.0.0.1:6379>` 里敲。
2. **中文在命令行显示乱码**（`\xe6\x97\xa0...` = "无线鼠标" 的 UTF-8 转义）：数据没坏，命令行成员用英文。
3. **演示残留**：我 Python 演示过的键（cart:9 / seckill:users:3 / rank:hot）会有残留数据，自己实操前先 `DEL 键` 清场，别被"全 0 / 8 个成员"搞懵。
4. **List 允许重复、Set 去重**——两个结构别混。
5. **冒号是命名习惯不是语法**：`seckill:users:3` = 秒杀:名单:3号商品（人肉文件夹），`user4` 是值（成员）。
6. **命令命名规律**：前缀=结构（S=Set/L=List/H=Hash/Z=ZSet），后缀=动作（ADD/PUSH/POP/MEMBERS）。

---

## 六、速查表

| 想干什么 | 命令 |
|---|---|
| 购物车加商品 | `HSET cart:9 product:1 2` |
| 购物车加数量（原子） | `HINCRBY cart:9 product:1 1` |
| 看整个购物车 | `HGETALL cart:9` |
| 队列塞一条 | `LPUSH order:notify order6_paid` |
| 队列弹出处理 | `RPOP order:notify` |
| 一人一单（去重） | `SADD seckill:users:3 user4`（返回 1 抢到 / 0 重复） |
| 看抢到名单 | `SMEMBERS seckill:users:3` |
| 排行榜加成员 | `ZADD rank:hot 320 mouse` |
| 分数 +50 | `ZINCRBY rank:hot 50 mouse` |
| 看前十 | `ZREVRANGE rank:hot 0 9 WITHSCORES` |
| 清场 | `DEL 键名` |

---

## 七、下一步（Day 13 预告）

- **MySQL 事务隔离 + 锁**：并发世界的地基——两个人同时下单/改钱，MySQL 怎么保证不乱账（隔离级别、行锁、乐观/悲观锁）。
- 学完这课，"高并发怎么解决"就能从"锁"这一个字，展开成一套完整回答。

---

## 八、给未来的自己

- Redis 五兄弟：**String 一个值 / Hash 一个对象 / List 排队 / Set 去重 / ZSet 排名**——面试背这个口诀就够。
- 冒号 = 人肉文件夹；命令前缀 = 结构；返回 1/0 = 加没加进去。
- 消息队列 = 下单不等通知；排行榜 = 加分即重排；一人一单 = SADD 返回 0 就是拦下了。
- 你的直觉又升级了：**"狂点 = 去重的活，Set 出厂自带"**、**"ZSet = 带分的排行榜"**——全都能写进简历。
