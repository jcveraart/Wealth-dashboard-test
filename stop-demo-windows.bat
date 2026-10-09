@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 launch.py demo --command stop
) else (
  python launch.py demo --command stop
)
if errorlevel 1 pause
