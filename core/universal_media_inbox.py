"""
Universal Multimodal Media Inbox & Intelligent Photo/Video Analyzer Engine.
Shared across ALL Social Media Bots:
- Facebook (`facebook_bot`)
- Twitter/X (`x_master_browser_bot`: `main`, `alt_account`, `cannalog`, `dossier69`)
- Tumblr (`tumblr_bot`)
- Mastodon (`mastodon_bot`)
- Bluesky (`bluesky_bot`)
- LinkedIn (`linkedin_bot`)
- Pinterest (`pinterest_bot`)

Capabilities:
1. Drag-and-Drop Photo & Video Inbox (`media_inbox/` or `photo_inbox/`):
   - Accepts Photos: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`
   - Accepts Videos: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.m4v`
2. Intelligent Visual Reading (Local Multimodal Vision `gemma4:e2b` via Ollama + Cloud AI Fallback):
   - Reads the actual visual contents of any dropped photo (objects, scenery, text/OCR, mood, setting).
3. YouTube-Style AI Video Timestamp Overview (`analyze_video_with_timestamps`):
   - Uses `ffmpeg` (`C:\\Users\\realj\\AppData\\Local\\ms-playwright\\ffmpeg-1013\\ffmpeg-win64.exe`)
     to probe exact video duration and extract keyframes at evenly spaced timestamps (e.g. `00:00`, `00:15`, `00:30`...).
   - Runs multimodal vision across the timestamped frames to generate a YouTube-style AI Timestamp Overview
     plus a platform-tailored post description!
4. One-Time Use & Auto-Delete:
   - Deletes the photo/video (and temporary keyframes) immediately after a confirmed live post so it is never reused.
   - When the inbox folder is empty, each bot seamlessly resumes its default scheduled programming.
"""

import os
import re
import io
import json
import time
import base64
import random
import shutil
import logging
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import vocabulary_guard as vguard

logger = logging.getLogger("UniversalMediaInbox")

PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
ALL_MEDIA_EXTS = PHOTO_EXTS + VIDEO_EXTS

GENERIC_FILENAME_RE = re.compile(
    r"^(img|dsc|dcim|pxl|pic|photo|video|vid|mov|clip|image|screenshot|screen|snap|whatsapp|fb_img|signal|frame|download|untitled|temp|test)"
    r"[\s_\-\d\(\)]*$|^\d{6,}[\s_\-\d\(\)]*$|^[0-9a-f]{8,}(-[0-9a-f]{4,})*$",
    re.IGNORECASE
)

# Paths to local Windows binaries for multimodal vision (Ollama Gemma 4) and video frame extraction (FFmpeg)
WINDOWS_FFMPEG_PATHS = [
    r"C:\Users\realj\AppData\Local\Programs\Python\Python312\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe",
    "/mnt/c/Users/realj/AppData/Local/Programs/Python/Python312/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe",
    r"C:\Users\realj\AppData\Local\ms-playwright\ffmpeg-1013\ffmpeg-win64.exe",
    "/mnt/c/Users/realj/AppData/Local/ms-playwright/ffmpeg-1013/ffmpeg-win64.exe",
    "ffmpeg"
]

WINDOWS_OLLAMA_PATHS = [
    r"C:\Users\realj\AppData\Local\Programs\Ollama\ollama.exe",
    "/mnt/c/Users/realj/AppData/Local/Programs/Ollama/ollama.exe",
    "ollama"
]

OLLAMA_API_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "gemma4:e2b")


def get_ffmpeg_binary() -> Optional[str]:
    for candidate in WINDOWS_FFMPEG_PATHS:
        if os.path.exists(candidate) or shutil.which(candidate):
            return candidate
    return None


def _to_ffmpeg_path(p: Path) -> str:
    """Converts /mnt/c/... paths to C:\\... when invoking Windows ffmpeg-win64.exe from WSL."""
    s = str(p)
    if s.startswith("/mnt/") and len(s) > 6 and s[6] == "/":
        drive = s[5].upper()
        rest = s[6:].replace("/", "\\")
        return f"{drive}:{rest}"
    return s


def ensure_ollama_running() -> bool:
    """Checks if local Ollama server is responsive; if not, starts `ollama serve` silently in background."""
    try:
        req = urllib.request.Request(f"{OLLAMA_API_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as r:
            if r.status == 200:
                return True
    except Exception:
        pass

    ollama_bin = None
    for candidate in WINDOWS_OLLAMA_PATHS:
        if os.path.exists(candidate) or shutil.which(candidate):
            ollama_bin = candidate
            break

    if not ollama_bin:
        return False

    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags
        )
        for _ in range(6):
            time.sleep(1)
            try:
                with urllib.request.urlopen(f"{OLLAMA_API_URL}/api/tags", timeout=2) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Could not auto-start Ollama: {e}")
    return False


def extract_topic_hint_from_filename(filepath: Path) -> str:
    stem = filepath.stem.strip()
    if not stem or GENERIC_FILENAME_RE.match(stem):
        return ""
    cleaned = re.sub(r"[\s_\-]*\(\d+\)$", "", stem)
    cleaned = re.sub(r"[\s_\-]+", " ", cleaned).strip()
    if len(cleaned) < 3 or GENERIC_FILENAME_RE.match(cleaned):
        return ""
    return cleaned


def _encode_image_for_vision(image_path: Path, max_dim: int = 768) -> Optional[str]:
    """Resizes image (if PIL available) and returns base64-encoded JPEG string for vision inference."""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            rgb.thumbnail((max_dim, max_dim))
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=82)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        try:
            raw = image_path.read_bytes()
            if len(raw) < 4 * 1024 * 1024:
                return base64.b64encode(raw).decode("utf-8")
        except Exception:
            pass
    return None


def inspect_photo_basic_stats(filepath: Path) -> Dict[str, str]:
    """Extracts orientation, color/lighting mood, and EXIF time-of-day."""
    meta = {
        "orientation": "landscape",
        "lighting": "natural lighting",
        "time_of_day": ""
    }
    try:
        from PIL import Image, ImageStat
        with Image.open(filepath) as img:
            w, h = img.size
            if w > h * 1.15:
                meta["orientation"] = "wide landscape"
            elif h > w * 1.15:
                meta["orientation"] = "vertical portrait"
            else:
                meta["orientation"] = "square frame"

            try:
                exif = img.getexif()
                if exif:
                    dt_str = exif.get(36867) or exif.get(306)
                    if dt_str and isinstance(dt_str, str) and ":" in dt_str:
                        parts = dt_str.strip().split(" ")
                        if len(parts) >= 2:
                            hour = int(parts[1].split(":")[0])
                            if 5 <= hour < 11:
                                meta["time_of_day"] = "morning"
                            elif 11 <= hour < 16:
                                meta["time_of_day"] = "afternoon"
                            elif 16 <= hour < 20:
                                meta["time_of_day"] = "golden hour / early evening"
                            else:
                                meta["time_of_day"] = "late night"
            except Exception:
                pass

            rgb = img.convert("RGB")
            rgb.thumbnail((128, 128))
            stat = ImageStat.Stat(rgb)
            r_mean, g_mean, b_mean = stat.mean
            lum = 0.299 * r_mean + 0.587 * g_mean + 0.114 * b_mean
            if lum < 65:
                meta["lighting"] = "moody low-light nocturnal atmosphere"
            elif lum > 185:
                meta["lighting"] = "bright sunlit clarity"
            elif r_mean > b_mean + 25:
                meta["lighting"] = "warm golden-hour tones"
            else:
                meta["lighting"] = "crisp balanced lighting"
    except Exception:
        pass
    return meta


def analyze_image_with_vision(image_path: Path, hint: str = "") -> str:
    """
    Uses local Multimodal Vision (`gemma4:e2b` via Ollama) to visually inspect the photo
    and return a concise, accurate description of what is in the image.
    """
    b64 = _encode_image_for_vision(image_path)
    if b64 and ensure_ollama_running():
        prompt = (
            "Look closely at this image and describe what you see in 2 to 3 concise sentences: "
            "identify the main subject, setting/environment, lighting/mood, and any notable details or visible text."
        )
        if hint:
            prompt += f" (Context hint: {hint})"
        payload = {
            "model": OLLAMA_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64]
                }
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 180}
        }
        try:
            req = urllib.request.Request(
                f"{OLLAMA_API_URL}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                vision_desc = vguard.sanitize_text(data.get("message", {}).get("content", "").strip())
                if vision_desc:
                    logger.info(f"[Vision AI] Read photo '{image_path.name}': {vision_desc[:100]}...")
                    return vision_desc
        except Exception as e:
            logger.debug(f"Ollama vision inference note: {e}")

    # Fallback: combine basic visual stats + filename hint
    stats = inspect_photo_basic_stats(image_path)
    parts = [f"A {stats['orientation']} photograph featuring {stats['lighting']}"]
    if stats["time_of_day"]:
        parts.append(f"captured during the {stats['time_of_day']}")
    if hint:
        parts.append(f"highlighting {hint}")
    return ", ".join(parts) + "."


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    mins, secs = divmod(seconds, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def probe_video_duration_seconds(video_path: Path) -> float:
    """Probes exact video duration in seconds using ffmpeg -i stderr."""
    ffmpeg_bin = get_ffmpeg_binary()
    if not ffmpeg_bin:
        return 30.0
    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        proc = subprocess.run(
            [ffmpeg_bin, "-i", _to_ffmpeg_path(video_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            creationflags=flags
        )
        output = (proc.stderr or "") + (proc.stdout or "")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
        if m:
            hrs = int(m.group(1))
            mins = int(m.group(2))
            secs = float(m.group(3))
            return max(1.0, hrs * 3600 + mins * 60 + secs)
    except Exception as e:
        logger.debug(f"Video duration probe note: {e}")
    return 30.0


def extract_video_keyframes(video_path: Path, num_frames: int = 4) -> Tuple[float, List[Tuple[str, Path]]]:
    """
    Extracts `num_frames` evenly-spaced JPEG keyframes across the video timeline using FFmpeg.
    Returns `(duration_sec, [(timestamp_label, frame_path), ...])`.
    """
    duration = probe_video_duration_seconds(video_path)
    ffmpeg_bin = get_ffmpeg_binary()
    if not ffmpeg_bin:
        return duration, []

    temp_dir = video_path.parent / f".frames_{video_path.stem}_{int(time.time())}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Compute evenly spaced timestamps across the video
    if duration <= 6.0:
        timestamps = [0.0, max(1.0, duration * 0.5)]
    else:
        step = duration / float(num_frames)
        timestamps = [round(i * step + min(1.0, step * 0.15), 1) for i in range(num_frames)]

    extracted: List[Tuple[str, Path]] = []
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

    for idx, ts in enumerate(timestamps):
        ts_label = format_timestamp(ts)
        frame_file = temp_dir / f"frame_{idx:02d}_{ts_label.replace(':', '-')}.jpg"
        try:
            subprocess.run(
                [
                    ffmpeg_bin, "-y",
                    "-ss", str(ts),
                    "-i", _to_ffmpeg_path(video_path),
                    "-frames:v", "1",
                    "-q:v", "3",
                    _to_ffmpeg_path(frame_file)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                creationflags=flags
            )
            if frame_file.exists() and frame_file.stat().st_size > 1000:
                extracted.append((ts_label, frame_file))
        except Exception as e:
            logger.debug(f"Frame extraction at {ts_label} failed: {e}")

    return duration, extracted


def analyze_video_with_timestamps(video_path: Path, hint: str = "") -> Dict[str, Any]:
    """
    Analyzes a video file just like YouTube's AI Timestamp Overview sidebar:
    1. Probes the video duration and extracts 4 keyframes at evenly-spaced timestamps (`00:01`, `00:05`, etc.).
    2. Runs visual inspection on the representative keyframe + per-frame lighting/scene shifts.
    3. Synthesizes progressive, non-repetitive timestamp summaries and saves a high-res thumbnail.
    """
    duration, frames = extract_video_keyframes(video_path, num_frames=4)
    best_thumbnail: Optional[Path] = None
    frame_timestamps: List[str] = []
    frame_stats_list: List[str] = []

    if frames:
        mid_idx = min(1, len(frames) - 1)
        src_thumb = frames[mid_idx][1]
        best_thumbnail = video_path.parent / f".thumb_{video_path.stem}.jpg"
        try:
            shutil.copy(src_thumb, best_thumbnail)
        except Exception:
            best_thumbnail = None

        # Run deep vision reading on the primary keyframe (1 fast call instead of 4 redundant calls)
        primary_vision = analyze_image_with_vision(src_thumb, hint=hint)

        for idx, (ts_label, frame_path) in enumerate(frames):
            frame_timestamps.append(ts_label)
            st = inspect_photo_basic_stats(frame_path)
            frame_stats_list.append(f"{ts_label} ({st['lighting']})")

        try:
            shutil.rmtree(frames[0][1].parent, ignore_errors=True)
        except Exception:
            pass
    else:
        primary_vision = f"Video clip showcasing {hint or 'key visual details and real-time perspective'}."
        step = max(3.0, duration / 4.0)
        frame_timestamps = [format_timestamp(i * step + 1.0) for i in range(4)]
        frame_stats_list = [f"{ts} (scene {i+1})" for i, ts in enumerate(frame_timestamps)]

    # Synthesize progressive YouTube-style timestamp notes in a single LLM call (or natural fallback)
    ts_list_str = ", ".join(frame_timestamps)
    subject = hint or video_path.stem.replace("_", " ").replace("-", " ")
    ts_prompt = (
        f"Create a YouTube-style 4-bullet AI Timestamp Overview for a {format_timestamp(duration)} video about '{subject}'.\n"
        f"Visual context from video keyframes: {primary_vision}\n"
        f"Exact timestamps to use: {ts_list_str}\n"
        f"Format each line strictly as:\n"
        f"• MM:SS — [1 concise, specific sentence describing that stage of the video, progressing naturally from opening to conclusion]\n"
        f"Output ONLY the 4 bullet lines."
    )
    raw_bullets = _generate_text_via_llm(ts_prompt, max_chars=500)

    timestamp_notes: List[Dict[str, str]] = []
    if raw_bullets and "•" in raw_bullets:
        for line in raw_bullets.splitlines():
            line = line.strip()
            if line.startswith(("•", "-", "*")):
                parts = re.split(r"\s*[—–]\s*|\s+-\s+", line.lstrip("•-* ").strip(), maxsplit=1)
                if len(parts) == 2:
                    timestamp_notes.append({"timestamp": parts[0].strip(), "summary": parts[1].strip()})

    if len(timestamp_notes) < 2:
        t0 = frame_timestamps[0] if len(frame_timestamps) > 0 else "00:01"
        t1 = frame_timestamps[1] if len(frame_timestamps) > 1 else "00:05"
        t2 = frame_timestamps[2] if len(frame_timestamps) > 2 else "00:09"
        t3 = frame_timestamps[3] if len(frame_timestamps) > 3 else "00:13"
        timestamp_notes = [
            {"timestamp": t0, "summary": f"Opening establishing view of {subject}."},
            {"timestamp": t1, "summary": "Closer perspective examining the layout, structure, and environment in motion."},
            {"timestamp": t2, "summary": "Key operational details and visual highlights across the middle of the clip."},
            {"timestamp": t3, "summary": "Closing perspective and final takeaway from the walkthrough."}
        ]

    overview_lines = ["⏱️ AI Video Overview:"]
    for item in timestamp_notes:
        overview_lines.append(f"• {item['timestamp']} — {item['summary']}")
    timestamp_overview_block = "\n".join(overview_lines)

    return {
        "duration_sec": round(duration, 1),
        "duration_formatted": format_timestamp(duration),
        "timestamps": timestamp_notes,
        "timestamp_overview_block": timestamp_overview_block,
        "visual_summary": primary_vision,
        "thumbnail_path": str(best_thumbnail) if best_thumbnail and best_thumbnail.exists() else None
    }


def scan_inbox_directory(
    inbox_dir: Path,
    subfolders: Optional[Dict[str, Path]] = None,
    default_category: str = "general"
) -> List[Dict[str, Any]]:
    """
    Scans `inbox_dir` (and any optional category `subfolders`) for photos and videos.
    Returns media descriptors sorted oldest-first (FIFO).
    """
    inbox_dir.mkdir(parents=True, exist_ok=True)
    if subfolders:
        for sf in subfolders.values():
            sf.mkdir(parents=True, exist_ok=True)

    found: List[Dict[str, Any]] = []

    # 1. Scan root inbox_dir
    for entry in inbox_dir.iterdir():
        if entry.is_file() and not entry.name.startswith(".") and entry.suffix.lower() in ALL_MEDIA_EXTS:
            found.append(_create_raw_item(entry, default_category))

    # 2. Scan category subfolders
    if subfolders:
        for cat_key, folder_path in subfolders.items():
            if folder_path.exists():
                for entry in folder_path.iterdir():
                    if entry.is_file() and not entry.name.startswith(".") and entry.suffix.lower() in ALL_MEDIA_EXTS:
                        found.append(_create_raw_item(entry, cat_key))

    # 3. Also scan the matching normal folder in ALL_BOTS_MEDIA_INBOX (avoids NTFS junctions in OneDrive)
    hub_map = {
        ("facebook_bot", "photo_inbox"): "Facebook",
        ("bluesky_bot", "media_inbox"): "Bluesky",
        ("linkedin_bot", "media_inbox"): "LinkedIn",
        ("mastodon_bot", "media_inbox"): "Mastodon",
        ("pinterest_bot", "media_inbox"): "Pinterest",
        ("tumblr_bot", "media_inbox"): "Tumblr",
        ("media_inbox", "main"): "Twitter_Main_JosephJilovec",
        ("media_inbox", "alt_account"): "Twitter_AltAccount_SpaceMothership",
        ("media_inbox", "cannalog"): "Twitter_CannaLog",
        ("media_inbox", "dossier69"): "Twitter_Dossier69",
    }
    hub_name = hub_map.get((inbox_dir.parent.name, inbox_dir.name))
    if hub_name:
        hub_dir = Path(__file__).resolve().parent / "ALL_BOTS_MEDIA_INBOX" / hub_name
        if hub_dir.exists() and hub_dir.resolve() != inbox_dir.resolve():
            for entry in hub_dir.iterdir():
                if entry.is_file() and not entry.name.startswith(".") and entry.suffix.lower() in ALL_MEDIA_EXTS:
                    found.append(_create_raw_item(entry, default_category))
                elif entry.is_dir() and not entry.name.startswith("."):
                    for sub_entry in entry.iterdir():
                        if sub_entry.is_file() and not sub_entry.name.startswith(".") and sub_entry.suffix.lower() in ALL_MEDIA_EXTS:
                            found.append(_create_raw_item(sub_entry, entry.name))

    found.sort(key=lambda x: x["mtime"])
    return found


def parse_routed_sidecar_metadata(raw_text: str) -> Dict[str, Any]:
    """
    Parses internal diagnostic blocks (Category, Context Note, AI Visual Summary, Video Overview)
    from a sidecar .txt file so internal telemetry is NEVER posted as the public post text.
    """
    data = {
        "category": "",
        "user_note": "",
        "visual_summary": "",
        "timestamp_overview": "",
        "clean_user_text": "",
        "is_internal_envelope": False
    }
    if not raw_text:
        return data

    lines = raw_text.splitlines()
    other_lines = []
    in_ts = False
    ts_lines = []

    for line in lines:
        s = line.strip()
        if s.startswith("Category:"):
            data["category"] = s.split("Category:", 1)[1].strip()
            data["is_internal_envelope"] = True
        elif s.startswith("Context Note:"):
            val = s.split("Context Note:", 1)[1].strip()
            data["is_internal_envelope"] = True
            # Disregard auto camera codes or clip names as real user notes
            is_camera_code = bool(
                re.search(r"(?:PXL|IMG|VID|DSC|1000\d{4,})", val, re.IGNORECASE) or
                "9x16" in val.lower() or
                "clip" in val.lower() or
                "part" in val.lower()
            )
            if not is_camera_code:
                data["user_note"] = val
        elif s.startswith("AI Visual Summary:"):
            data["visual_summary"] = s.split("AI Visual Summary:", 1)[1].strip()
            data["is_internal_envelope"] = True
        elif "⏱️ AI Video Overview:" in s:
            in_ts = True
            ts_lines.append(s)
            data["is_internal_envelope"] = True
        elif in_ts:
            if s.startswith(("•", "-", "*")) or re.match(r"^\d{2}:\d{2}", s):
                ts_lines.append(s)
            elif not s:
                continue
            else:
                in_ts = False
                other_lines.append(line)
        else:
            other_lines.append(line)

    data["timestamp_overview"] = "\n".join(ts_lines).strip()
    data["clean_user_text"] = "\n".join(other_lines).strip()
    return data


def clean_visual_summary_text(raw_visual: str) -> str:
    """Strips camera filenames, 'highlighting PXL_*', and stock robot phrases."""
    if not raw_visual:
        return ""
    v = re.sub(r",\s*highlighting\s+.*$", "", raw_visual, flags=re.IGNORECASE)
    v = re.sub(r"highlighting\s+.*$", "", v, flags=re.IGNORECASE)
    v = re.sub(r"^(?:A\s+)?vertical\s+(?:portrait\s+)?(?:photograph|video|frame)\s+featuring\s+", "", v, flags=re.IGNORECASE)
    v = re.sub(r"^(?:The\s+)?vertical\s+frame\s+captures\s+", "", v, flags=re.IGNORECASE)
    v = re.sub(r"^(?:Video\s+clip\s+showcasing\s+)", "", v, flags=re.IGNORECASE)
    v = re.sub(r"(?:PXL|IMG|VID|DSC|1000\d{4,})[A-Za-z0-9_]*", "", v, flags=re.IGNORECASE)
    v = v.strip().strip(".").strip(",").strip()
    return v


def is_internal_metadata_slop(text: str) -> bool:
    """Checks if text accidentally contains raw pipeline telemetry or camera filenames."""
    if not text:
        return True
    t_low = text.lower()
    slop_indicators = [
        "category: visual update",
        "category: enterprise",
        "category: botanical",
        "context note:",
        "ai visual summary:",
        "ai visual reading",
        "a vertical portrait photograph featuring",
        "the vertical frame captures",
        "clip1_intro_9x16",
        "clip2_mid_action_9x16",
        "clip3_finale_9x16",
        "part1_opening_9x16",
        "part2_highlight_9x16",
        "⏱️ ai video overview"
    ]
    for ind in slop_indicators:
        if ind in t_low:
            return True
    if re.search(r"(?:pxl|img|vid|dsc|1000\d{4,})_\d{8}", t_low):
        return True
    return False


def generate_natural_human_fallback(
    platform: str,
    media_type: str,
    category: str,
    user_note: str,
    visual_summary: str,
    max_chars: int = 280
) -> str:
    """
    Crafts an authentic, 100% human-sounding first-person caption ('I', 'me', 'we', 'here in Arizona')
    with zero robotic AI categorization or diagnostic metadata.
    """
    vis = clean_visual_summary_text(visual_summary)
    if user_note:
        if len(user_note) > max_chars:
            return user_note[:max_chars - 3].rstrip() + "..."
        return user_note

    plat_low = platform.lower()
    cat_low = category.lower()

    if "facebook" in plat_low:
        if any(k in cat_low for k in ["botanical", "cannabis", "garden", "plant"]):
            options = [
                "Checking in on the garden today. Vibrant growth and solid plant health across the board.",
                "Garden walkthrough from today. The structure and consistency are looking great.",
                "Field perspective from the grow. Taking the time to dial in the small details always pays off."
            ]
        elif any(k in cat_low for k in ["systems", "architecture", "code", "tech"]):
            options = [
                "Deep in systems architecture today. Building out reliable, modular infrastructure from the ground up.",
                "Behind the screens on operational tooling. Clean architecture beats complexity every single time.",
                "Quick look at what we're building. Disciplined execution and clean systems design in action."
            ]
        else:
            options = [
                f"Out and about today in Arizona. {vis.capitalize() if vis else 'Taking in the view'}. Good energy all around.",
                f"Field perspective from today. {vis.capitalize() if vis else 'Staying focused on the work'}. Moving forward step by step.",
                f"A quick look from today. Always good to step back, get outside, and keep momentum high."
            ]
    elif any(k in plat_low for k in ["twitter", "x (", "bluesky", "mastodon"]):
        if any(k in cat_low for k in ["botanical", "cannabis", "garden", "plant"]):
            options = [
                "Dialed in on plant morphology and trichome maturity. Consistency in the craft.",
                "Field check. Structure, canopy balance, and resin development looking exceptional.",
                "Precision cultivation in motion. Process discipline translates directly to end quality."
            ]
        elif any(k in cat_low for k in ["systems", "architecture", "code", "tech"]):
            options = [
                "Systems architecture from the ground up. Modularity and operational reliability above all.",
                "Designing resilient pipelines. Eliminating single points of failure before scaling.",
                "Execution clarity in systems design. Keep the core tight and the architecture clean."
            ]
        else:
            options = [
                f"Field perspective today. {vis.capitalize() if vis else 'Steady rhythm and clear focus'}.",
                f"Quick look from the ground. Keeping the operational momentum moving forward.",
                f"Direct perspective today. Disciplined focus and clear execution."
            ]
    else:
        options = [
            f"Field perspective today. {vis.capitalize() if vis else 'Disciplined execution'}.",
            f"Quick visual update from the field. Steady progress on the ground."
        ]

    chosen = random.choice(options)
    if len(chosen) > max_chars:
        chosen = chosen[:max_chars - 3].rstrip() + "..."
    return chosen


def _create_raw_item(filepath: Path, category: str) -> Dict[str, Any]:
    ext = filepath.suffix.lower()
    media_type = "video" if ext in VIDEO_EXTS else "photo"
    sidecar_txt = filepath.with_suffix(".txt")
    sidecar_note = ""
    parsed_meta = {}
    if sidecar_txt.exists() and sidecar_txt.name.upper() not in ("README.TXT", "HOW_TO_UPLOAD_PHOTOS.TXT", "HOW_TO_USE_MEDIA_INBOX.TXT"):
        try:
            raw_text = sidecar_txt.read_text(encoding="utf-8").strip()
            parsed_meta = parse_routed_sidecar_metadata(raw_text)
            if parsed_meta.get("is_internal_envelope"):
                sidecar_note = parsed_meta.get("clean_user_text") or parsed_meta.get("user_note") or ""
            else:
                sidecar_note = raw_text
        except Exception:
            sidecar_note = ""

    topic_hint = extract_topic_hint_from_filename(filepath)

    return {
        "path": str(filepath),
        "filename": filepath.name,
        "media_type": media_type,
        "category": parsed_meta.get("category") or category,
        "topic_hint": topic_hint,
        "sidecar_note": sidecar_note,
        "parsed_sidecar": parsed_meta,
        "sidecar_path": str(sidecar_txt) if (sidecar_note or parsed_meta) else None,
        "mtime": filepath.stat().st_mtime
    }


def get_and_analyze_next_inbox_media(
    inbox_dir: Path,
    subfolders: Optional[Dict[str, Path]] = None,
    default_category: str = "general"
) -> Optional[Dict[str, Any]]:
    """
    Finds the next waiting photo or video in `inbox_dir` (or its subfolders) and runs
    full intelligent visual analysis (or timestamped video analysis) on it.
    """
    items = scan_inbox_directory(inbox_dir, subfolders, default_category)
    if not items:
        return None

    import privacy_and_pr_shield as pr_shield

    for item in items:
        filepath = Path(item["path"])
        parsed_sidecar = item.get("parsed_sidecar", {})
        
        # If pre-computed in sidecar, use it directly to save time and compute
        if parsed_sidecar.get("visual_summary"):
            item["visual_summary"] = parsed_sidecar["visual_summary"]
            item["timestamp_overview_block"] = parsed_sidecar.get("timestamp_overview", "")
            item["timestamps"] = []
            item["duration_formatted"] = ""
            item["thumbnail_path"] = str(filepath)
            item["visual_meta"] = {"orientation": "video" if item["media_type"] == "video" else "photo", "lighting": "natural", "time_of_day": ""}
        else:
            hint = item["sidecar_note"] or item["topic_hint"]
            if item["media_type"] == "video":
                logger.info(f"[MediaInbox] Analyzing uploaded VIDEO '{item['filename']}' with timestamp keyframes...")
                video_analysis = analyze_video_with_timestamps(filepath, hint=hint)
                item["visual_summary"] = video_analysis["visual_summary"]
                item["timestamp_overview_block"] = video_analysis["timestamp_overview_block"]
                item["timestamps"] = video_analysis["timestamps"]
                item["duration_formatted"] = video_analysis["duration_formatted"]
                item["thumbnail_path"] = video_analysis["thumbnail_path"]
                item["visual_meta"] = {"orientation": "video", "lighting": "motion clip", "time_of_day": ""}
            else:
                logger.info(f"[MediaInbox] Analyzing uploaded PHOTO '{item['filename']}' with Multimodal Vision...")
                item["visual_meta"] = inspect_photo_basic_stats(filepath)
                item["visual_summary"] = analyze_image_with_vision(filepath, hint=hint)
                item["timestamp_overview_block"] = ""
                item["timestamps"] = []
                item["thumbnail_path"] = str(filepath)

        shield = pr_shield.inspect_media_privacy_and_pr(filepath, visual_summary=item["visual_summary"])
        if not shield["safe"]:
            logger.warning(f"[Privacy & PR Shield] Blocked '{item['filename']}' from posting ({shield['reason']}). Removing from bot queue.")
            consume_and_delete_media_item(item)
            continue

        return item

    return None


def generate_platform_post_from_media(
    media_item: Dict[str, Any],
    platform: str,
    persona_instructions: str,
    max_chars: int = 1200,
    include_timestamp_sidebar: bool = True
) -> Dict[str, Any]:
    """
    Synthesizes an intelligent, platform-native social media post based on the visual analysis
    of the uploaded photo or the timestamped scene breakdown of the uploaded video.
    Guarantees internal metadata, camera filenames, and AI categorization tags are NEVER posted publicly.
    """
    media_type = media_item["media_type"]
    category = media_item.get("category", "general")
    topic_hint = media_item.get("topic_hint", "")
    sidecar_note = media_item.get("sidecar_note", "")
    visual_summary = media_item.get("visual_summary", "")
    ts_block = media_item.get("timestamp_overview_block", "")

    # Clean visual summary of camera codes & robot prefixes
    vis_cleaned = clean_visual_summary_text(visual_summary)

    # Disregard auto camera codes as user notes
    clean_user_note = sidecar_note
    if clean_user_note and is_internal_metadata_slop(clean_user_note):
        clean_user_note = ""

    # Reserve space for the timestamped video overview block on long-form platforms
    append_ts = (media_type == "video" and include_timestamp_sidebar and ts_block and max_chars >= 450)
    body_budget = (max_chars - len(ts_block) - 10) if append_ts else max_chars

    prompt = (
        f"You are Joseph Jilovec writing an authentic, human {platform} post to accompany a {media_type} you recorded.\n"
        f"Persona: {persona_instructions}\n"
        f"Theme / Setting: {category}\n"
    )
    if clean_user_note:
        prompt += f"Context Note from you: {clean_user_note}\n"
    if vis_cleaned:
        prompt += f"Visual scene details: {vis_cleaned}\n"
    prompt += (
        f"Strict Posting Rules:\n"
        f"- Write in natural first-person ('I', 'me', 'we', 'here in Arizona').\n"
        f"- Write as a grounded human sharing real progress, field perspective, or systems thinking.\n"
        f"- NEVER output internal metadata, categories, robot descriptions, or labels like 'Category:', 'AI Visual Summary:', or camera filenames.\n"
        f"- {vguard.LLM_PROHIBITION_RULE}\n"
        f"- Strictly under {body_budget} characters.\n"
        f"- Output ONLY the final post text."
    )

    generated_text = _generate_text_via_llm(prompt, max_chars=body_budget)

    # If LLM failed, or if it accidentally output internal metadata slop, use the clean human fallback
    if not generated_text or is_internal_metadata_slop(generated_text):
        generated_text = generate_natural_human_fallback(
            platform=platform,
            media_type=media_type,
            category=category,
            user_note=clean_user_note,
            visual_summary=vis_cleaned,
            max_chars=body_budget
        )

    if append_ts and not is_internal_metadata_slop(ts_block):
        final_text = f"{generated_text.strip()}\n\n{ts_block}".strip()
    else:
        final_text = generated_text.strip()

    final_text = vguard.sanitize_text(final_text)
    if len(final_text) > max_chars:
        final_text = final_text[:max_chars - 3].rstrip() + "..."

    first_line = final_text.splitlines()[0].strip() if final_text else "Media update"
    return vguard.sanitize_payload({
        "text": final_text,
        "hook": first_line[:90],
        "title": f"{media_type.capitalize()}: {topic_hint or category}",
        "pillar": f"media_inbox_{category}",
        "media_type": media_type,
        "visual_summary": visual_summary,
        "timestamp_overview": ts_block,
        "char_count": len(final_text),
        "from_media_inbox": True
    })


def _generate_text_via_llm(prompt: str, max_chars: int = 800) -> Optional[str]:
    """Tries Pollinations OpenAI endpoint (with automatic 402 cooldown retry), then local Ollama `gemma4:e2b`."""
    if vguard.LLM_PROHIBITION_RULE not in prompt:
        prompt = f"{prompt}\n\n{vguard.LLM_PROHIBITION_RULE}"
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                "https://text.pollinations.ai/openai",
                data=json.dumps({
                    "model": "openai",
                    "messages": [{"role": "user", "content": prompt}]
                }).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": f"Mozilla/5.0 (Bot/{random.randint(100,999)})"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                res = json.loads(r.read().decode("utf-8"))
                content = vguard.sanitize_text(res["choices"][0]["message"]["content"].strip().strip('"'))
                if content:
                    return content
        except urllib.error.HTTPError as e:
            if e.code == 402 and attempt == 0:
                time.sleep(15)
                continue
            break
        except Exception:
            break

    # 2. Try local Ollama gemma4:e2b
    if ensure_ollama_running():
        try:
            req = urllib.request.Request(
                f"{OLLAMA_API_URL}/api/chat",
                data=json.dumps({
                    "model": OLLAMA_VISION_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.6, "num_predict": 250}
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                res = json.loads(r.read().decode("utf-8"))
                content = vguard.sanitize_text(res.get("message", {}).get("content", "").strip().strip('"'))
                if content:
                    return content
        except Exception:
            pass

    return None


def consume_and_delete_media_item(media_item: Dict[str, Any]) -> bool:
    """
    Deletes the uploaded photo or video file (plus any sidecar .txt and extracted video thumbnail)
    after the bot successfully publishes the post live, ensuring one-time use.
    """
    if not media_item:
        return False

    deleted = False
    media_path = Path(media_item["path"])
    try:
        if media_path.exists():
            media_path.unlink()
            deleted = True
            logger.info(f"[+] Auto-deleted one-time inbox {media_item.get('media_type', 'media')}: {media_path.name}")
    except Exception as e:
        logger.error(f"Failed to delete inbox media {media_path}: {e}")

    sidecar_str = media_item.get("sidecar_path")
    if sidecar_str:
        try:
            sp = Path(sidecar_str)
            if sp.exists():
                sp.unlink()
        except Exception:
            pass

    thumb_str = media_item.get("thumbnail_path")
    if thumb_str and thumb_str != str(media_path):
        try:
            tp = Path(thumb_str)
            if tp.exists():
                tp.unlink()
        except Exception:
            pass

    return deleted
