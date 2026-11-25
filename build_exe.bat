@echo off
REM ==========================================================================
REM  Build the Windows installer locally:
REM    desktop\dist\StickKnowledge3DStudio-Setup-<version>.exe
REM  Needs: uv (or Python 3.13), Node.js 20+, git. Takes ~5-10 minutes.
REM ==========================================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=backend\.venv\Scripts\python.exe"

echo.
echo [1/5] Python backend environment
if not exist "%PY%" (
  uv venv backend\.venv --python 3.13 || goto :fail
)
uv pip install --python "%PY%" -r backend\requirements.txt "pyinstaller>=6.11" || goto :fail

echo.
echo [2/5] Logo and icons (desktop\assets\logo.png)
"%PY%" scripts\apply_logo.py || goto :fail

echo.
echo [3/5] Studio UI
pushd frontend
call npm ci || (popd & goto :fail)
call npm run build || (popd & goto :fail)
popd

echo.
echo [4/5] Freezing the backend (PyInstaller)
"%PY%" -m PyInstaller --noconfirm --clean --distpath build --workpath build\pyi-work packaging\stick-backend.spec || goto :fail

echo.
echo [5/5] Electron installer (NSIS)
pushd desktop
call npm ci || (popd & goto :fail)
call npm run dist || (popd & goto :fail)
popd

echo.
echo Done. Installer:
dir /b desktop\dist\*.exe
exit /b 0

:fail
echo.
echo BUILD FAILED (see the messages above).
exit /b 1
