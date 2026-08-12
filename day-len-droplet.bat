@echo off
REM ===========================================================
REM  Day code len droplet roi khoi dong lai bot.
REM  Chay tren MAY WINDOWS (khong phai tren droplet).
REM
REM  Lan dau dung: sua dong SET IP= ben duoi thanh IP droplet cua ban.
REM ===========================================================

chcp 65001 >nul
cd /d "%~dp0"

REM >>> SUA DONG NAY: dien IP droplet <<<
set "IP="

if "%IP%"=="" (
    set /p IP="Nhap IP droplet (vd 165.22.10.20): "
)
if "%IP%"=="" (
    echo  [LOI] Chua co IP.
    pause
    exit /b 1
)

echo.
echo  Dang day code len %IP% ...
echo  ---------------------------------------------------------

REM Chi day ma nguon. KHONG day:
REM   tessdata\  - tren droplet da co goi vie cai bang apt
REM   .venv\     - moi truong ao cua Windows, khong dung duoc tren Linux
REM   .env       - chua token, tao tay tren droplet mot lan
REM   antispam.db- du lieu song tren droplet, day len se de len mat het
scp -r antispam_bot requirements.txt root@%IP%:/opt/antispam/app/
if errorlevel 1 (
    echo.
    echo  [LOI] Day code that bai. Kiem tra IP va ket noi SSH.
    echo.
    pause
    exit /b 1
)

echo.
echo  Dang cai thu vien va khoi dong lai...
ssh root@%IP% "cd /opt/antispam/app && /opt/antispam/venv/bin/pip install -q -r requirements.txt && chown -R antispam:antispam /opt/antispam/app && systemctl restart antispam && sleep 2 && systemctl is-active antispam"

echo.
echo  ---------------------------------------------------------
echo  Xong. Xem log truc tiep bang lenh:
echo     ssh root@%IP% "journalctl -u antispam -f"
echo.
pause
