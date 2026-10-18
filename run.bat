@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" goto missing
start "" ".venv\Scripts\pythonw.exe" "%~dp0run.pyw"
exit /b 0
:missing
echo The DailyFocus environment is missing.
echo Please run install.bat first.
pause
exit /b 1
