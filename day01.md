# Day 1・MySQL + Python 入门实战报告

> 日期：2026-10-09（周四）・学习者：从零起步的编程新手（有 Python 基础、无后端经验）
> 目标：完成 MySQL 安装，亲手完成 "建库→建表→增删改查"，并让 Python 程序连接数据库完成读写。



***

## 一、今日成果（一句话）

**从一个数据库都没碰过的新手，到用 Python 程序往 MySQL 里成功存入数据 —— 后端的第一扇门打开了。**



***

## 二、环境现状（已全部就绪）



| 组件     | 版本 / 方式                      | 连接信息                            | 备注                      |
| ------ | ---------------------------- | ------------------------------- | ----------------------- |
| MySQL  | 8.0.29（Windows 免安装版）         | `127.0.0.1:3306`，root / root123 | 放 D:\RediAndMySQL\mysql |
| Redis  | Memurai 4.1.2（官方 Windows 原生） | `localhost:6379`，无密码            | 开机自启，兼容 Redis 7.2/8 API |
| Python | 3.13 + pymysql               | —                               | 已通过 pip 安装              |

**日常操作**：双击 `start_mysql.bat` 启动 MySQL（Redis 不用管，自动在跑）；双击 `check_status.bat` 看状态。



***

## 三、今天学到的核心概念



1. **服务端 vs 客户端**：`start_mysql.bat` 是 "开后厨"（启动数据库服务 mysqld，常驻后台）；`mysql -uroot -proot123` 是 "进店点菜"（客户端登录发命令）。两个都要，时机不同。

2. **磁盘数据库 vs 内存数据库**：MySQL 数据常驻硬盘，断电不丢，管 "不能丢的账本"；Redis 数据主要放内存，超快，管 "要快的临时数据"（缓存 / 验证码 / 排行榜）。配合使用，不是二选一。

3. **命令行参数**：`mysql -u root -p root123` = 程序名 + 选项（`-u`用户、`-p`密码）+ 值。`-uroot` 与 `-u root` 等价。

4. **分号是句号**：SQL 每条命令必须以 `;` 结尾，否则 MySQL 一直等（显示 `->`）。忘了就用 `\c` 取消重来。

5. **事务与 commit**：读（SELECT）不用盖章；写（INSERT/UPDATE/DELETE）必须 `conn.commit()`，否则数据只是 "草稿"。

6. **WHERE 是保护伞**：改和删必须带条件（`WHERE id=1`），否则会动到全表，谁都救不回来。



***

## 四、今日实操全记录（照着可复现）

### 4.1 手工 SQL 流程



```
-- 1. 连接（终端执行）
mysql -uroot -proot123

-- 2. 查看系统库
SHOW DATABASES;

-- 3. 建库
CREATE DATABASE my_first_db;

-- 4. 进入库
USE my_first_db;

-- 5. 建表（3 列：学号、姓名、年龄）
CREATE TABLE student (
  id INT,
  name VARCHAR(50),
  age INT
);

-- 6. 增（插入）
INSERT INTO student VALUES (1, '小明', 18);
INSERT INTO student VALUES (2, '小红', 17), (3, '小刚', 19);

-- 7. 查（全查 / 条件查）
SELECT * FROM student;
SELECT * FROM student WHERE id = 1;

-- 8. 改
UPDATE student SET age = 19 WHERE id = 1;

-- 9. 删
DELETE FROM student WHERE id = 3;

-- 10. 退出
exit
```

### 4.2 当前数据库状态（今晚定格）



| id | name | age               |
| -- | ---- | ----------------- |
| 1  | 小明   | 19                |
| 2  | 小红   | 17                |
| 3  | 小刚   | 18 ← Python 程序插入的 |

### 4.3 Python 读写脚本（已存 D:\RediAndMySQL\）



* `my_first_query.py`：连接 → 执行 SELECT → fetchall 打印 → 关闭。

* `insert_student.py`：连接 → 执行 INSERT → **commit()** → 关闭。

运行方式：`python D:\RediAndMySQL\my_first_query.py`



***

## 五、命令速查表（以后天天用）



| 想干什么       | 命令                                          |
| ---------- | ------------------------------------------- |
| 连接 MySQL   | `mysql -uroot -proot123`                    |
| 看所有库       | `SHOW DATABASES;`                           |
| 建库         | `CREATE DATABASE 库名;`                       |
| 进库         | `USE 库名;`                                   |
| 看库里的表      | `SHOW TABLES;`                              |
| 建表         | `CREATE TABLE 表名 (列名 类型, ...);`             |
| 插入         | `INSERT INTO 表名 VALUES (值, ...);`           |
| 全查         | `SELECT * FROM 表名;`                         |
| 条件查        | `SELECT * FROM 表名 WHERE 条件;`                |
| 改          | `UPDATE 表名 SET 列=新值 WHERE 条件;`              |
| 删          | `DELETE FROM 表名 WHERE 条件;`                  |
| 取消当前输入     | `\c`                                        |
| 退出         | `exit`                                      |
| Python 读   | `cursor.execute(...)` + `cursor.fetchall()` |
| Python 写   | `cursor.execute(...)` + `conn.commit()`     |
| 装 Python 库 | `python -m pip install 包名 -i 清华源`           |



***

## 六、今日踩坑记录（价值最高的一节）



1. `mysql`**&#x20;命令找不到** → 免安装版没加入 PATH，已把 `D:\RediAndMySQL\mysql\bin` 写入用户 PATH，重开终端生效。

2. **命令没加分号** → 一直显示 `->`（MySQL 在等你说完），用 `\c` 取消后重新输入。

3. `mysql`**&#x20;不带账号** → MySQL 用 Windows 默认用户名（ODBC）登录被拒，报 `Access denied`。必须带 `-uroot -proot123`。

4. `ModuleNotFoundError: pymysql` → 电脑里有多个 Python：豆包环境的 Python 有 pymysql，桌面终端的 Python 没有。解决：在自己的终端跑 `python -m pip install pymysql -i https://pypi.tuna.tsinghua.edu.cn/simple`。

5. **教训**：Windows 多 Python 并存很常见，以后装包永远用 `python -m pip install 包名`，确保装进当前环境。



***

## 七、下一步（Day 2 预告）



1. **主键**：给表装 "身份证"（id 不能重复、不能为空）—— 现在这张表还很粗糙。

2. **约束与数据类型**：年龄不能为负、日期 / 小数怎么存。

3. **Python 学生管理系统小项目**：加人、查人、改年龄、删除，把今天学的全串起来。

4. **Redis 入门**：`SET` / `GET` / `EXPIRE` 三个命令，理解 "缓存"。



***

## 八、给未来的自己



* 改和删，**永远先想清楚 WHERE 圈住谁**。

* 写数据**必须 commit**。

* 数据库是 "常驻员工"：云服务器上的 MySQL 开机自启、7×24 工作，没人每天开关。

* 环境、命令、概念都在这份报告里，忘了就回来翻。