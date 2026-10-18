# 第一个连接 MySQL 的 Python 程序
# 作用：连上 my_first_db，把 student 表里的数据读出来

import pymysql

# 第 1 步：连接数据库（相当于拿钥匙开门）
conn = pymysql.connect(
    host="127.0.0.1", port=4306,      # MySQL 在哪：本机
    user='root',           # 账号
    password='root123',    # 密码
    database='my_first_db', # 进哪个库
    charset='utf8mb4'      # 用 UTF-8 编码（中文不乱码）
)

# 第 2 步：创建游标（相当于一个"跑腿的"，帮你把命令递进去）
cursor = conn.cursor()

# 第 3 步：执行 SQL（和你在命令行敲的一模一样）
cursor.execute('SELECT * FROM student')

# 第 4 步：把结果取回来
rows = cursor.fetchall()

# 第 5 步：打印每一行
print('数据库里的学生：')
for row in rows:
    print(row)

# 第 6 步：收尾（关掉游标和连接，好习惯）
cursor.close()
conn.close()
print('完成！')
