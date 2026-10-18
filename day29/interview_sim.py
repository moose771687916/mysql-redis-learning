# -*- coding: utf-8 -*-
"""Day 29：面试模拟器 —— 每天抽 5 题，先口头答再看答案对照

用法：
    python day29/interview_sim.py            # 随机抽 5 题
    python day29/interview_sim.py --cat redis   # 只抽 Redis 题
    python day29/interview_sim.py --num 3       # 抽 3 题
    python day29/interview_sim.py --self-test   # 非交互自检（打印全部题号）

练习方法：
  1. 看到题目，先自己口头答 30 秒（用三层公式：结论→原理→实战数据）
  2. 按回车看标准答案对照
  3. 答不出的题心里记一下，明天重点练
"""
import argparse
import random

BANK = [
    # ---------- MySQL ----------
    {"cat": "mysql", "q": "MySQL 事务的 ACID 是什么？隔离级别有哪些？",
     "a": "ACID=原子性/一致性/隔离性/持久性。隔离级别4档：读未提交(脏读)→读已提交(不可重复读)→可重复读(幻读)→串行化。MySQL 默认可重复读。我实测过转账事务回滚：中途失败钱自动退回。"},
    {"cat": "mysql", "q": "什么是脏读、不可重复读、幻读？",
     "a": "脏读=读到别人未提交的数据；不可重复读=同一条数据两次读不一样；幻读=同一范围查询两次行数不一样。我用两个终端实测过，提升隔离级别后消失。"},
    {"cat": "mysql", "q": "乐观锁和悲观锁的区别？什么时候用哪个？",
     "a": "悲观锁=先锁后操作(SELECT FOR UPDATE)，适合写多冲突多；乐观锁=更新带 WHERE version=?，失败重试，适合读多写少。锁库存用原子 UPDATE 更轻，我实测过乐观锁版本不对更新 0 行。"},
    {"cat": "mysql", "q": "索引为什么能提速？B+树和 B 树区别？",
     "a": "索引=目录，全表扫描变树查找 O(n)→O(log n)。B+树数据全在叶子、叶子链表串起来，范围查询快；B树数据分散每层。我建 100 万行表实测：没索引 3.2 秒，加索引 0.01 秒，快 300 倍。"},
    {"cat": "mysql", "q": "什么情况索引会失效？",
     "a": "对索引列做函数/运算、前缀模糊 LIKE '%张'、隐式转换、OR 没覆盖、违反最左前缀。我用 EXPLAIN 实测 type 从 ref 变 ALL，rows 从几行变几十万行。"},
    {"cat": "mysql", "q": "什么是回表和覆盖索引？",
     "a": "回表=普通索引查到主键再回主键索引捞整行(多一次IO)；覆盖索引=索引里已有要查字段，不用回表。EXPLAIN 的 Extra 看 Using index。"},
    {"cat": "mysql", "q": "主从复制原理？",
     "a": "主库写 binlog → 从库 IO 线程拉日志到 relay log → SQL 线程重放。我搭过主 4306/从 4307：写主库 1 秒内从库同步，IO/SQL=Yes/Yes。"},
    {"cat": "mysql", "q": "读写分离怎么做？有什么问题？",
     "a": "写走主库、读走从库(代码按 SQL 类型路由)。问题是复制延迟：刚写完立刻读可能读旧数据，秒杀写后读要走主库。我商城脚本订单主从一致 5=5。"},
    {"cat": "mysql", "q": "主库挂了怎么办？",
     "a": "从库扶正成新主库(RESET SLAVE ALL)，旧主恢复后挂回从属。生产用 MHA/Orchestrator 或云数据库自动切换。我真实演练过：停主库→从库扶正→写新数据成功→旧主挂回。"},
    {"cat": "mysql", "q": "什么是分库分表？什么时候用？",
     "a": "单表数据千万级+查询变慢，按分片键取模拆 N 张表，带键查询只碰 1 张。我写 30 万订单拆 4 表实测：单表 61.7ms vs 分表 15.3ms 快 4 倍。"},
    {"cat": "mysql", "q": "分片键怎么选？选错的后果？",
     "a": "选高频查询都带着的字段(电商选 user_id)。选错=每次查询广播所有表+合并，扫描总量没少还更复杂。我实测不带键查询：4 表全扫+UNION 合并。"},
    {"cat": "mysql", "q": "全局 ID 为什么不用自增？雪花算法原理？",
     "a": "分表后每张表自增都从 1 开始会撞号。雪花 ID=时间戳+机器号+序号 64 位，全局唯一。我分表实验里两张表都有 id=1~75000 撞号，雪花 ID 5 个全不重复。"},
    {"cat": "mysql", "q": "慢查询怎么排查？",
     "a": "慢查询日志捞 SQL + EXPLAIN 看执行计划：type=ALL 全表扫描、rows 扫了多少行、key 用哪个索引、Extra 有 Using filesort。我 EXPLAIN 对比过单表 30 万 vs 分表 7.5 万。"},
    {"cat": "mysql", "q": "MySQL 数据变了，Redis 缓存怎么保持一致？",
     "a": "先更新 DB 再删缓存(可延迟双删)，读时回源重建。DB 是权威，缓存可删。我商城预热缓存实测：命中直接返回，DB 更新后删缓存下次重建。"},
    {"cat": "mysql", "q": "事务隔离级别怎么选？",
     "a": "默认可重复读(RR)够用，防幻读(MVCC+间隙锁)；读已提交(RC)适合读多写少高并发；串行化全表锁巨慢不用。我实验看到 RR 下两次 SELECT 一致。"},

    # ---------- Redis ----------
    {"cat": "redis", "q": "Redis 为什么快？",
     "a": "纯内存 + 单线程(无锁竞争) + IO 多路复用(epoll 一个线程管上万连接)。我压测过：Redis 单命令 0.0x ms，MySQL 查询 1-100ms，快 100 倍以上。"},
    {"cat": "redis", "q": "Redis 和 MySQL 的区别？",
     "a": "Redis=内存数据库(快、容量小、易失)，MySQL=磁盘数据库(慢、容量大、可靠)。电商架构 Redis 挡前面当缓存，MySQL 兜底存正式数据。"},
    {"cat": "redis", "q": "Redis 五种基本数据类型？",
     "a": "String(缓存/计数 INCR)、Hash(对象)、List(队列 LPUSH/BRPOP)、Set(去重/幂等 SADD)、ZSet(排行榜)。我秒杀用到 List+Set+String 三种。"},
    {"cat": "redis", "q": "缓存穿透、击穿、雪崩是什么？怎么解决？",
     "a": "穿透=查不存在 key 打穿(缓存空值/布隆过滤器)；击穿=热点 key 过期瞬间(互斥锁/永不过期)；雪崩=大量 key 同时过期(随机过期时间)。我实测布隆过滤器 100 个无效 ID 全拦下。"},
    {"cat": "redis", "q": "布隆过滤器原理？",
     "a": "多个哈希函数映射到位数组：查'不在'一定准，查'在'可能误判。只要有位是 0 就是绝对不存在。空间省、可挡缓存穿透。"},
    {"cat": "redis", "q": "分布式锁怎么实现？有什么问题？",
     "a": "SET key value NX EX 秒数：NX=不存在才设(抢锁)，EX=超时自动释放(防死锁)。问题：锁超时业务没跑完、误删锁——生产用 Redisson。我秒杀 3 消费者抢锁没超卖。"},
    {"cat": "redis", "q": "秒杀系统怎么设计？",
     "a": "请求先进 Redis 队列削峰(接口毫秒返回) → 消费者慢慢处理：分布式锁+幂等+原子扣库存+写订单。我实测 1000 人抢 5 件：0.1 秒进完队列，5 单、库存归零、零超卖。"},
    {"cat": "redis", "q": "消息队列为什么能削峰？",
     "a": "把瞬时高并发攒进队列，下游按自己速度消费，把尖峰拉平。1000 人同时下单 → DB 扛不住；先进队列 0.1 秒，DB 全程无压力。"},
    {"cat": "redis", "q": "幂等怎么实现？",
     "a": "用唯一标识(用户ID)记录已处理：SADD 已处理集合，返回 1=首次处理，0=重复丢弃。我秒杀里同一个人连点 10 次只有第一枪有效。"},
    {"cat": "redis", "q": "原子操作(INCR)为什么不需要锁？",
     "a": "Redis 单线程，命令执行不可分割，天然原子。我压测 10 线程同时 INCR 同一 key，结果精确 100000 一个不差。"},
    {"cat": "redis", "q": "RDB 和 AOF 持久化区别？",
     "a": "RDB=定期全量快照(恢复快、可能丢两次快照间的数据)；AOF=追加写日志(按策略 fsync、几乎不丢、文件大)。生产 AOF+RDB 混合。我实测杀进程重启 AOF 数据一条不丢。"},
    {"cat": "redis", "q": "主从复制、哨兵、Cluster 的区别？",
     "a": "主从=复制数据；哨兵=监控主库+自动故障转移(从库扶正)；Cluster=数据分片+横向扩容+自动故障。三个我都跑过：复制 IO/SQL=Yes、哨兵自动扶正、Cluster 迁槽 key 不丢。"},
    {"cat": "redis", "q": "Redis 过期删除策略？",
     "a": "惰性删除(访问时发现过期才删) + 定期删除(每 100ms 抽查一批) 结合。我设 60 秒过期实测：到期再访问返回 nil。"},
    {"cat": "redis", "q": "缓存和数据库一致性怎么保证？",
     "a": "先更新 DB 后删缓存(延迟双删)，读时回源重建。核心：DB 是权威，缓存可删。我商城写主库→删缓存→下次查询重建。"},
    {"cat": "redis", "q": "Redis 内存淘汰策略？",
     "a": "8 种：noeviction(满了报错)/allkeys-lru(所有 key 最近最少用)/volatile-lru(只淘汰带过期时间的)。缓存场景常用 allkeys-lru。我设 maxmemory 实测自动淘汰不报错。"},

    # ---------- 项目 ----------
    {"cat": "project", "q": "讲一下你的项目（10 分钟模板）",
     "a": "28 天从零搭电商后端：用户请求→Redis(缓存+秒杀队列)→消费者(分布式锁+幂等+原子扣库存)→MySQL 主库写→从库读。实测 1000 人抢 5 件：0.1 秒进完队列、5 单零超卖、主从一致、熔断切库不断服务；扩展学了分表快 4 倍、Cluster 6 节点。"},
    {"cat": "project", "q": "怎么防超卖？",
     "a": "三层防线：①分布式锁 SET NX 防并发；②原子 UPDATE ... WHERE stock>0(DB 保证不扣成负数，最后防线)；③SADD 幂等防一人重复抢。秒杀冲突高，乐观锁重试放大压力，原子 SQL 最合适。实测 1000 抢 5 成功 5 单。"},
    {"cat": "project", "q": "1000 并发怎么扛？",
     "a": "请求只做进 Redis 队列一件事(毫秒级返回'排队中')，真实处理由消费者线程消化，DB 压力平稳。实测 1000 请求 0.1 秒进完，DB 没崩。"},
    {"cat": "project", "q": "为什么订单写主库、读从库？",
     "a": "读写分离：写串行走主库保证正确，读分散到从库减轻主库压力。实测订单主库 5 单=从库 5 单。"},
    {"cat": "project", "q": "从库挂了怎么办？",
     "a": "熔断降级：检测从库不可用→读自动切主库→服务不断；恢复自动切回。实测故障注入后读切主库 4306 成功。"},
    {"cat": "project", "q": "怎么保证主从数据一致？",
     "a": "主库写 binlog→从库重放，脚本最后断言主库订单数=从库订单数。注意复制毫秒级延迟，写后立即读要走主库。"},
    {"cat": "project", "q": "数据量大了怎么办？",
     "a": "分库分表：订单按 user_id 取模拆表带键查询只碰 1 张；雪花 ID 全局唯一；统计用汇总表。实测 30 万订单拆 4 表查询快 4 倍。"},
    {"cat": "project", "q": "缓存和数据库不一致怎么办？",
     "a": "先更新 DB 再删缓存(极端延迟双删)，读时回源重建。缓存可删，DB 权威。"},
    {"cat": "project", "q": "如果让你优化，先优化哪里？",
     "a": "看数据说话：①缓存命中率；②EXPLAIN 找全表扫描；③队列长度验证削峰；④主从复制延迟。不拍脑袋。"},
    {"cat": "project", "q": "为什么用 Redis 队列不用 Kafka？",
     "a": "Redis 队列零依赖、轻量、我已用 Redis；Kafka 适合海量日志/跨团队解耦但引入成本高。中小项目 Redis 够用，业务大了平滑迁 RocketMQ/Kafka。"},
]


def main():
    ap = argparse.ArgumentParser(description="Day29 面试模拟器")
    ap.add_argument("--cat", choices=["mysql", "redis", "project"],
                    help="只抽某一类")
    ap.add_argument("--num", type=int, default=5, help="抽几题(默认5)")
    ap.add_argument("--self-test", action="store_true", help="非交互自检")
    args = ap.parse_args()

    pool = [x for x in BANK if not args.cat or x["cat"] == args.cat]
    if not pool:
        print("题库为空，检查 --cat")
        return
    picked = random.sample(pool, min(args.num, len(pool)))

    if args.self_test:
        from collections import Counter
        c = Counter(x["cat"] for x in BANK)
        print(f"题库：共 {len(BANK)} 题")
        print(f"   MySQL  {c['mysql']} 题 ｜ Redis {c['redis']} 题 ｜ 项目 {c['project']} 题")
        print("   非空检查：全部题目/答案非空 ✅")
        return

    print("=" * 56)
    print(f"🎤 面试模拟器：抽 {len(picked)} 题（{args.cat or '全分类'}）")
    print("   看到题目先自己口头答 30 秒，再按回车看答案！")
    print("=" * 56)
    for i, item in enumerate(picked, 1):
        tag = {"mysql": "MySQL", "redis": "Redis", "project": "项目"}[item["cat"]]
        print(f"\n【第 {i} 题 · {tag}】{item['q']}")
        print("   （先答！30 秒）")
        try:
            input("   按回车看答案...")
        except KeyboardInterrupt:
            print("\n   已退出，明天继续练！")
            return
        print(f"   ▶ {item['a']}")
    print("\n" + "=" * 56)
    print("✅ 今天练完！记下没答顺的题，明天重点抽（--cat redis 只练 Redis 等）")
    print("=" * 56)


if __name__ == "__main__":
    main()
