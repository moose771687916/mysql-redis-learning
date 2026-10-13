@echo off
start "MySQL Server" /min "D:\RediAndMySQL\mysql\bin\mysqld.exe" --defaults-file=D:\RediAndMySQL\mysql\my.ini
echo MySQL started in background.
echo Test: mysql -u root -proot123 -e "SELECT 1"
