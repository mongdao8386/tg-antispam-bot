@echo off
REM ===========================================================
REM  CHUYEN BOT SANG VPS - chay MOT LAN tren may Windows nay.
REM
REM  Lam gi:
REM    1. SSH vao VPS, chay script cai dat (lay code tu GitHub, dung
REM       dich vu systemd, bat tu cap nhat).
REM    2. Day .env va antispam.db tu may nay len VPS.
REM    3. Bat bot tren VPS va kiem tra.
REM
REM  TRUOC KHI CHAY: TAT bot dang chay tren may nay (bam F4).
REM  Telegram chi cho MOT tien trinh nhan tin; hai bot cung token
REM  la giat tin cua nhau, ca hai deu loi.
REM ===========================================================

chcp 65001 >nul
cd /d "%~dp0"
title Chuyen bot sang VPS

set "IP=187.53.132.36"
set "APP=/opt/antispam/app"

if not exist ".env" (
    echo  [LOI] Khong thay .env o day.
    pause
    exit /b 1
)
if not exist "antispam.db" (
    echo  [LOI] Khong thay antispam.db o day.
    pause
    exit /b 1
)

echo.
echo  VPS: %IP%
echo.
echo  Bot tren may nay DA TAT chua? (bam F4 trong cua so bot)
set /p OK="  Go 'y' de tiep tuc: "
if /i not "%OK%"=="y" exit /b 0

echo.
echo  [1/3] Cai dat tren VPS (mat 2-4 phut)...
echo  ---------------------------------------------------------
ssh root@%IP% "curl -fsSL https://raw.githubusercontent.com/mongdao8386/tg-antispam-bot/main/deploy/cai-dat-lan-dau.sh | bash"
if errorlevel 1 (
    echo.
    echo  [LOI] Cai dat that bai. Xem thong bao ben tren.
    pause
    exit /b 1
)

echo.
echo  [2/3] Day .env va antispam.db len...
scp .env antispam.db root@%IP%:%APP%/
if errorlevel 1 (
    echo  [LOI] Day file that bai.
    pause
    exit /b 1
)

echo.
echo  [3/3] Bat bot tren VPS...
ssh root@%IP% "chown -R antispam:antispam %APP% && chmod 600 %APP%/.env && systemctl enable --now antispam && sleep 4 && systemctl is-active antispam && journalctl -u antispam -n 15 --no-pager"

echo.
echo  ---------------------------------------------------------
echo  Xong. Tu gio:
echo    - Xem log     : ssh root@%IP% "journalctl -u antispam -f"
echo    - Dieu khien  : ssh root@%IP% "cd %APP% && /opt/antispam/venv/bin/python -m antispam_bot.cli"
echo    - Cap nhat    : chi can git push, VPS tu lay code moi trong 2 phut
echo    - Lay DB ve   : scp root@%IP%:%APP%/antispam.db .
echo.
echo  Dung bat lai bot tren may nay nua.
echo.
pause
