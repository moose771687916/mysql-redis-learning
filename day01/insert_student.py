# 第二个连接 MySQL 的 Python 程序
# 作用：往 student 表里插入一个新学生

import pymysql

# 连接数据库
conn = pymysql.connect(
    host='127.0.0.1',
    user='root',
    password='root123',
    database='my_first_db',
    charset='utf8mb4'
)

cursor = conn.cursor()

# 插入一个新学生：学号 3，名字 小刚，年龄 18
cursor.execute(
    "INSERT INTO student (id, name, age) VALUES (3, '小刚', 18)"
)

# ⚠️ 关键一步：提交（commit）
# MySQL 有个"事务"机制：你改了数据，要先"确认"才算数
# 不 commit，数据只是"草稿"，其他人和程序都看不到，程序退出就丢了
conn.commit()

print('插入成功！去 MySQL 里 SELECT 一下看看吧')

cursor.close()
conn.close()
