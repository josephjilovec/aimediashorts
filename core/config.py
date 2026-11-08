"""
Configuration Loader & Environment Auto-Detection
Author: Joseph Jilovec (JJ)
"""

import os
import sys
import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PACKAGE_ROOT / "config.json"
ENV_FILE = PACKAGE_ROOT / ".env"

# Candidate search paths for FFmpeg across Windows, macOS, and Linux
COMMON_FFMPEG_PATHS = [
    r"C:\Users\realj\AppData\Local\Programs\Python\Python312\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe",
    r"C:\Users\realj\AppData\Local\ms-playwright\ffmpeg-1013\ffmpeg-win64.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
    "ffmpeg",
]

# Candidate search paths for Ollama
COMMON_OLLAMA_PATHS = [
    r"C:\Users\realj\AppData\Local\Programs\Ollama\ollama.exe",
    r"C:\Program Files\Ollama\ollama.exe",
    "/usr/local/bin/ollama",
    "/usr/bin/ollama",
    "/opt/homebrew/bin/ollama",
    "ollama",
]


def load_env_file():
    """Lightweight .env loader without requiring external python-dotenv package."""
    if ENV_FILE.exists():
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


load_env_file()


def find_google_drive_mount() -> Optional[Path]:
    """Auto-detects Google Drive desktop mount location across Windows, macOS, and Linux."""
    # 1. Check Windows drive letters (G:, H:, D:, etc.)
    if os.name == "nt":
        for letter in ["G", "H", "D", "E", "F", "I", "J"]:
            cand = Path(f"{letter}:\\My Drive")
            if cand.exists():
                return cand

    # 2. Check WSL mounted Windows drive letters
    if Path("/mnt/g/My Drive").exists():
        return Path("/mnt/g/My Drive")
    for letter in ["g", "h", "d", "e", "f"]:
        cand = Path(f"/mnt/{letter}/My Drive")
        if cand.exists():
            return cand

    # 3. Check macOS Google Drive CloudStorage path
    mac_cs = Path.home() / "Library" / "CloudStorage"
    if mac_cs.exists():
        for d in mac_cs.iterdir():
            if "GoogleDrive" in d.name:
                sub = d / "My Drive"
                if sub.exists():
                    return sub
                return d

    # 4. Check home directory Google Drive
    home_gdrive = Path.home() / "Google Drive"
    if home_gdrive.exists():
        return home_gdrive

    return None


def find_binary(candidates: list) -> Optional[str]:
    """Finds the first existing executable binary or resolves it from system PATH."""
    for cand in candidates:
        if os.path.exists(cand) or shutil.which(cand):
            return cand
    return None


def get_ffmpeg_binary() -> Optional[str]:
    custom = os.environ.get("FFMPEG_BINARY_PATH")
    if custom and (os.path.exists(custom) or shutil.which(custom)):
        return custom
    return find_binary(COMMON_FFMPEG_PATHS) or shutil.which("ffmpeg")


def get_ollama_binary() -> Optional[str]:
    return find_binary(COMMON_OLLAMA_PATHS) or shutil.which("ollama")


# Load JSON configuration if present
_RAW_CONFIG: Dict[str, Any] = {}
if CONFIG_FILE.exists():
    try:
        _RAW_CONFIG = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass


def get_workspace_dir() -> Path:
    """Returns the primary media workspace directory (default: ~/Desktop/AI_Auto_Shorts_Pipeline)."""
    env_dir = os.environ.get("MEDIA_WORKSPACE_DIR")
    if env_dir:
        return Path(env_dir).resolve()

    cfg_dir = _RAW_CONFIG.get("pipeline", {}).get("desktop_workspace_dir")
    if cfg_dir:
        return Path(cfg_dir).resolve()

    # Default to user Desktop or package media_workspace
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop / "AI_Auto_Shorts_Pipeline"
    return PACKAGE_ROOT / "media_workspace"


def get_gdrive_inbox_dir() -> Optional[Path]:
    """Returns the Google Drive Phone_Media_Inbox directory if mounted."""
    env_dir = os.environ.get("GDRIVE_INBOX_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.exists():
            return p

    cfg_dir = _RAW_CONFIG.get("pipeline", {}).get("gdrive_inbox_dir")
    if cfg_dir:
        p = Path(cfg_dir)
        if p.exists():
            return p

    mount = find_google_drive_mount()
    if mount and mount.exists():
        return mount / "Phone_Media_Inbox"
    return None


# Base Directories
WORKSPACE_DIR = get_workspace_dir()
RAW_INBOX_DIR = WORKSPACE_DIR / "Phone_Raw_Inbox"
PROCESSED_SHORTS_DIR = WORKSPACE_DIR / "Exported_9x16_Shorts"
ARCHIVE_RAW_DIR = WORKSPACE_DIR / "Processed_Originals_Archive"
CURATED_BEST_DIR = WORKSPACE_DIR / "Curated_Best_Photos"
PRIVACY_VAULT_DIR = WORKSPACE_DIR / "Protected_Private_Vault"
ALL_BOTS_INBOX = PACKAGE_ROOT / "ALL_BOTS_MEDIA_INBOX"

# Friendly Aliases
PHONE_RAW_INBOX = RAW_INBOX_DIR
EXPORTED_SHORTS_DIR = PROCESSED_SHORTS_DIR
ALL_BOTS_DIR = ALL_BOTS_INBOX

LEDGER_FILE = PACKAGE_ROOT / "processed_media_ledger.json"
LOG_FILE = PACKAGE_ROOT / "auto_shorts_pipeline.log"

# Pipeline Settings
AUTO_DELETE_LOCAL_ORIGINALS_AFTER_ROUTING = _RAW_CONFIG.get("pipeline", {}).get(
    "auto_delete_local_originals_after_routing", True
)
AUTO_DELETE_GDRIVE_INBOX_AFTER_PULL = _RAW_CONFIG.get("pipeline", {}).get(
    "auto_delete_gdrive_inbox_after_pull", True
)
MAX_CURATED_PHOTOS_PER_BATCH = _RAW_CONFIG.get("pipeline", {}).get(
    "max_curated_photos_per_batch", 8
)

# Ollama Settings
OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL",
    _RAW_CONFIG.get("ollama", {}).get("base_url", "http://127.0.0.1:11434")
)
OLLAMA_VISION_MODEL = os.environ.get(
    "OLLAMA_VISION_MODEL",
    _RAW_CONFIG.get("ollama", {}).get("vision_model", "gemma4:e2b")
)


def ensure_workspace():
    """Ensures all staging and queue directories exist."""
    for d in [
        WORKSPACE_DIR,
        RAW_INBOX_DIR,
        PROCESSED_SHORTS_DIR,
        ARCHIVE_RAW_DIR,
        CURATED_BEST_DIR,
        PRIVACY_VAULT_DIR,
        ALL_BOTS_INBOX,
    ]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    g_inbox = get_gdrive_inbox_dir()
    if g_inbox:
        try:
            g_inbox.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
