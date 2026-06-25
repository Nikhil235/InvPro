@echo off
echo =========================================
echo Starting XAU/USD Trading Dashboard
echo =========================================

:: Ensure we are running from the directory where the batch file is located
cd /d "%~dp0"

echo [1/3] Starting FastAPI Backend...
start "FastAPI Backend" cmd /k "title FastAPI Backend && python -m uvicorn api.server:app --reload --port 8000"

echo [2/3] Starting Trading Engine...
:: Wait 2 seconds to ensure backend is up before engine starts pushing data
timeout /t 2 /nobreak >nul
start "Trading Engine" cmd /k "title Trading Engine && python main.py"

echo [3/3] Starting React Frontend...
cd dashboard
start "React Frontend" cmd /k "title React Frontend && npm run dev"
cd ..

echo.
echo All services launched in separate windows! 
echo To safely stop everything, run: stop.bat
echo =========================================
