@echo off
echo =========================================
echo Stopping XAU/USD Trading Dashboard
echo =========================================

:: Ensure we are running from the directory where the batch file is located
cd /d "%~dp0"

echo Sending kill signals to terminal windows...
:: The /T flag ensures child processes (python.exe, node.exe) are also killed
taskkill /F /FI "WINDOWTITLE eq FastAPI Backend*" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Trading Engine*" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq React Frontend*" /T >nul 2>&1

echo Dashboard stopped successfully!
echo =========================================
