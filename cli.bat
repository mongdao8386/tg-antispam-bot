@echo off
REM ===========================================================
REM  Dieu khien bot ngay tren terminal - khong can mo .env,
REM  khong can khoi dong lai bot. Bam dup de mo menu tuong tac.
REM
REM  Hoac goi voi tham so:
REM     cli.bat list                trang thai moi cong tac
REM     cli.bat on captcha          bat mot cong tac
REM     cli.bat off scan_ocr        tat mot cong tac
REM     cli.bat starters            ai da bam Start (kem ID de copy)
REM     cli.bat seeding all         them MOI acc da bam Start lam seeding
REM     cli.bat seeding add 123 456
REM     cli.bat pause 30 / resume / action report
REM ===========================================================

chcp 65001 >nul
cd /d "%~dp0"
title Dieu khien bot chong spam

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo  [LOI] Chua co .venv - chay chay-bot.bat mot lan truoc.
    pause
    exit /b 1
)

"%PY%" -m antispam_bot.cli %*

if "%~1"=="" pause
