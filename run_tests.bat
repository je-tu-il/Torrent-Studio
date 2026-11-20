@echo off
chcp 65001 > nul
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" -m unittest discover -s tests
) else (
    python -m unittest discover -s tests
)