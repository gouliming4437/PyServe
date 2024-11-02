@echo off
REM Navigate to the project directory
cd /d "C:\path\to\intranet_site"

REM (Optional) Activate Virtual Environment
REM Uncomment the following line if you're using a virtual environment
REM call venv\Scripts\activate

REM Start the Python server
"C:\path\to\python.exe" server.py

REM Keep the command window open after the server stops
pause