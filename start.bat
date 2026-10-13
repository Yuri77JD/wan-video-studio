@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [Wan Video Studio] Creating virtual environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 goto :error
)
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
if errorlevel 1 goto :error
if not exist ".env" copy /Y ".env.example" ".env" >nul
python app.py
if errorlevel 1 goto :error
goto :eof
:error
echo.
echo Startup failed. See the error above.
pause
exit /b 1
