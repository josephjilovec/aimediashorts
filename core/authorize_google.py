"""
Google Photos & Google Drive OAuth 2.0 Authorizer
Author: Joseph Jilovec (JJ)

Walks the user through a 1-click browser sign-in and permanently saves the
OAuth 2.0 Refresh Token into `credentials.json` / environment variables.
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
LOCAL_TOKEN_FILE = PACKAGE_ROOT / "google_photos_token.json"
CREDENTIALS_FILE = PACKAGE_ROOT / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def load_client_config() -> dict:
    """Loads client_id and client_secret from credentials.json, .env, or system vault."""
    # 1. Check local credentials.json
    if CREDENTIALS_FILE.exists():
        try:
            raw = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
            if "installed" in raw or "web" in raw:
                return raw
            if "client_id" in raw:
                return {"installed": raw}
        except Exception:
            pass

    # 2. Check environment variables
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    csec = os.environ.get("GOOGLE_CLIENT_SECRET")
    if cid and csec:
        return {
            "installed": {
                "client_id": cid,
                "client_secret": csec,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }

    # 3. Check permanent system vault if running on original author machine
    vault_path = Path.home() / ".summithill-credentials.json"
    if vault_path.exists():
        try:
            vault = json.loads(vault_path.read_text(encoding="utf-8"))
            cfg = vault.get("googleCloudLocalOllamaCalendar")
            if cfg and cfg.get("client_id"):
                return {"installed": cfg}
        except Exception:
            pass

    return {}


def main():
    print("=" * 72)
    print("  GOOGLE PHOTOS & DRIVE OAUTH 2.0 PERMANENT AUTHORIZER")
    print("=" * 72)

    client_config = load_client_config()
    if not (client_config and client_config.get("installed", {}).get("client_id")):
        print("\n[!] No Google OAuth Client configuration found.")
        print("Please configure your Google Cloud credentials:")
        print("1. Download your OAuth 2.0 Client credentials JSON from Google Cloud Console")
        print(f"2. Save it as: {CREDENTIALS_FILE}")
        print("   OR set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env\n")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("[!] Missing required library: google-auth-oauthlib")
        print("Run: pip install google-auth-oauthlib google-api-python-client")
        sys.exit(1)

    print(f"[*] Client ID : {client_config['installed']['client_id']}")
    print("[*] Opening your browser to authorize Google Photos and Drive...")
    print("    (Sign in and click 'Continue' -> 'Allow')\n")

    try:
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    except Exception as e:
        print(f"\n[!] Notice with all scopes ({e}). Retrying with primary scopes...")
        fallback_scopes = [
            "https://www.googleapis.com/auth/photoslibrary.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        flow = InstalledAppFlow.from_client_config(client_config, scopes=fallback_scopes)
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }

    LOCAL_TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    print(f"[+] Saved OAuth Token to: {LOCAL_TOKEN_FILE}")

    # Also persist to Windows User Environment Variable if on Windows
    if creds.refresh_token and os.name == "nt":
        try:
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f'[Environment]::SetEnvironmentVariable("GOOGLE_PHOTOS_REFRESH_TOKEN", "{creds.refresh_token}", "User")'
                ],
                check=False
            )
            print("[+] Saved GOOGLE_PHOTOS_REFRESH_TOKEN to Windows User Registry Environment.")
        except Exception:
            pass

    print("\n" + "=" * 72)
    print(" SUCCESS! Google Photos & Drive OAuth Refresh Token Stored Permanently!")
    print("=" * 72)


if __name__ == "__main__":
    main()
