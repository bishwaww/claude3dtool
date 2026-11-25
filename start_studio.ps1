$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Starting Stick Knowledge 3D Studio..." -ForegroundColor Cyan

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Root\backend'; & '.\.venv\Scripts\python.exe' -m uvicorn main:app --host 127.0.0.1 --port 8420"
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Root\frontend'; npm.cmd run dev"
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"

Write-Host "Backend API: http://127.0.0.1:8420" -ForegroundColor Green
Write-Host "Studio UI:   http://localhost:5173" -ForegroundColor Green
