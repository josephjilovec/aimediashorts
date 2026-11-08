@echo off
setlocal
title AI Media Shorts Studio - Desktop Control Center
cd /d "%~dp0"

:: Start the GUI application
python main.py --gui
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application exited with error code %ERRORLEVEL%.
    pause
)
