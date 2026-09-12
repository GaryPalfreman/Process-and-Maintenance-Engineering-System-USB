@echo off
setlocal
set "APP=%LOCALAPPDATA%\PMES-USB"
set "PY=%APP%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Engineering System is not installed on this computer.
  echo Run install_local.py once on this Windows computer first.
  pause
  exit /b 1
)
cd /d "%APP%"
start "PMES USB" "%PY%" launch_local.py
exit /b 0
