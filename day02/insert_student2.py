# Day2：用 Python 往正规表 student2 插入数据（含防注入的参数化写法）

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

# 让程序问用户要数据（交互式）
name = input('学生姓名: ')
age = int(input('年龄: '))
email = input('邮箱（可不填，直接回车）: ')

# 关键知识点：参数化（Parameterized SQL）
# %s 是"占位符"，真实值放在后面的括号里
# 好处：数据里就算有坏字符（比如 ' 或恶意 SQL），数据库也只会当它是"值"，不会当它是"命令"
# 这叫防 SQL 注入 —— 后端开发最重要的安全习惯之一
cursor.execute(
    "INSERT INTO student2 (name, age, email) VALUES (%s, %s, %s)",
    (name, age, email if email else None)
)

# 写数据必须提交
conn.commit()
print('插入成功！')

# 查看当前全部数据
cursor.execute('SELECT * FROM student2')
for row in cursor.fetchall():
    print(row)

cursor.close()
conn.close()
print('完成！')
