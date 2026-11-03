@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 (
  echo Startup failed. See logs\app.log and run --selfcheck.
  pause
)