#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "============================================================"
echo "  AI Media Shorts Studio - Setup & Environment Initializer"
echo "  Repository: https://github.com/josephjilovec/aimediashorts"
echo "============================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found. Please install Python 3.10+."
    exit 1
fi

PY_VER=$(python3 --version)
echo "[+] Detected: $PY_VER"

# Install Dependencies
echo ""
echo "[*] Installing Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Check FFmpeg
echo ""
if command -v ffmpeg &> /dev/null; then
    echo "[+] FFmpeg detected in PATH."
else
    echo "[NOTE] FFmpeg not found. Install ffmpeg for 9:16 vertical video clipping (e.g. 'sudo apt install ffmpeg' or 'brew install ffmpeg')."
fi

# Check Ollama
echo ""
if command -v ollama &> /dev/null; then
    echo "[+] Ollama detected!"
else
    echo "[NOTE] Ollama not found in PATH (Optional for local vision analysis & captioning)."
fi

# Templates
if [ ! -f "config.json" ] && [ -f "config.example.json" ]; then
    cp config.example.json config.json
    echo "[+] Created config.json from template."
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[+] Created .env from template."
fi

echo ""
python3 main.py --status

echo ""
echo "============================================================"
echo "  Setup Complete!"
echo "  - To launch GUI: ./launch_gui.sh"
echo "  - To run pipeline headless: ./run_pipeline.sh"
echo "============================================================"
