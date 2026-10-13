@echo off
echo === MySQL ===
tasklist /FI "IMAGENAME eq mysqld.exe" 2>nul | findstr /i mysqld >nul && echo MySQL: RUNNING || echo MySQL: NOT RUNNING
echo === Redis (Memurai) ===
sc query Memurai | findstr /i RUNNING >nul && echo Redis: RUNNING || echo Redis: NOT RUNNING
pause
