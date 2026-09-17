@echo off
python -m pip install -q -r "%~dp0backend\requirements-ai.txt"
if errorlevel 1 goto failed

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_api.ps1"
if errorlevel 1 goto failed

echo.
echo Setup complete. Restart the app backend to use the API settings.
pause
exit /b 0

:failed
echo.
echo Setup failed. Check the message above.
pause
exit /b 1
