@echo off
chcp 65001 >nul
title Antigravity Account Manager
cd /d "%~dp0"

echo Запуск Antigravity Account Manager...
start "" pythonw app.py
if %ERRORLEVEL% NEQ 0 (
    echo Pythonw не сработал, пробуем стандартный python...
    python app.py
)
