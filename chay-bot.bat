@echo off
REM ===========================================================
REM  Bat bot: bam dup vao file nay.
REM  Tat bot : bam Shift+F (Ctrl+C khong dung vi trung phim copy).
REM
REM  Dat mat khau mo bot:
REM     .venv\Scripts\python.exe -m antispam_bot --dat-mat-khau
REM
REM  Lan chay dau tien se tu tao moi truong rieng (.venv) va cai
REM  thu vien - mat vai phut. Cac lan sau khoi dong ngay.
REM ===========================================================

chcp 65001 >nul
cd /d "%~dp0"
title Bot chong spam Telegram - dong cua so nay la tat bot

if not exist ".env" (
    echo.
    echo  [LOI] Khong thay file .env
    echo  Copy .env.example thanh .env roi dien BOT_TOKEN.
    echo.
    pause
    exit /b 1
)

REM Dung moi truong rieng trong thu muc nay. Khong dung "python" tran vi
REM may co the co nhieu ban Python, va ban tren PATH thuong thieu thu vien.
set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo.
    echo  Lan dau chay - dang tao moi truong rieng...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist "%PY%" (
        echo.
        echo  [LOI] Khong tao duoc .venv. Cai Python tu python.org roi thu lai.
        echo.
        pause
        exit /b 1
    )
    echo  Dang cai thu vien, doi mot chut...
    "%PY%" -m pip install --upgrade pip -q
    "%PY%" -m pip install -r requirements.txt -q
    if errorlevel 1 (
        echo.
        echo  [LOI] Cai thu vien that bai. Xem thong bao ben tren.
        echo.
        pause
        exit /b 1
    )
    echo  Xong.
)

echo.
echo  Dang khoi dong bot...
echo  ---------------------------------------------------------
echo.

"%PY%" -m antispam_bot

echo.
echo  ---------------------------------------------------------
echo  Bot da dung.
echo.
pause
