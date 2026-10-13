# MySQL + Redis 从零实战学习仓库

> 一个编程新手用 15 天，从零学完 MySQL + Redis，并亲手搭出**电商商城**的完整学习记录。
> 每天一个总结文档（`day01.md` ~ `day15.md`）+ 可运行的实战代码。

## 这是什么

这不是笔记堆砌，而是**每天动手写代码、跑通、截图验收**的实战仓库：

- **MySQL**：环境搭建 → 建库建表 → 增删改查 → 三表 JOIN → 聚合 → 事务 → 索引 → 隔离级别 → 悲观/乐观锁 → 并发压测防超卖
- **Redis**：安装（Windows 用 Memurai）→ String/过期/自增 → 缓存 → 秒杀原子扣库存 → 五种数据结构 → 持久化（RDB/AOF）→ 事务 → 发布订阅 → 分布式锁
- **实战项目**：Flask + MySQL + Redis 的电商商城（注册登录 / 商品缓存 / 购物车 / 下单事务 / 秒杀 / 防超卖）

## 15 天路线图

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

## 目录结构

```
├── day01.md ~ day15.md      # 每天的学习总结
├── day01/ ~ day15/          # 每天的可运行代码（按天归档）
│   ├── my_first_query.py    # 第一天：第一条 SELECT
│   ├── create_order.py      # 事务下单（含超买回滚演示）
│   ├── seckill_demo.py      # 秒杀：1000 人抢 13 件
│   ├── index_demo.py        # 20 万条数据索引提速演示
│   ├── stress_test.py       # 并发压测：BUG 版 vs 修复版
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

1. 启动 MySQL（`day01/start_mysql.bat`）与 Redis
2. 运行商城：`python app.py` → 浏览器打开 `http://localhost:5000`
3. 跑演示脚本：`python day14/stress_test.py`（并发压测）等

> 注：本地 MySQL 连接密码为教学用简单密码，仅限本地学习环境。
