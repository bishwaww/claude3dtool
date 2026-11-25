@echo off
REM ==========================================================================
REM  Publish a new version:
REM    1. bump the patch version in desktop\package.json (1.0.0 -> 1.0.1)
REM    2. commit, push to main
REM    3. create + push tag vX.Y.Z  -> GitHub Actions builds the .exe and
REM       publishes a GitHub Release; installed apps then offer the update.
REM  Usage: release_update.bat            (patch)
REM         release_update.bat minor      (or major)
REM         release_update.bat 1.0.0      (exact version, e.g. the first release)
REM ==========================================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "BUMP=%~1"
if "%BUMP%"=="" set "BUMP=patch"

for /f %%b in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"
if /i not "%BRANCH%"=="main" (
  echo You are on branch "%BRANCH%". Switch to main first.
  exit /b 1
)

git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
  echo You have uncommitted changes. Commit them first:
  git status --short
  exit /b 1
)

git pull --ff-only origin main || exit /b 1

pushd desktop
call npm version %BUMP% --no-git-tag-version --allow-same-version || (popd & exit /b 1)
for /f "delims=" %%v in ('node -p "require('./package.json').version"') do set "VER=%%v"
popd

echo.
echo Releasing v%VER% ...
git rev-parse -q --verify "refs/tags/v%VER%" >nul && (
  echo Tag v%VER% already exists. Pick a newer version.
  exit /b 1
)
git add desktop\package.json desktop\package-lock.json
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Release v%VER%" || exit /b 1
)
git push origin main || exit /b 1
git tag -a "v%VER%" -m "Stick Knowledge 3D Studio v%VER%" || exit /b 1
git push origin "v%VER%" || exit /b 1

echo.
echo Tag v%VER% pushed. GitHub Actions is now building the installer:
echo   https://github.com/bishwaww/claude3dtool/actions
echo When it finishes, the release appears at:
echo   https://github.com/bishwaww/claude3dtool/releases/tag/v%VER%
echo Installed copies of the studio will show "Update available".
exit /b 0
