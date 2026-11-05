@echo off
chcp 65001 >nul
title Antigravity License Server
cd /d "%~dp0"
echo ===================================================
echo     🚀 ЗАПУСК СЕРВЕРА ЛИЦЕНЗИЙ ANTIGRAVITY
echo ===================================================
echo.
echo Сервер доступен по адресу: http://127.0.0.1:5000
echo Пароль от админки: admin123
echo.
python app.py
pause
