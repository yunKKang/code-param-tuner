@echo off
setlocal

cd /d "%~dp0\.."

set PYTHON_BIN=python
if exist ".venv\Scripts\python.exe" set PYTHON_BIN=.venv\Scripts\python.exe
if exist "backend\venv\Scripts\python.exe" set PYTHON_BIN=backend\venv\Scripts\python.exe

%PYTHON_BIN% -m py_compile backend\main.py backend\ai_analyzer.py backend\parser.py
if errorlevel 1 exit /b 1

%PYTHON_BIN% -m unittest discover -s tests
