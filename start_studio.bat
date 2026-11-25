@echo off
REM Start Stick Knowledge 3D Studio from the source checkout as a desktop app.
REM (Installed users just open "Stick Knowledge 3D Studio" from the Start menu.)
setlocal
cd /d "%~dp0"
if not exist frontend\dist\index.html (
  echo Building the studio UI once...
  pushd frontend & call npm ci & call npm run build & popd
)
if not exist desktop\node_modules\electron\dist\electron.exe (
  echo Installing the desktop shell once...
  pushd desktop & call npm ci & popd
)
start "" desktop\node_modules\electron\dist\electron.exe desktop
