@echo off
REM Stop the server
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000" ^| find "LISTENING"') do taskkill /F /PID %%a
timeout /t 2
REM Start the server
start /b "" wscript.exe start_hidden.vbs
echo Server restarted!
pause 