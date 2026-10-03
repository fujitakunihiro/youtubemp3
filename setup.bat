@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

echo [1/3] Python environment...
py -3 -m venv .venv
if errorlevel 1 goto :error

echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [3/3] Installing FFmpeg...
".venv\Scripts\python.exe" -c "import static_ffmpeg; static_ffmpeg.add_paths()"
if errorlevel 1 goto :error

echo.
echo Setup complete. Run start.bat.
pause
exit /b 0

:error
echo.
echo Setup failed. Check your internet connection and Python installation.
pause
exit /b 1
