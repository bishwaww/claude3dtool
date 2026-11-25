@echo off
title Stick Knowledge 3D Studio Launcher
echo ====================================================
echo   Stick Knowledge 3D Studio - Starting Services
echo ====================================================
start "Stick Knowledge Backend (8420)" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8420"
timeout /t 2 /nobreak >nul
start "Stick Knowledge Frontend (5173)" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"
timeout /t 3 /nobreak >nul
start http://localhost:5173
echo Studio launched at http://localhost:5173
