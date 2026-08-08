@echo off
REM Launch the J.A.R.V.I.S. Desktop HUD.
cd /d "%~dp0"

REM Use the project virtual environment when present, otherwise system python.
if exist "ollama_assistant_env\Scripts\python.exe" (
    set "PYTHON=ollama_assistant_env\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo Starting J.A.R.V.I.S. Desktop HUD...
"%PYTHON%" main.py
pause
