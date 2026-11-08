#!/usr/bin/env python3
"""
AI Media Shorts & Auto-Clipper Studio
Main Entry Point and CLI Dispatcher
Author: Joseph Jilovec (JJ)
Repository: https://github.com/josephjilovec/aimediashorts

Usage:
  python main.py                  # Run the complete pipeline (sync, curate, clip, route)
  python main.py --gui            # Launch the Dark-Mode Desktop GUI Control Center
  python main.py --auth           # Run Google OAuth authorization (Google Photos / Drive)
  python main.py --import <dir>   # Import local images/videos from any folder into the pipeline
  python main.py --status         # Display system environment, binaries, and queue health
"""

import sys
import os
import argparse
import shutil
from pathlib import Path

# Force UTF-8 stdout encoding for cross-platform emoji and Unicode support
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import config
from core import auto_shorts_pipeline
from core import vocabulary_guard
from core import privacy_and_pr_shield


def cmd_status():
    """Print system diagnostics, detected paths, binaries, and queue stats."""
    config.ensure_workspace()
    print("\n" + "=" * 65)
    print("  AI Media Shorts Studio - System Diagnostics & Queue Status")
    print("=" * 65)
    
    ws = config.get_workspace_dir()
    print(f"\n[Directories]")
    print(f"  Repo Root:          {REPO_ROOT}")
    print(f"  Workspace Root:     {ws}")
    print(f"  Phone Raw Inbox:    {config.PHONE_RAW_INBOX}")
    print(f"  Curated Best:       {config.CURATED_BEST_DIR}")
    print(f"  Privacy Vault:      {config.PRIVACY_VAULT_DIR}")
    print(f"  Exported Shorts:    {config.EXPORTED_SHORTS_DIR}")
    print(f"  Bot Media Inbox:    {config.ALL_BOTS_DIR}")

    print(f"\n[Google Drive Auto-Detection]")
    gdrive = config.find_google_drive_mount()
    if gdrive:
        print(f"  Status:             CONNECTED ({gdrive})")
        inbox = config.get_gdrive_inbox_dir()
        print(f"  Sync Inbox:         {inbox}")
    else:
        print(f"  Status:             Not mounted (local folder mode active)")

    print(f"\n[Binaries & AI Acceleration]")
    ffmpeg_bin = config.get_ffmpeg_binary()
    print(f"  FFmpeg:             {ffmpeg_bin if ffmpeg_bin else 'NOT FOUND (Install FFmpeg to enable 9:16 video clipping)'}")
    
    ollama_bin = config.get_ollama_binary()
    print(f"  Ollama Binary:      {ollama_bin if ollama_bin else 'Not in PATH (Local vision analysis is optional)'}")
    
    ollama_ok, ollama_msg = privacy_and_pr_shield.check_ollama_status()
    print(f"  Ollama Vision Server: {'ONLINE (' + ollama_msg + ')' if ollama_ok else 'OFFLINE (' + ollama_msg + ')'}")

    print(f"\n[Queue Metrics]")
    raw_count = len(list(config.PHONE_RAW_INBOX.glob("*.*"))) if config.PHONE_RAW_INBOX.exists() else 0
    curated_count = len(list(config.CURATED_BEST_DIR.glob("*.*"))) if config.CURATED_BEST_DIR.exists() else 0
    privacy_count = len(list(config.PRIVACY_VAULT_DIR.glob("*.*"))) if config.PRIVACY_VAULT_DIR.exists() else 0
    shorts_count = len(list(config.EXPORTED_SHORTS_DIR.glob("*.mp4"))) if config.EXPORTED_SHORTS_DIR.exists() else 0
    bot_inbox_count = len(list(config.ALL_BOTS_DIR.glob("*.*"))) if config.ALL_BOTS_DIR.exists() else 0

    print(f"  Raw Media Waiting:  {raw_count} files")
    print(f"  Curated Best Shots: {curated_count} files")
    print(f"  Privacy Vaulted:    {privacy_count} files (Personal/Nude/Docs protected)")
    print(f"  9:16 Shorts Ready:  {shorts_count} videos")
    print(f"  Bot Queue Pending:  {bot_inbox_count} items")
    print("=" * 65 + "\n")


def cmd_import(source_folder: str):
    """Import media from an external directory into the pipeline."""
    src = Path(source_folder).expanduser().resolve()
    if not src.exists() or not src.is_dir():
        print(f"[!] Error: Source directory '{src}' does not exist.")
        sys.exit(1)

    config.ensure_workspace()
    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".avi"}
    imported = 0
    print(f"[*] Importing media from: {src}")
    for item in src.iterdir():
        if item.is_file() and item.suffix.lower() in valid_exts:
            dest = config.PHONE_RAW_INBOX / item.name
            if not dest.exists():
                shutil.copy2(item, dest)
                imported += 1
                print(f"    [+] Imported: {item.name}")

    print(f"[+] Import complete: {imported} new media items copied to Phone_Raw_Inbox.")
    if imported > 0:
        print("[*] Launching pipeline to curate and process imported media...")
        auto_shorts_pipeline.run_pipeline()


def main():
    parser = argparse.ArgumentParser(
        description="AI Media Shorts Clipper, Best-Shot Curator & Privacy Shield",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Repository: https://github.com/josephjilovec/aimediashorts\nAuthor: Joseph Jilovec"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the desktop Dark-Mode GUI Control Center"
    )
    parser.add_argument(
        "--run", "--scan",
        dest="run",
        action="store_true",
        help="Run the complete automated curation and clipping pipeline (default)"
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Run Google Cloud OAuth authorization flow"
    )
    parser.add_argument(
        "--import-folder",
        metavar="FOLDER",
        type=str,
        help="Import images and videos from a folder into Phone_Raw_Inbox"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check system diagnostics, paths, binaries, and queue metrics"
    )

    args = parser.parse_args()

    if args.gui:
        from gui import ai_media_studio_gui
        ai_media_studio_gui.launch()
    elif args.auth:
        from core import authorize_google
        authorize_google.main()
    elif args.import_folder:
        cmd_import(args.import_folder)
    elif args.status:
        cmd_status()
    else:
        # Default action: run the pipeline
        auto_shorts_pipeline.run_pipeline()


if __name__ == "__main__":
    main()
