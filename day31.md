# Day 31：Docker 部署终极商城（一条命令起全套）

> 把 Day 28 的终极商城容器化：MySQL 主从 + Redis + 商城 API 装进 4 个容器，`docker compose up` 一条命令全部上线。
> 真实跑数：1000 人抢 5 件 → 0 超卖 0 重复 0 阻塞；从库挂了自动切主库，恢复自动切回。

## 一、Docker 是干嘛的（30 秒版）

**把"环境"本身打包成文件**。以前你配 MySQL 要下载、解压、改配置、起服务；现在一个 `mysql:8.0` 镜像 = 一个装好 MySQL 的"运行环境快照"，拉下来就能跑，到哪台机器都一样。

| 概念 | 类比 | 一句话 |
|---|---|---|
| 镜像（image）| 安装包 | 只读模板，`mysql:8.0` 就是"装好 MySQL 的模板" |
| 容器（container）| 运行中的程序 | 镜像跑起来就是容器，可以起停删 |
| 数据卷（volume）| 外挂硬盘 | 容器删了数据还在（`mysql/data` 放卷里）|
| 网络（network）| 内网 | 容器之间用服务名互访（`mysql-master:3306`）|
| compose | 一键脚本 | 一个 yml 文件描述"几台机器怎么协作" |

## 二、4 容器编排（docker-compose.yml 核心）

```
┌────────────────────────────────────────────┐
│  shop-app      Flask 商城 API + 3 消费者    │  ← :5001
│    ↓ 服务名互访（不走映射端口）              │
│  shop-redis    缓存/队列/锁                  │  ← :6380→6379
│  shop-mysql-master  主库（binlog+GTID）     │  ← :4308→3306
│  shop-mysql-slave   从库（自动复制）         │  ← :4309→3306
└────────────────────────────────────────────┘
```

要点：
- **端口映射**：本机已有 MySQL 4306/4307 和 Memurai 6379，容器端口必须避开 → 4308/4309/6380
- **服务名互访**：容器内 `app` 连数据库用 `mysql-master:3306`，不走映射端口
- **启动顺序**：`depends_on + healthcheck`——从库等主库 healthy 才起，app 等全部 healthy 才起
- **初始化 SQL**：挂到 `/docker-entrypoint-initdb.d/`，容器首次启动自动执行（建表、建复制用户、CHANGE MASTER）

## 三、真实踩的 4 个坑（必看，都修好了）

### 坑 1：拉镜像被墙（国内必经）
`registry-1.docker.io` 连不上。解法：配镜像加速器。
```
编辑 %USERPROFILE%\.docker\daemon.json，加 registry-mirrors：
"registry-mirrors": ["https://dockerproxy.net", "https://docker.m.daocloud.io", ...]
重启 Docker Desktop 生效
```

### 坑 2：MySQL 8 复制认证失败（Slave_IO_Running 一直 Connecting）
`caching_sha2_password` 插件要求复制连接走安全通道。解法：复制用户显式用老插件。
```sql
CREATE USER 'repl'@'%' IDENTIFIED WITH mysql_native_password BY 'repl123';
```

### 坑 3：消费者线程启动即死（最隐蔽）
app 启动瞬间 MySQL 可能没就绪，`mysql(MASTER)` 抛异常 → **daemon 线程异常没有日志、静默消失** → 队列没人消化。解法：连接失败重试，别让线程死。
```python
while True:
    try:
        conn = mysql(MASTER)
        break
    except Exception:
        time.sleep(2)
```

### 坑 4：熔断恢复"乒乓"
只做"从库失败切主库"还不够：读主库成功后不能直接恢复开关（从库可能还挂着，会来回切）。解法：**半开探测**——熔断态先短超时试连从库，通了才切回。
```python
if not slave_ok:
    probe = pymysql.connect(connect_timeout=2, **SLAVE)   # 短超时试一下
    probe.close()
    src, tag, slave_ok = SLAVE, "从库", True
```

## 四、真实跑数（验收输出）

```
① 重置：清订单/库存回5/清队列            ✅
② 读链路：第1次未命中读从库，后2次缓存命中 ✅
③ 秒杀：1000 请求全部发出，耗时 6.56s    ✅（接口 0 阻塞）
④ 消费者：库存 0 = 订单 5 = 队列 0       ✅
⑤ 验收：零超卖零重复（参与1000人，抢到5人）✅
⑥ 熔断：停从库→读切主库(熔断) → 恢复→切回从库 ✅
```

## 五、怎么跑（Windows）

```powershell
cd D:\RediAndMySQL\day31
docker compose up -d --build    # 首次拉镜像几分钟，之后秒起
python test_shop.py             # 全链路压测验收
```

手动访问：
- 商品详情 `GET http://localhost:5001/api/product/1`
- 秒杀下单 `POST http://localhost:5001/api/seckill`  body: `{"uid":1001}`
- 状态 `GET http://localhost:5001/api/stats`
- 主库直连 `127.0.0.1:4308 root/root123`，从库 `127.0.0.1:4309`

停/清：
```powershell
docker compose down          # 停但保留数据
docker compose down -v       # 停+删数据卷（重新初始化，重跑 init.sql）
```

## 六、面试怎么讲

> "我把商城容器化部署：docker-compose 编排 MySQL 主从 + Redis + 应用 4 个容器，一条命令上线。用 healthcheck 控制启动顺序、GTID 自动定位复制位点；踩过 MySQL 8 复制认证、容器启动时序两个坑都解决了；做了一键压测脚本，1000 并发零超卖，从库故障自动熔断切主库、恢复半开探测自动切回。"

**简历一行**：`Docker Compose 编排 MySQL 主从/Redis/应用 4 容器一键部署，healthcheck 控制启动顺序，1000 并发压测零超卖，从库故障自动熔断+半开恢复`

## 七、明日预告

Day 32：把商城部署到真正的 Linux 服务器（云主机/虚拟机），用 nginx 反向代理 + 域名访问——"部署"和"上线"就差这一层。
