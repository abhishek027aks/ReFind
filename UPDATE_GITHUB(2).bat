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
    echo Install Git for Windows, then run this file again.
    pause
    exit /b 1
)

if not exist ".git" (
    echo [ERROR] This folder is not a Git repository.
    echo Expected project folder: E:\Refind
    pause
    exit /b 1
)

echo [1/4] Checking GitHub connection...
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [INFO] GitHub remote is missing. Adding ReFind remote...
    git remote add origin https://github.com/abhishek027aks/ReFind.git
    if errorlevel 1 goto :error
) else (
    git remote set-url origin https://github.com/abhishek027aks/ReFind.git
    if errorlevel 1 goto :error
)

echo.
echo [2/4] Adding all ReFind changes...
git add -A
if errorlevel 1 goto :error

git diff --cached --quiet
if errorlevel 1 (
    git commit -m "update: ReFind project"
    if errorlevel 1 goto :error
) else (
    echo [INFO] No local changes found.
)

echo.
echo [3/4] Syncing with GitHub...
git pull --rebase origin main
if errorlevel 1 (
    echo.
    echo [WARNING] GitHub changes could not be rebased automatically.
    echo Resolve the conflict manually, then run this file again.
    pause
    exit /b 1
)

echo.
echo [4/4] Pushing to GitHub...
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
echo You can close this window.
echo.
pause
exit /b 0

:error
echo.
echo ========================================================
echo                 UPDATE FAILED
echo ========================================================
echo.
echo Check the error message above and try again.
echo.
pause
exit /b 1

:pusherror
echo.
echo ========================================================
echo                  PUSH FAILED
echo ========================================================
echo.
echo Most common reason: GitHub authentication is not set up.
echo Sign in through Git Credential Manager / GitHub CLI,
echo then run this file again.
echo.
pause
exit /b 1
