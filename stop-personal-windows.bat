@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 launch.py personal --command stop
) else (
  python launch.py personal --command stop
)
if errorlevel 1 pause
