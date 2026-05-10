@echo off
setlocal

cd /d "%~dp0\.."

if "%CPT_PORT%"=="" set CPT_PORT=8000

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo Code Param Tuner: http://localhost:%CPT_PORT%/
python -m backend.main
