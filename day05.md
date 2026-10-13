# Day 5 · 第一个实战项目：学生管理系统

> 日期：2026-10-11 · 主题：用 Python 写一个完整可用的命令行管理系统
> 前置：Day 1-4 已掌握 MySQL 增删改查、建表规范、多表 JOIN、聚合统计

---

## 一、今日成果（一句话）

**独立完成第一个"能交货"的作品——命令行学生管理系统（student_manager.py），7 个功能全部实测通过，把四天学的 SQL 能力全串进了真实程序。**

---

## 二、项目结构（三个部分）

| 部分 | 代码 | 作用 |
|---|---|---|
| 连接函数 | `connect()` | 用 pymysql 连 MySQL（127.0.0.1 / root / root123 / my_first_db） |
| 功能函数 | `show_all` `add_student` `find_student` `update_age` `delete_student` `class_stats` | 每个菜单项一个函数 |
| 主循环 | `main()` 的 while True | 打印菜单 → 读输入 → 调对应函数 → 回到菜单 |

---

## 三、每个功能对应的"知识点账单"

| 菜单功能 | 用到的 SQL / 知识 |
|---|---|
| 1. 查看所有学生 | **JOIN** 班级名（Day 3）+ ORDER BY 排序 |
| 2. 添加学生 | **参数化 %s** 防 SQL 注入（Day 2）+ commit 提交（Day 1）+ 外键报错捕获（Day 3） |
| 3. 按姓名搜索 | WHERE + 参数化 |
| 4. 修改年龄 | UPDATE |
| 5. 删除学生 | DELETE + rowcount 判断 |
| 6. 班级统计 | **GROUP BY + COUNT + AVG**（Day 4） |
| 7. 退出 | 关闭连接 |

---

## 四、关键代码记忆点

```python
# 参数化 = 防注入的关键（值单独传，不拼进 SQL 字符串）
cur.execute("INSERT INTO student3 (name, age, class_id) VALUES (%s, %s, %s)",
            (name, int(age), int(class_id)))
conn.commit()          # 写操作必须提交，否则不生效

# 外键报错要"温柔处理"（班级号不存在时）
except pymysql.err.IntegrityError:
    print("❌ 添加失败：班级编号不存在或数据不合法")

# 聚合统计：分堆 + 每堆算一次
SELECT class.name, COUNT(student3.id), AVG(student3.age)
FROM student3 JOIN class ON student3.class_id = class.id
GROUP BY class.id
```

---

## 五、实测验证记录（AI 代跑全流程）

```
✅ 数据库连接成功
✅ 查看全部学生（3 人，带班级名）
✅ 添加 tester（编号 5）→ 列表出现
✅ 搜索 tester → 找到
✅ 删除 tester → 列表恢复 3 人
📊 班级统计：软件1班 2 人 平均 18.0 岁 / 软件2班 1 人 平均 16.0 岁
✅ 退出
```

用户实测体验：添加"春风、班级 3"被外键温柔拒绝（班级 3 不存在）——**程序正确守门**。

---

## 六、运行方式

```
python D:\RediAndMySQL\student_manager.py
```
（前提：MySQL 已启动，双击 start_mysql.bat）

---

## 七、下一步（Day 7 起：电商系统）

学生管理系统是"单机版练习"；下一步**升级为电商系统**（用户/商品/购物车/订单/订单明细五张表 + 事务下单 + Redis 缓存 + API 接口），向"商业落地"级项目进发。

---

## 八、给未来的自己

- 一个系统 = 连接 + 功能函数 + 主循环，这是所有管理系统的骨架。
- 参数化不是选项，是底线（防 SQL 注入）。
- 外键报错不是 bug，是数据库在保护数据——程序要学会"温柔地转告用户"。
