@echo off
setlocal
title AI Media Shorts Pipeline Runner
cd /d "%~dp0"

echo ============================================================
echo   AI Media Shorts - Processing Raw Media & Curation
echo ============================================================
echo.

python main.py --run

echo.
echo ============================================================
echo   Pipeline Finished!
echo ============================================================
pause
