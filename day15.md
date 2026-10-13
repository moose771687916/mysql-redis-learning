# Day 15 · Redis 进阶：事务 · 发布订阅 · 分布式锁

> 日期：2026-10-13 · 主题：把 Redis 从"缓存"升级成"会办事的全能选手"
> 前置：Day 6 Redis 入门（String/过期/自增）· Day 7 MySQL 事务 · Day 10 秒杀

---

## 一、今日成果（一句话）

**Redis 三大进阶能力全部通关：事务（MULTI/EXEC 打包执行，但无回滚）、发布订阅（一个发 N 个收的广播）、分布式锁（SET NX EX 多服务器协调）——命令行 + 三个 Python 演示脚本全跑通，还搞懂了 QUEUED 和 nil 两个神秘单词。**

---

## 二、核心概念

### A. Redis 事务 MULTI/EXEC = 打包下单

```
MULTI → OK                   开始打包
SET money:tom 100 → QUEUED   命令抄进单子（排队，没执行）
SET money:jerry 50 → QUEUED  继续排队
EXEC → 1) OK 2) OK           一口气全部执行
```

- 提示符会变成 `127.0.0.1:6379(TX)>`：TX = transaction（事务中），EXEC 后恢复。
- **QUEUED = "记下了，还没执行"**——这就是"打包"。
- **关键区别 vs MySQL 事务**：
  - MySQL：一组操作**要么全成、要么全回滚**（Day 7 超买 9999 台整单回滚）
  - Redis：**没有回滚**！中途一条出错，后面的命令照样执行（实测：incr 报错，money:tom 照样变 66）
- **结论**：强一致的事（转账、下单）交给 MySQL；Redis 事务只做"打包快跑"。

### B. 发布订阅 PUBLISH/SUBSCRIBE = 对讲机广播

- `PUBLISH 频道 消息` = 喊话（发的人不知道谁在听）
- `SUBSCRIBE 频道` = 挂机收听（会一直等消息，阻塞）
- 场景：秒杀开抢通知、直播开播提醒、后台推消息——**一个发，N 个收**
- 实测：用户 A、B 同时收到运营的 3 条广播。

### C. 分布式锁 SET NX EX = 厕所门锁（多服务器协调）

```
SET lock:daily_job "server1" NX EX 10
```

- **NX** = Not eXists：锁不存在才能设置成功（= 抢到资格）
- **EX 10** = 10 秒自动过期（= 拿锁的人挂了，锁自动弹开，防死锁）
- 抢到返回 `OK`，没抢到返回 `nil`（= 空/失败）
- 释放锁要**带身份判断**（`GET 锁 == 自己` 才 DEL），防止误删别人的锁
- **为什么叫"分布式"**：MySQL 行锁管"一个数据库内部"，管不了"多台服务器之间"——Redis 是公共柜台，所有服务器都看得见
- 实测：3 台服务器抢任务，只有 server0 抢到执行，server1/2 自动放弃。

---

## 三、今日实操全记录

### 3.1 命令行（memurai-cli）
- MULTI/SET/EXEC 打包：QUEUED × 2 → EXEC → 1) OK 2) OK ✅
- SET lock NX EX：user1 → OK（抢到），user2 → (nil)（被拒）✅

### 3.2 redis_tx_demo.py（事务转账）
- 演示 1：tom 100 → 70，jerry 50 → 80，一起变 ✅
- 演示 2（重点）：`incr` 对字符串报错，但后面的 `set` **照样执行**（money:tom = 66）→ **Redis 不回滚** ✅

### 3.3 pubsub_demo.py（广播）
- 用户 A、B 订阅频道挂机 → 运营发 3 条广播 → 两人全部收到 ✅

### 3.4 dist_lock_demo.py（分布式锁）
- 3 台服务器抢"清空过期订单"任务 → server0 抢到执行、server1/2 放弃 → server0 完成任务并释放锁 ✅

---

## 四、今日踩坑/要点

1. **QUEUED ≠ OK**：QUEUED 是"排进单子"，EXEC 才真正执行。
2. **nil = 空**：SET NX 失败返回 nil = 没抢到锁（不是报错，是"结果为空"）。
3. **Redis 事务没有回滚**：别用 Redis 做"必须全成或全撤"的事。
4. **释放锁要验身份**：`if GET(lock) == 自己: DEL`，防止误删别人的锁。
5. **SUBSCRIBE 会阻塞**：命令行跑它会卡住等消息，演示用 Python 双线程更可控。

---

## 五、速查表

| 想干什么 | 命令/代码 |
|---|---|
| 打包执行多条命令 | `MULTI` → 命令们 → `EXEC` |
| 取消打包 | `DISCARD` |
| 抢锁 | `SET key value NX EX 10` → OK=抢到，nil=没抢到 |
| 释放锁（验身份） | `if GET(key)==自己: DEL key` |
| 发布消息 | `PUBLISH 频道 消息` |
| 订阅频道 | `SUBSCRIBE 频道`（阻塞） |
| Python 事务 | `pipe = r.pipeline(); pipe.multi(); ...; pipe.execute()` |
| Python 发布 | `r.publish("频道", "消息")` |
| Python 订阅 | `ps = r.pubsub(); ps.subscribe("频道"); ps.listen()` |
| Python 抢锁 | `r.set(key, val, nx=True, ex=10)` |
