@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 goto failed
echo Installation complete. Double-click run.bat.
pause
exit /b 0
:failed
echo Installation failed. See the message above.
pause
exit /b 1
