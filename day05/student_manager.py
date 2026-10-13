# -*- coding: utf-8 -*-
"""
学生管理系统（Day 5 实战项目）
================================
把你学的全用上：
  - 参数化查询（防 SQL 注入）      -> Day 2
  - 多表 JOIN（学生 + 班级）       -> Day 3
  - 聚合统计（GROUP BY + COUNT）   -> Day 4
  - 增删改查 + 提交事务（commit）  -> Day 1

运行前提：MySQL 已启动（先双击 start_mysql.bat）
运行方式：python student_manager.py
"""

import pymysql

# ---------- 连接数据库 ----------
def connect():
    return pymysql.connect(
        host="127.0.0.1",          # 本机
        user="root",
        password="root123",
        database="my_first_db",
        charset="utf8mb4"
    )


# ---------- 功能 1：查看所有学生（JOIN 班级名） ----------
def show_all(conn):
    cur = conn.cursor()
    sql = """
        SELECT student3.id, student3.name, student3.age, class.name
        FROM student3
        JOIN class ON student3.class_id = class.id
        ORDER BY student3.id
    """
    cur.execute(sql)
    rows = cur.fetchall()
    print("\n===== 全部学生名单 =====")
    if not rows:
        print("（暂无学生）")
        return
    print(f"{'编号':<6}{'姓名':<10}{'年龄':<8}{'班级'}")
    print("-" * 34)
    for r in rows:
        print(f"{r[0]:<6}{r[1]:<10}{r[2]:<8}{r[3]}")
    print(f"共 {len(rows)} 人\n")


# ---------- 功能 2：添加学生（参数化 INSERT，防注入） ----------
def add_student(conn):
    name = input("请输入姓名：").strip()
    if not name:
        print("姓名不能为空！")
        return
    age = input("请输入年龄：").strip()
    class_id = input("请输入班级编号（1=软件1班，2=软件2班）：").strip()

    cur = conn.cursor()
    try:
        # 参数化写法：占位符 %s，值单独传——防 SQL 注入的关键
        cur.execute(
            "INSERT INTO student3 (name, age, class_id) VALUES (%s, %s, %s)",
            (name, int(age), int(class_id))
        )
        conn.commit()   # 写入必须提交，否则不生效
        print(f"✅ 添加成功！新学生编号是 {cur.lastrowid}")
    except pymysql.err.IntegrityError:
        # 外键错误：班级号不存在 / 约束错误
        print("❌ 添加失败：班级编号不存在或数据不合法（试试 1 或 2）")
    except ValueError:
        print("❌ 添加失败：年龄和班级必须是数字")


# ---------- 功能 3：按姓名搜索（WHERE 参数化） ----------
def find_student(conn):
    name = input("请输入要搜索的姓名：").strip()
    cur = conn.cursor()
    cur.execute("SELECT id, name, age FROM student3 WHERE name = %s", (name,))
    rows = cur.fetchall()
    if not rows:
        print(f"❌ 没找到叫「{name}」的学生")
        return
    for r in rows:
        print(f"✅ 找到：编号 {r[0]}，姓名 {r[1]}，年龄 {r[2]}")


# ---------- 功能 4：修改年龄（UPDATE） ----------
def update_age(conn):
    name = input("请输入要改年龄的学生姓名：").strip()
    new_age = input("请输入新年龄：").strip()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE student3 SET age = %s WHERE name = %s",
            (int(new_age), name)
        )
        conn.commit()
        if cur.rowcount == 0:
            print("❌ 没找到这个人，或者年龄没变化")
        else:
            print(f"✅ 已把「{name}」的年龄改为 {new_age}")
    except ValueError:
        print("❌ 年龄必须是数字")


# ---------- 功能 5：删除学生（DELETE） ----------
def delete_student(conn):
    name = input("请输入要删除的学生姓名：").strip()
    cur = conn.cursor()
    cur.execute("DELETE FROM student3 WHERE name = %s", (name,))
    conn.commit()
    if cur.rowcount == 0:
        print(f"❌ 没找到叫「{name}」的学生")
    else:
        print(f"✅ 已删除「{name}」（共 {cur.rowcount} 条）")


# ---------- 功能 6：班级统计（GROUP BY 聚合） ----------
def class_stats(conn):
    cur = conn.cursor()
    sql = """
        SELECT class.name, COUNT(student3.id) AS 人数, AVG(student3.age) AS 平均年龄
        FROM student3
        JOIN class ON student3.class_id = class.id
        GROUP BY class.id
    """
    cur.execute(sql)
    rows = cur.fetchall()
    print("\n===== 班级统计 =====")
    if not rows:
        print("（还没有学生数据）")
        return
    print(f"{'班级':<12}{'人数':<8}{'平均年龄'}")
    print("-" * 30)
    for r in rows:
        print(f"{r[0]:<12}{r[1]:<8}{r[2]:.1f}")
    print()


# ---------- 主菜单 ----------
def main():
    print("=" * 40)
    print("   🎓 学生管理系统 v1.0")
    print("=" * 40)
    try:
        conn = connect()
        print("✅ 数据库连接成功！\n")
    except Exception as e:
        print(f"❌ 连不上数据库：{e}")
        print("请先双击 start_mysql.bat 启动 MySQL 再运行本程序")
        return

    while True:
        print("请选择功能：")
        print("  1. 查看所有学生")
        print("  2. 添加学生")
        print("  3. 按姓名搜索")
        print("  4. 修改年龄")
        print("  5. 删除学生")
        print("  6. 班级统计")
        print("  7. 退出")
        choice = input(">>> 输入数字：").strip()

        if choice == "1":
            show_all(conn)
        elif choice == "2":
            add_student(conn)
        elif choice == "3":
            find_student(conn)
        elif choice == "4":
            update_age(conn)
        elif choice == "5":
            delete_student(conn)
        elif choice == "6":
            class_stats(conn)
        elif choice == "7":
            print("👋 拜拜，数据都保存好了！")
            conn.close()
            break
        else:
            print("❌ 无效选择，请输入 1-7\n")


if __name__ == "__main__":
    main()
