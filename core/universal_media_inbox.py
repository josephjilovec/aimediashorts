"""
Universal Multimodal Media Analyzer & Intelligent Video Keyframe Engine
Author: Joseph Jilovec (JJ)
"""

import io
import re
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

from . import config
from . import vocabulary_guard as vguard

logger = logging.getLogger("UniversalMediaInbox")

PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
ALL_MEDIA_EXTS = PHOTO_EXTS + VIDEO_EXTS

GENERIC_FILENAME_RE = re.compile(
    r"^(img|dsc|dcim|pxl|pic|photo|video|vid|mov|clip|image|screenshot|screen|snap|whatsapp|fb_img|signal|frame|download|untitled|temp|test)"
    r"[\s_\-\d\(\)]*$|^\d{6,}[\s_\-\d\(\)]*$|^[0-9a-f]{8,}(-[0-9a-f]{4,})*$",
    re.IGNORECASE
)


def to_ffmpeg_path(p: Path) -> str:
    """Converts WSL /mnt/c/... paths to C:\\... when invoking Windows FFmpeg binary from WSL."""
    s = str(p)
    if s.startswith("/mnt/") and len(s) > 6 and s[6] == "/":
        drive = s[5].upper()
        rest = s[6:].replace("/", "\\")
        return f"{drive}:{rest}"
    return s


def ensure_ollama_running() -> bool:
    """Checks if local Ollama server is responsive; if not, attempts to start `ollama serve`."""
    try:
        req = urllib.request.Request(f"{config.OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as r:
            if r.status == 200:
                return True
    except Exception:
        pass

    ollama_bin = config.get_ollama_binary()
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
                with urllib.request.urlopen(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=2) as r:
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


def encode_image_for_vision(image_path: Path, max_dim: int = 768) -> Optional[str]:
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
    """Uses local Multimodal Vision via Ollama to return a concise description of the image."""
    b64 = encode_image_for_vision(image_path)
    if b64 and ensure_ollama_running():
        prompt = (
            "Look closely at this image and describe what you see in 2 to 3 concise sentences: "
            "identify the main subject, setting/environment, lighting/mood, and any notable details or visible text."
        )
        if hint:
            prompt += f" (Context hint: {hint})"
        payload = {
            "model": config.OLLAMA_VISION_MODEL,
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
                f"{config.OLLAMA_BASE_URL}/api/chat",
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

    stats = inspect_photo_basic_stats(image_path)
    parts = [f"A {stats['orientation']} photograph featuring {stats['lighting']}"]
    if hint:
        parts.append(f"highlighting {hint}")
    return vguard.sanitize_text(", ".join(parts) + ".")


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    mins, secs = divmod(seconds, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def probe_video_duration_seconds(video_path: Path) -> float:
    ffmpeg_bin = config.get_ffmpeg_binary()
    if not ffmpeg_bin:
        return 30.0
    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        proc = subprocess.run(
            [ffmpeg_bin, "-i", to_ffmpeg_path(video_path)],
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
    """Extracts `num_frames` evenly-spaced JPEG keyframes across the video timeline using FFmpeg."""
    duration = probe_video_duration_seconds(video_path)
    ffmpeg_bin = config.get_ffmpeg_binary()
    if not ffmpeg_bin:
        return duration, []

    temp_dir = video_path.parent / f".frames_{video_path.stem}_{int(time.time())}"
    temp_dir.mkdir(parents=True, exist_ok=True)

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
                    "-i", to_ffmpeg_path(video_path),
                    "-frames:v", "1",
                    "-q:v", "3",
                    to_ffmpeg_path(frame_file)
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
    duration, frames = extract_video_keyframes(video_path, num_frames=4)
    best_thumbnail: Optional[Path] = None
    frame_timestamps: List[str] = []

    if frames:
        mid_idx = min(1, len(frames) - 1)
        src_thumb = frames[mid_idx][1]
        best_thumbnail = video_path.parent / f".thumb_{video_path.stem}.jpg"
        try:
            shutil.copy(src_thumb, best_thumbnail)
        except Exception:
            best_thumbnail = None

        primary_vision = analyze_image_with_vision(src_thumb, hint=hint)
        for _, (ts_label, _) in enumerate(frames):
            frame_timestamps.append(ts_label)

        try:
            shutil.rmtree(frames[0][1].parent, ignore_errors=True)
        except Exception:
            pass
    else:
        primary_vision = f"Video clip showcasing {hint or 'key visual details and real-time perspective'}."
        step = max(3.0, duration / 4.0)
        frame_timestamps = [format_timestamp(i * step + 1.0) for i in range(4)]

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
    raw_bullets = generate_text_via_llm(ts_prompt, max_chars=500)

    timestamp_notes: List[Dict[str, str]] = []
    if raw_bullets and "•" in raw_bullets:
        for line in raw_bullets.splitlines():
            line = line.strip()
            if line.startswith(("•", "-", "*")):
                parts = re.split(r"\s*[—–]\s*|\s+-\s+", line.lstrip("•-* ").strip(), maxsplit=1)
                if len(parts) == 2:
                    timestamp_notes.append({
                        "timestamp": parts[0].strip(),
                        "summary": vguard.sanitize_text(parts[1].strip())
                    })

    if len(timestamp_notes) < 2:
        t0 = frame_timestamps[0] if len(frame_timestamps) > 0 else "00:01"
        t1 = frame_timestamps[1] if len(frame_timestamps) > 1 else "00:05"
        t2 = frame_timestamps[2] if len(frame_timestamps) > 2 else "00:09"
        t3 = frame_timestamps[3] if len(frame_timestamps) > 3 else "00:13"
        timestamp_notes = [
            {"timestamp": t0, "summary": f"Opening establishing view of {subject}."},
            {"timestamp": t1, "summary": "Closer perspective examining the layout, structure, and environment in motion."},
            {"timestamp": t2, "summary": "Key operational highlights and perspective across the middle of the clip."},
            {"timestamp": t3, "summary": "Closing view and final takeaway from the walkthrough."}
        ]

    overview_lines = ["⏱️ AI Video Overview:"]
    for item in timestamp_notes:
        overview_lines.append(f"• {item['timestamp']} — {item['summary']}")
    timestamp_overview_block = vguard.sanitize_text("\n".join(overview_lines))

    return {
        "duration_sec": round(duration, 1),
        "duration_formatted": format_timestamp(duration),
        "timestamps": timestamp_notes,
        "timestamp_overview_block": timestamp_overview_block,
        "visual_summary": primary_vision,
        "thumbnail_path": str(best_thumbnail) if best_thumbnail and best_thumbnail.exists() else None
    }


def generate_platform_post_from_media(
    media_item: Dict[str, Any],
    platform: str,
    persona_instructions: str,
    max_chars: int = 1200,
    include_timestamp_sidebar: bool = True
) -> Dict[str, Any]:
    media_type = media_item["media_type"]
    category = media_item.get("category", "general")
    topic_hint = media_item.get("topic_hint", "")
    sidecar_note = media_item.get("sidecar_note", "")
    visual_summary = media_item.get("visual_summary", "")
    ts_block = media_item.get("timestamp_overview_block", "")

    append_ts = (media_type == "video" and include_timestamp_sidebar and ts_block and max_chars >= 450)
    body_budget = (max_chars - len(ts_block) - 10) if append_ts else max_chars

    prompt = (
        f"You are writing a {platform} post accompanying a {media_type} that was just uploaded.\n"
        f"Persona / Voice: {persona_instructions}\n"
        f"Folder / Theme Category: {category}\n"
    )
    if topic_hint or sidecar_note:
        prompt += f"User Topic / Location Note: {sidecar_note or topic_hint}\n"
    prompt += (
        f"AI Visual Reading of the {media_type.upper()}: {visual_summary}\n"
        f"Rules:\n"
        f"- Write an authentic, engaging {platform} post that naturally reflects what is in this {media_type}.\n"
        f"- {vguard.LLM_PROHIBITION_RULE}\n"
        f"- Strictly under {body_budget} characters.\n"
        f"- Output ONLY the post text (no surrounding quotes, no meta-commentary)."
    )

    generated_text = generate_text_via_llm(prompt, max_chars=body_budget)
    if not generated_text:
        subject = sidecar_note or topic_hint or "today's visual update"
        generated_text = f"Sharing a look at {subject} — {visual_summary}"

    final_text = f"{generated_text.strip()}\n\n{ts_block}".strip() if append_ts else generated_text.strip()
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


def generate_text_via_llm(prompt: str, max_chars: int = 800) -> Optional[str]:
    """Generates text via Pollinations AI or local Ollama with vocabulary safety."""
    if vguard.LLM_PROHIBITION_RULE not in prompt:
        prompt = f"{prompt}\n\n{vguard.LLM_PROHIBITION_RULE}"

    # 1. Try local Ollama first for zero latency & offline autonomy
    if ensure_ollama_running():
        try:
            req = urllib.request.Request(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                data=json.dumps({
                    "model": config.OLLAMA_VISION_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.5, "num_predict": 250}
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

    # 2. Free Cloud fallback
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
                time.sleep(10)
                continue
            break
        except Exception:
            break

    return None


def consume_and_delete_media_item(media_item: Dict[str, Any]) -> bool:
    """Deletes uploaded media file after successful live post to ensure one-time use."""
    if not media_item:
        return False
    deleted = False
    media_path = Path(media_item["path"])
    try:
        if media_path.exists():
            media_path.unlink()
            deleted = True
            logger.info(f"[+] Auto-deleted one-time inbox media: {media_path.name}")
    except Exception as e:
        logger.error(f"Failed to delete inbox media {media_path}: {e}")

    for key in ("sidecar_path", "thumbnail_path"):
        val = media_item.get(key)
        if val and val != str(media_path):
            try:
                p = Path(val)
                if p.exists():
                    p.unlink()
            except Exception:
                pass
    return deleted
