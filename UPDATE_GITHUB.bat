@echo off
setlocal EnableExtensions
cd /d "E:\Refind"

title ReFind - GitHub Auto Update
color 0B

echo.
echo ========================================================
echo              REFIND - GITHUB AUTO UPDATE
echo ========================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git is not installed or not available in PATH.
    pause
    exit /b 1
)

if not exist ".git" (
    echo [ERROR] E:\Refind is not a Git repository.
    pause
    exit /b 1
)

git remote set-url origin https://github.com/abhishek027aks/ReFind.git

echo [1/4] Adding all changes...
git add -A
if errorlevel 1 goto :error

git diff --cached --quiet
if errorlevel 1 (
    echo [INFO] Changes detected. Creating commit...
    git commit -m "update: ReFind project"
    if errorlevel 1 goto :error
) else (
    echo [INFO] No local changes found.
)

echo.
echo [2/4] Syncing with GitHub...
git pull --rebase origin main
if errorlevel 1 goto :error

echo.
echo [3/4] Pushing to GitHub...
git push -u origin main
if errorlevel 1 goto :pusherror

echo.
echo ========================================================
echo          SUCCESS - REFIND IS UP TO DATE
echo ========================================================
echo.
echo Repository:
echo https://github.com/abhishek027aks/ReFind
echo.
pause
exit /b 0

:error
echo.
echo ========================================================
echo                 UPDATE FAILED
echo ========================================================
echo.
pause
exit /b 1

:pusherror
echo.
echo ========================================================
echo                  PUSH FAILED
echo ========================================================
echo.
echo Check GitHub authentication.
echo.
pause
exit /b 1
