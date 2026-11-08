@echo off
setlocal enabledelayedexpansion
title AI Media Shorts Studio - Setup & Environment Initializer

echo ============================================================
echo   AI Media Shorts Studio - Environment Setup
echo   Repository: https://github.com/josephjilovec/aimediashorts
echo ============================================================
echo.

:: 1. Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in your system PATH!
    echo Please install Python 3.10 or newer from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo [+] Detected: %PY_VER%

:: 2. Install Python Dependencies
echo.
echo [*] Installing required Python libraries from requirements.txt...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some pip packages had issues installing. Check your internet connection.
) else (
    echo [+] All Python requirements installed successfully!
)

:: 3. Check FFmpeg
echo.
where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [NOTE] FFmpeg was not detected in PATH.
    echo If you want automatic 9:16 vertical video clipping:
    echo 1. Download FFmpeg from https://ffmpeg.org/download.html
    echo 2. Place ffmpeg.exe inside this folder, or add it to your Windows PATH.
) else (
    echo [+] FFmpeg detected in system PATH!
)

:: 4. Check Ollama (Optional)
echo.
where ollama >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [NOTE] Ollama not found in PATH (Optional: used for local AI captions and visual PR check).
    echo You can download it from https://ollama.ai if you want local AI vision features.
) else (
    echo [+] Ollama detected!
)

:: 5. Copy config template if not present
if not exist "config.json" (
    if exist "config.example.json" (
        copy "config.example.json" "config.json" >nul
        echo [+] Created config.json from template.
    )
)

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [+] Created .env from template.
    )
)

:: 6. Run Status Check
echo.
python main.py --status

echo.
echo ============================================================
echo   Setup Complete!
echo   - To launch GUI: Double click launch_gui.bat
echo   - To run pipeline headless: Double click run_pipeline.bat
echo ============================================================
pause
