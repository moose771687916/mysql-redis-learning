@echo off
chcp 65001 >nul
REM Day 31：一键启动 Docker 版终极商城
echo ============================================
echo  Day 31  Docker 版终极商城 - 一键启动
echo ============================================

REM 1. 构建 + 启动 4 个容器（首次会拉镜像，需要几分钟）
docker compose up -d --build
if errorlevel 1 (
    echo [失败] compose 启动出错，看上面的日志
    pause
    exit /b 1
)

REM 2. 等 app 就绪（最多 60 秒）
echo.
echo 等待商城 API 就绪...
set /a cnt=0
:wait
curl -s -o nul http://localhost:5001/api/stats
if not errorlevel 1 goto ready
set /a cnt+=1
if %cnt% geq 30 (
    echo [超时] 60 秒 API 还没起来，执行 docker compose logs app 看日志
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait

:ready
echo.
echo ============================================
echo  ✅ 商城已上线！
echo  API 地址:      http://localhost:5001
echo  商品详情:      GET  http://localhost:5001/api/product/1
echo  秒杀下单:      POST http://localhost:5001/api/seckill  {"uid":1001}
echo  状态查询:      GET  http://localhost:5001/api/stats
echo  容器列表:      docker ps
echo  主库直连:      127.0.0.1:4308  root/root123
echo  从库直连:      127.0.0.1:4309  root/root123
echo  压测验收:      python day31\test_shop.py
echo ============================================
pause
