# MySQL + Redis 从零实战学习仓库

> 一个编程新手用 31 天，从零学完 MySQL + Redis + Docker，并亲手搭出**电商商城**并部署上线的完整学习记录。
> 每天一个总结文档（`day01.md` ~ `day31.md`）+ 可运行的实战代码。

## 这是什么

这不是笔记堆砌，而是**每天动手写代码、跑通、截图验收**的实战仓库：

- **MySQL**：环境搭建 → 建库建表 → 增删改查 → 三表 JOIN → 聚合 → 事务 → 索引 → 隔离级别 → 悲观/乐观锁 → 并发压测防超卖
- **Redis**：安装（Windows 用 Memurai）→ String/过期/自增 → 缓存 → 秒杀原子扣库存 → 五种数据结构 → 持久化（RDB/AOF）→ 事务 → 发布订阅 → 分布式锁 → 缓存三兄弟防护
- **实战项目**：Flask + MySQL + Redis 的电商商城（注册登录 / 商品缓存 / 购物车 / 下单事务 / 秒杀 / 防超卖 / 防缓存穿透）

## 16 天路线图

| 天数 | 主题 | 产出 |
|---|---|---|
| Day 01 | MySQL 安装 + 第一条查询 | 环境 + 命令行入门 |
| Day 02 | 增删改查 + 参数化防注入 | 建库建表实操 |
| Day 03 | 三表 JOIN 拼成绩单 | 外键 + 联表查询 |
| Day 04 | 聚合统计（AVG/MAX/GROUP BY） | 五题全对 |
| Day 05 | 学生管理系统（Python + MySQL） | 7 功能菜单程序 |
| Day 06 | Redis 入门（SET/GET/EXPIRE/INCR） | 中文存取 + 过期 + 自增 |
| Day 07 | 电商五表设计 + 事务下单 | 五张表 + 回滚实战 |
| Day 08 | Flask 后端 + 商品缓存 API | 缓存命中快 24 倍 |
| Day 09 | 商城前端页面 | 浏览器购物体验 |
| Day 10 | 登录加密 / 购物车 / 秒杀 | 密码哈希 + 原子扣库存 |
| Day 11 | 持久化 RDB/AOF + 索引 | 20 万条数据索引提速 53 倍 |
| Day 12 | Redis 五种数据结构 | 哈希/列表/集合/有序集合 |
| Day 13 | 事务隔离 + 悲观/乐观锁 | 可重复读 + 版本号对账 |
| Day 14 | 并发压测 + 防超卖修复 | 100 人抢 13 件不超卖 |
| Day 15 | Redis 事务 / 发布订阅 / 分布式锁 | 三件套全通关 |
| Day 16 | 缓存三兄弟：穿透/击穿/雪崩 | 商城防穿透实战（布隆+空值+互斥锁） |
| Day 17 | MySQL 执行计划 EXPLAIN | 10 万条数据 8 场景实测索引失效 |
| Day 18 | Redis 消息队列削峰 | LPUSH/BRPOP 排队消化，直连 vs 队列实测 |
| Day 19 | 秒杀接口实战（队列接进商城） | /seckill 秒回排队 + worker 异步下单，1000 人全响应 |
| Day 20 | Redis 主从复制 | 一主一从：主写从读、全量同步、从库只读、断线补账 |
| Day 21 | 哨兵自动故障转移 | 主库倒下 5 秒自动扶正，数据不丢、业务不停 |
| Day 22 | 读写分离版商城 | 读走从库写走主库，熔断降级自动切回 |
| Day 23 | MySQL 主从复制 | binlog 增量同步，主写从读、删也同步、掉线补账 |
| Day 24 | MySQL 读写分离落地商城 | 读走从库写走主库，熔断降级自动切回 |
| Day 25 | MySQL 主库故障转移 | 宕机→从库提权扶正（数据完整可写）→旧主恢复挂回 |
| Day 26 | Redis Cluster 真集群 | WSL 6 节点：16384 槽分片、扩容迁槽、从节点自动顶班 |
| Day 27 | MySQL 分库分表（水平拆分）| 30 万订单按 user_id 取模拆 4 表，带键查询快 3.9 倍 |
| Day 28 | 终极版商城（27 天全家桶）| 缓存+队列+锁+幂等+读写分离+熔断，1000 人抢 5 件零超卖 |
| Day 29 | 面试冲刺：全知识点题库 | 40 道面试题（MySQL/Redis/项目）+ 面试模拟器 |
| Day 31 | Docker 部署终极商城 | 4 容器编排一键上线，1000 并发零超卖，熔断+半开恢复 |

## 目录结构

```
├── day01.md ~ day25.md      # 每天的学习总结
├── day01/ ~ day25/          # 每天的可运行代码（按天归档）
│   ├── my_first_query.py    # 第一天：第一条 SELECT
│   ├── create_order.py      # 事务下单（含超买回滚演示）
│   ├── seckill_demo.py      # 秒杀：1000 人抢 13 件
│   ├── index_demo.py        # 20 万条数据索引提速演示
│   ├── stress_test.py       # 并发压测：BUG 版 vs 修复版
│   ├── cache_attack_demo.py # 缓存穿透：1000 次攻击三方案对比
│   ├── explain_demo.py      # EXPLAIN 执行计划：8 场景索引失效实测
│   ├── mq_demo.py           # 消息队列削峰：直连 vs LPUSH/BRPOP 队列实测
│   ├── seckill_queue_demo.py # 秒杀接口全链路：1000 人抢 13 件
│   ├── replication_demo.py  # 主从复制：一主一从主写从读
│   ├── failover_demo.py     # 哨兵故障转移：主库倒下自动扶正
│   ├── read_write_demo.py   # 读写分离商城：读走从库写走主库+熔断降级
│   ├── mysql_replication_demo.py # MySQL 主从复制：binlog 增量同步
│   ├── mysql_read_write_demo.py  # MySQL 读写分离商城：读走从库写走主库
│   ├── mysql_failover_demo.py    # MySQL 主库故障转移：宕机→扶正→恢复
│   ├── redis_cluster_demo.py     # Redis Cluster 真集群：WSL 6 节点分片+扩容+故障转移
│   ├── sharding_demo.py          # MySQL 分库分表：30 万订单取模拆 4 表+三痛+雪花 ID
│   ├── final_shop_demo.py        # 终极版商城：缓存+队列+锁+读写分离+熔断 全家桶
│   ├── interview_sim.py          # 面试模拟器：抽题→口头答→对照答案
│   ├── day31/                    # Docker 版商城：docker-compose 4 容器（MySQL主从+Redis+app）
│   │   ├── docker-compose.yml    # 一条命令编排全套
│   │   ├── app/Dockerfile        # 商城应用镜像
│   │   └── test_shop.py          # 一键压测验收（1000并发+熔断演练）
│   └── ...
├── app.py                   # 电商商城后端（Flask + MySQL + Redis）
├── static/shop.html         # 商城前端页面
```

## 技术栈

- **Python 3** + Flask（后端接口）
- **MySQL 8**（关系型数据库：事务、索引、锁）
- **Redis**（缓存 + 秒杀 + 分布式锁；Windows 用 Memurai 替代）
- **pymysql / redis-py**（Python 连接库）

## 运行方式

1. 启动 MySQL（`day01/start_mysql.bat`，**端口 4306**）与 Redis
2. 运行商城：`python app.py` → 浏览器打开 `http://localhost:5000`
3. 跑演示脚本：`python day18/mq_demo.py`（队列削峰）、`python day19/seckill_queue_demo.py`（秒杀接口全链路）、`python day20/replication_demo.py`（Redis 主从复制）、`python day21/failover_demo.py`（哨兵故障转移）、`python day22/read_write_demo.py`（读写分离商城）、`python day23/mysql_replication_demo.py`（MySQL 主从复制）、`python day24/mysql_read_write_demo.py`（MySQL 读写分离商城）、`python day25/mysql_failover_demo.py`（MySQL 主库故障转移）、`python day26/redis_cluster_demo.py`（Redis Cluster 真集群，需 WSL）、`python day27/sharding_demo.py`（MySQL 分库分表）、`python day28/final_shop_demo.py`（终极版商城全家桶）、`python day29/interview_sim.py`（面试模拟器）等
4. Docker 版商城：`cd day31 && docker compose up -d --build && python test_shop.py`（需 Docker Desktop，镜像加速器已配好，见 day31.md 坑 1）

> 注：本地 MySQL 连接密码为教学用简单密码，仅限本地学习环境；
> 端口用 4306 是因为 Windows 会随机保留端口区间（Hyper-V），3306/3307 曾被系统锁死。
> 商城支持读写分离：`set REDIS_RO_PORT=6380` 后再 `python app.py`，读接口走从库（见 day22）。
> MySQL 主从：主库 4306（server-id=1, 已开 binlog）+ 从库 4307（server-id=2），复制账号 repl/repl123（见 day23）。
> MySQL 读写分离：`set MYSQL_RO_PORT=4307` 后再 `python app.py`，纯读接口走从库（见 day24）。
