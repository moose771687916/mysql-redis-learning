# -*- coding: utf-8 -*-
"""
Redis 事务 MULTI/EXEC 演示（Day 15）
====================================
场景：转账 30 元（tom → jerry），对比 MySQL 事务

关键区别：
  MySQL 事务 = 一组操作要么全成、要么全回滚（Day 7 学过）
  Redis 事务 = 命令打包一起执行，但【没有回滚】——
              中途某条出错，其他命令照样执行！

运行：python redis_tx_demo.py
前提：Redis（Memurai）已启动
"""

import redis

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# ===== 场景：tom 有 100 元，jerry 有 50 元，tom 转 30 给 jerry =====
print("=" * 50)
print("演示 1：正常转账（MULTI 打包）")
print("=" * 50)
r.set("money:tom", 100)
r.set("money:jerry", 50)
print(f"转账前：tom={r.get('money:tom')} 元，jerry={r.get('money:jerry')} 元")

pipe = r.pipeline()          # 开一张"打包单"（MULTI）
pipe.multi()                 # 开始打包
pipe.set("money:tom", 70)    # tom 扣 30
pipe.set("money:jerry", 80)  # jerry 加 30
pipe.execute()               # EXEC 一口气执行
print(f"转账后：tom={r.get('money:tom')} 元，jerry={r.get('money:jerry')} 元")
print("✅ 两个账户一起变了，中间没人插队")

# ===== 演示 2：Redis 事务【没有回滚】！ =====
print()
print("=" * 50)
print("演示 2：故意让一条命令出错——其他命令照样执行！")
print("=" * 50)
r.set("counter", "abc")      # 存一个字符串（数字计数器的位置）
print("先把 counter 存成字符串 'abc'（不是数字）")

pipe = r.pipeline()
pipe.multi()
pipe.incr("counter")         # 对字符串做 +1 → 会报错（运行时错误）
pipe.set("money:tom", 66)    # 这条命令跟在上一条后面
try:
    pipe.execute()
    print("？？居然没报错")
except redis.ResponseError as e:
    print(f"incr 报错了：{e}")

print(f"money:tom 现在的值：{r.get('money:tom')}  ← 是 66！")
print("⚠️ 看到了吗：Redis 事务里，出错的那条报错，")
print("   但后面的命令【照样执行】了——没有回滚！")
print()
print("对比 MySQL（Day 7）：create_order 里扣库存失败，")
print("   订单+明细+库存【全部回滚】——MySQL 有回滚，Redis 没有！")
print()
print("这就是为什么：Redis 事务适合『打包执行』，")
print("不适合『必须全成或全撤』的强一致场景（那种交给 MySQL）")

# 清理
r.delete("money:tom", "money:jerry", "counter")
print()
print("🗑️ 临时数据已清理")
