@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

python -c "import numpy" >nul 2>nul
if errorlevel 1 (
    echo Installing NumPy...
    python -m pip install numpy
)

set PYTHONPATH=%~dp0
python 9_planets_v18_deterministic_weather.py
pause
