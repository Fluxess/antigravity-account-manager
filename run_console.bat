@echo off
chcp 65001 >nul
title Antigravity Account Manager (Debug Console)
cd /d "%~dp0"
python app.py
pause
