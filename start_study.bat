@echo off
REM ------------------------------------------------------------------
REM  Beyond Clicks study: start the website on this laptop.
REM  Double-click this file. Keep this window open while the study runs.
REM  Close the window (or press Ctrl+C) to stop the website.
REM ------------------------------------------------------------------
cd /d "%~dp0"

if not exist ".env" (
  echo [!] No .env file found. Copy .env.example to .env and fill in the values.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating the Python environment. This takes a few minutes...
  python -m venv .venv || (echo [!] Python 3.11+ is needed: https://www.python.org/downloads/ & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\pip.exe" install -r requirements-analysis.txt || (echo [!] Package install failed. & pause & exit /b 1)
)

netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if not errorlevel 1 (
  echo [!] The study website is ALREADY RUNNING in another window ^(maybe an older copy^).
  echo     Close that other black window first, then double-click start_study.bat again.
  echo     If you cannot find it: restart the laptop, then double-click start_study.bat.
  pause
  exit /b 1
)

echo.
echo  Study website:        http://localhost:8000
echo  Researcher dashboard: http://localhost:8000/admin   (password: ADMIN_PASSWORD in .env)
echo  Experimenter guide:   http://localhost:8000/guide
echo.
echo  Keep this window open. Close it to stop the website.
echo.
start "" "http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
