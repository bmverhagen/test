@echo off
cd /d "%~dp0"
echo.
echo  Eneco Heat Dashboard starten...
echo.

where node >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  Node.js niet gevonden!
    echo  Download: https://nodejs.org  ^(kies LTS^)
    pause
    exit /b 1
)

call npm install
if %ERRORLEVEL% NEQ 0 (
    echo  npm install mislukt
    pause
    exit /b 1
)

echo.
echo  Browser opent op http://localhost:5173/
echo  Stoppen met Ctrl+C
echo.
call npm run dev
pause
