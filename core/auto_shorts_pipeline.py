"""
AI Auto-Shorts Clipper, Best-Shot Curator & Multi-Bot Social Media Pipeline
Author: Joseph Jilovec (JJ)
"""

import os
import re
import sys
import json
import time
import shutil
import logging
import requests
import webbrowser
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from . import config
from . import universal_media_inbox as umi
from . import vocabulary_guard as vguard
from . import privacy_and_pr_shield as pr_shield

PHONE_CAMERA_FILENAME_RE = re.compile(
    r"^(1000\d{4,}|PXL_|IMG_|VID_|MOV_|DSC_|DCIM_|Snapchat|\d{8}_\d{6})",
    re.IGNORECASE
)

SCREENSHOT_FILENAME_RE = re.compile(r"^(Screenshot|Screen_Recording)", re.IGNORECASE)
BURST_TIMESTAMP_RE = re.compile(r"(?:PXL|IMG|VID|DSC)_?(\d{8})_?(\d{4})\d*", re.IGNORECASE)

logger = logging.getLogger("AutoShortsPipeline")


def setup_logging():
    config.ensure_workspace()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def load_ledger() -> Dict[str, Any]:
    if config.LEDGER_FILE.exists():
        try:
            return json.loads(config.LEDGER_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "initialized_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "processed_ids": [],
        "processed_files": [],
        "private_do_not_touch": []
    }


def save_ledger(ledger: Dict[str, Any]):
    try:
        config.LEDGER_FILE.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not save ledger: {e}")


def get_valid_google_access_token() -> Optional[str]:
    """Retrieves or refreshes a valid Google OAuth Access Token."""
    # 1. Check local token file
    tok_file = config.PACKAGE_ROOT / "google_photos_token.json"
    tok_info = {}
    if tok_file.exists():
        try:
            tok_info = json.loads(tok_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 2. Check system vault fallback
    if not tok_info:
        vault_p = Path.home() / ".summithill-credentials.json"
        if vault_p.exists():
            try:
                v = json.loads(vault_p.read_text(encoding="utf-8"))
                tok_info = v.get("googlePhotosOAuthToken", {})
            except Exception:
                pass

    if not tok_info:
        return None

    refresh_token = tok_info.get("refresh_token") or os.environ.get("GOOGLE_PHOTOS_REFRESH_TOKEN")
    client_id = tok_info.get("client_id") or os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = tok_info.get("client_secret") or os.environ.get("GOOGLE_CLIENT_SECRET")

    if not (refresh_token and client_id and client_secret):
        return tok_info.get("token")

    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("access_token")
    except Exception as e:
        logger.warning(f"Google OAuth token refresh note: {e}")
        return tok_info.get("token")


# ==============================================================================
# AI BEST-SHOT & BURST CURATOR
# ==============================================================================

def score_photo_quality(filepath: Path) -> Dict[str, Any]:
    """Computes an objective 0-100 visual quality score based on sharpness, exposure, and contrast."""
    if SCREENSHOT_FILENAME_RE.match(filepath.name):
        return {"score": 10.0, "reason": "Phone UI Screenshot (auto-skipped)", "keep": False}

    try:
        from PIL import Image, ImageFilter, ImageStat
        with Image.open(filepath) as img:
            w, h = img.size
            if w < 400 or h < 400:
                return {"score": 15.0, "reason": f"Low resolution ({w}x{h})", "keep": False}

            rgb = img.convert("RGB")
            thumb = rgb.copy()
            thumb.thumbnail((512, 512))

            stat = ImageStat.Stat(thumb)
            r_m, g_m, b_m = stat.mean
            lum = 0.299 * r_m + 0.587 * g_m + 0.114 * b_m

            if lum < 18:
                return {"score": 18.0, "reason": "Too dark / pocket shot", "keep": False}
            if lum > 242:
                return {"score": 20.0, "reason": "Overexposed / washed out", "keep": False}

            exposure_score = max(0.0, 30.0 - abs(lum - 128.0) * 0.22)

            edges = thumb.convert("L").filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            edge_mean = edge_stat.mean[0]
            edge_std = edge_stat.stddev[0]
            sharpness_score = min(45.0, (edge_mean * 0.8 + edge_std * 0.6))

            contrast_std = sum(stat.stddev) / 3.0
            contrast_score = min(25.0, contrast_std * 0.4)

            total_score = round(exposure_score + sharpness_score + contrast_score, 1)
            keep = total_score >= 34.0
            return {
                "score": total_score,
                "sharpness": round(sharpness_score, 1),
                "exposure": round(exposure_score, 1),
                "reason": "Crisp high-signal shot" if keep else "Blurry or low-contrast shot",
                "keep": keep
            }
    except Exception as e:
        return {"score": 50.0, "reason": f"Default pass ({e})", "keep": True}


def get_burst_group_key(filepath: Path) -> str:
    m = BURST_TIMESTAMP_RE.search(filepath.stem)
    if m:
        date_part = m.group(1)
        hhmm = m.group(2)
        try:
            mins = int(hhmm[:2]) * 60 + int(hhmm[2:])
            bucket = mins // 2
            return f"burst_{date_part}_{bucket}"
        except Exception:
            return f"burst_{date_part}_{hhmm}"
    try:
        mtime_bucket = int(filepath.stat().st_mtime) // 120
        return f"mtime_{mtime_bucket}"
    except Exception:
        return filepath.stem


def curate_best_media_batch(raw_files: List[Path], max_winners: int = 8) -> List[Path]:
    """Filters screenshots/blurry shots, deduplicates bursts, and picks only the #1 sharpest photo."""
    if len(raw_files) <= 1:
        return raw_files

    logger.info(f"[AI Best-Shot Curator] Evaluating {len(raw_files)} items to pick the best shots...")
    videos: List[Path] = []
    burst_groups: Dict[str, List[Tuple[float, Path, str]]] = {}
    rejected: List[Path] = []
    ledger = load_ledger()
    private_ignored = set(ledger.get("private_do_not_touch", []))

    for f in raw_files:
        # Privacy & PR Shield Gate
        shield_res = pr_shield.inspect_media_privacy_and_pr(f)
        if not shield_res["safe"]:
            logger.info(
                f"[Privacy & PR Shield] PROTECTED PRIVATE MEDIA '{f.name}' ({shield_res['reason']}). "
                f"Marked 'Leave Alone' and blocked from bots."
            )
            private_ignored.add(f.name)
            rejected.append(f)
            continue

        ext = f.suffix.lower()
        if ext in umi.VIDEO_EXTS:
            if SCREENSHOT_FILENAME_RE.match(f.name):
                rejected.append(f)
            else:
                videos.append(f)
        else:
            q = score_photo_quality(f)
            if not q["keep"]:
                logger.info(f"[AI Curator] Skipping '{f.name}' (Score {q['score']}: {q['reason']})")
                rejected.append(f)
            else:
                bkey = get_burst_group_key(f)
                burst_groups.setdefault(bkey, []).append((q["score"], f, q["reason"]))

    winning_photos: List[Tuple[float, Path]] = []
    for bkey, candidates in burst_groups.items():
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_file, _ = candidates[0]
        winning_photos.append((best_score, best_file))
        if len(candidates) > 1:
            logger.info(
                f"[AI Curator] Burst '{bkey}' ({len(candidates)} shots) -> Picked #1: '{best_file.name}' (Score {best_score})"
            )
            for _, loser_file, _ in candidates[1:]:
                rejected.append(loser_file)

    winning_photos.sort(key=lambda x: x[0], reverse=True)
    top_photos = [p for _, p in winning_photos[:max_winners]]
    for _, extra_photo in winning_photos[max_winners:]:
        rejected.append(extra_photo)

    if config.AUTO_DELETE_LOCAL_ORIGINALS_AFTER_ROUTING:
        for rej in rejected:
            try:
                if rej.exists():
                    rej.unlink()
            except Exception:
                pass

    ledger["private_do_not_touch"] = list(private_ignored)[-2000:]
    save_ledger(ledger)

    final_selection = videos + top_photos
    logger.info(
        f"[AI Best-Shot Curator] Selected {len(final_selection)} winners "
        f"({len(videos)} videos, {len(top_photos)} top photos; filtered {len(rejected)} duplicates/screenshots)."
    )
    return final_selection


# ==============================================================================
# 9:16 VERTICAL HD AUTO-SHORTS CLIPPER (FFmpeg)
# ==============================================================================

def create_vertical_9x16_short_clip(
    input_video: Path,
    output_video: Path,
    start_sec: float = 0.0,
    duration_sec: float = 28.0
) -> bool:
    """
    Renders a vertical 9:16 HD Short (1080x1920) with blurred cinematic letterboxing
    and uncropped centered foreground.
    """
    ffmpeg_bin = config.get_ffmpeg_binary()
    if not ffmpeg_bin:
        logger.error("FFmpeg binary not found! Please install FFmpeg.")
        return False

    vf_filter = (
        "split[original][copy];"
        "[copy]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[blurred];"
        "[original]scale=1080:1920:force_original_aspect_ratio=decrease[scaled];"
        "[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
    )

    cmd = [
        ffmpeg_bin, "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", umi.to_ffmpeg_path(input_video),
        "-t", f"{duration_sec:.2f}",
        "-filter_complex", vf_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        umi.to_ffmpeg_path(output_video)
    ]

    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
            creationflags=flags
        )
        if res.returncode == 0 and output_video.exists() and output_video.stat().st_size > 5000:
            return True
        else:
            logger.warning(f"FFmpeg 9:16 filter note: {res.stderr[-200:]}")
    except Exception as e:
        logger.warning(f"FFmpeg render error: {e}")

    # Fallback to copy trim
    try:
        subprocess.run(
            [
                ffmpeg_bin, "-y",
                "-ss", f"{start_sec:.2f}",
                "-i", umi.to_ffmpeg_path(input_video),
                "-t", f"{duration_sec:.2f}",
                "-c", "copy",
                umi.to_ffmpeg_path(output_video)
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            creationflags=flags
        )
        return output_video.exists() and output_video.stat().st_size > 1000
    except Exception:
        return False


def chop_video_into_shorts(video_path: Path) -> List[Path]:
    """Slices a raw video into 1 to 3 vertical 9:16 Shorts based on duration."""
    duration = umi.probe_video_duration_seconds(video_path)
    logger.info(f"[Auto-Shorts Clipper] Video '{video_path.name}' duration: {duration:.1f}s")

    segments: List[Tuple[float, float, str]] = []
    if duration <= 35.0:
        segments.append((0.0, duration, "full_short"))
    elif duration <= 90.0:
        half = round(duration / 2.0, 1)
        segments.append((0.0, min(28.0, half), "part1_opening"))
        segments.append((half, min(28.0, duration - half), "part2_highlight"))
    else:
        s1 = 0.0
        s2 = round(duration * 0.38, 1)
        s3 = round(duration * 0.72, 1)
        segments.append((s1, 26.0, "clip1_intro"))
        segments.append((s2, 26.0, "clip2_mid_action"))
        segments.append((s3, min(26.0, duration - s3), "clip3_finale"))

    exported_shorts: List[Path] = []
    for start_t, dur_t, tag in segments:
        out_name = f"{video_path.stem}_{tag}_9x16.mp4"
        out_path = config.PROCESSED_SHORTS_DIR / out_name
        logger.info(f"[Auto-Shorts Clipper] Rendering 9:16 Vertical Short: {out_name}...")
        if create_vertical_9x16_short_clip(video_path, out_path, start_sec=start_t, duration_sec=dur_t):
            exported_shorts.append(out_path)
            logger.info(f"[+] Exported Short: {out_path}")

    return exported_shorts or [video_path]


# ==============================================================================
# CONTENT CLASSIFIER & BOT ROUTER
# ==============================================================================

def classify_media_for_bots(visual_summary: str, filename_hint: str) -> Dict[str, Any]:
    combined = f"{visual_summary} {filename_hint}".lower()
    routes: List[str] = []

    if any(k in combined for k in ["helicopter", "aircraft", "chopper", "rotor", "sky", "flying", "aerial", "drone", "street", "city"]):
        routes.extend(["Twitter_Main_JosephJilovec", "Facebook", "Bluesky", "Tumblr", "Mastodon"])
        category_label = "Real-World Aerial & Field Observation"
    elif any(k in combined for k in ["space", "orbit", "mothership", "starship", "rocket", "astronomy", "satellite"]):
        routes.extend(["Twitter_AltAccount_SpaceMothership", "Tumblr", "Facebook", "Bluesky"])
        category_label = "Deep-Space & Aerospace Engineering"
    elif any(k in combined for k in ["cannabis", "hemp", "terpene", "dispensary", "plant", "cultivation", "strain"]):
        routes.extend(["Twitter_CannaLog", "Tumblr"])
        category_label = "Botanical & Cultivation Operations"
    elif any(k in combined for k in ["code", "screen", "dashboard", "healthcare", "compliance", "server", "architecture"]):
        routes.extend(["LinkedIn", "Twitter_Main_JosephJilovec", "Facebook", "Bluesky", "Mastodon"])
        category_label = "Enterprise Systems Architecture"
    else:
        routes.extend(["Twitter_Main_JosephJilovec", "Facebook", "Tumblr", "Bluesky"])
        category_label = "Visual Update & Field Perspective"

    unique_routes = []
    for r in routes:
        if r not in unique_routes:
            unique_routes.append(r)

    return {"target_bots": unique_routes, "category_label": category_label}


def route_media_to_bot_queues(media_path: Path, sidecar_note: str = "") -> Dict[str, Any]:
    ext = media_path.suffix.lower()
    is_video = ext in umi.VIDEO_EXTS
    hint = sidecar_note or umi.extract_topic_hint_from_filename(media_path)

    if is_video:
        vid_info = umi.analyze_video_with_timestamps(media_path, hint=hint)
        visual_summary = vguard.sanitize_text(vid_info.get("visual_summary", ""))
        ts_overview = vguard.sanitize_text(vid_info.get("timestamp_overview_block", ""))
    else:
        visual_summary = vguard.sanitize_text(umi.analyze_image_with_vision(media_path, hint=hint))
        ts_overview = ""

    # Second PR Shield Check on generated visual summary
    shield_res = pr_shield.inspect_media_privacy_and_pr(media_path, visual_summary=visual_summary)
    if not shield_res["safe"]:
        logger.info(f"[Privacy & PR Shield] Blocked '{media_path.name}' from queues ({shield_res['reason']}).")
        return {"file": media_path.name, "category": "Blocked (Private)", "routed_to": []}

    routing = classify_media_for_bots(visual_summary, hint)
    target_bots = routing["target_bots"]
    category_label = routing["category_label"]

    context_text = f"Category: {category_label}\n"
    if hint:
        context_text += f"Context Note: {vguard.sanitize_text(hint)}\n"
    context_text += f"AI Visual Summary: {visual_summary}\n"
    if ts_overview:
        context_text += f"\n{ts_overview}\n"

    delivered_to: List[str] = []
    for bot_folder_name in target_bots:
        bot_inbox = config.ALL_BOTS_INBOX / bot_folder_name
        bot_inbox.mkdir(parents=True, exist_ok=True)
        dest_media = bot_inbox / media_path.name
        dest_txt = dest_media.with_suffix(".txt")
        try:
            shutil.copy2(media_path, dest_media)
            dest_txt.write_text(context_text, encoding="utf-8")
            delivered_to.append(bot_folder_name)
        except Exception as e:
            logger.warning(f"Failed routing {media_path.name} to {bot_folder_name}: {e}")

    logger.info(f"[Bot Router] Routed '{media_path.name}' ({category_label}) -> {', '.join(delivered_to)}")
    return {
        "file": media_path.name,
        "category": category_label,
        "visual_summary": visual_summary,
        "routed_to": delivered_to
    }


# ==============================================================================
# SYNC RUNNER
# ==============================================================================

def sync_from_google_drive() -> List[Path]:
    """Copies any new photos/videos from mounted Google Drive."""
    copied: List[Path] = []
    g_inbox = config.get_gdrive_inbox_dir()
    ledger = load_ledger()
    processed_files = set(ledger.get("processed_files", []))
    private_ignored = set(ledger.get("private_do_not_touch", []))

    if g_inbox and g_inbox.exists():
        for entry in g_inbox.iterdir():
            if entry.is_file() and not entry.name.startswith(".") and entry.suffix.lower() in umi.ALL_MEDIA_EXTS:
                sig = f"{entry.name}_{entry.stat().st_size}"
                if sig in private_ignored or entry.name in private_ignored:
                    continue

                shield = pr_shield.inspect_media_privacy_and_pr(entry)
                if not shield["safe"]:
                    logger.info(f"[Privacy Shield] Leaving '{entry.name}' ALONE in Drive ({shield['reason']}).")
                    private_ignored.add(sig)
                    private_ignored.add(entry.name)
                    continue

                dest = config.RAW_INBOX_DIR / entry.name
                try:
                    if sig not in processed_files:
                        shutil.copy2(entry, dest)
                        copied.append(dest)
                        processed_files.add(sig)
                        logger.info(f"[Google Drive Inbox] Pulled: {entry.name}")
                    if config.AUTO_DELETE_GDRIVE_INBOX_AFTER_PULL and dest.exists():
                        entry.unlink()
                except Exception as e:
                    logger.warning(f"Drive pull note ({entry.name}): {e}")

    ledger["processed_files"] = list(processed_files)[-2000:]
    ledger["private_do_not_touch"] = list(private_ignored)[-2000:]
    save_ledger(ledger)
    return copied


def run_pipeline() -> List[Dict[str, Any]]:
    setup_logging()
    config.ensure_workspace()
    logger.info("=" * 72)
    logger.info(" Starting AI Auto-Shorts, Best-Shot Curator & Multi-Bot Pipeline...")
    logger.info("=" * 72)

    sync_from_google_drive()

    all_raw_files = sorted(
        [
            f for f in config.RAW_INBOX_DIR.iterdir()
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in umi.ALL_MEDIA_EXTS
        ],
        key=lambda x: x.stat().st_mtime
    )

    if not all_raw_files:
        logger.info("[*] No new raw media waiting in Phone_Raw_Inbox.")
        return []

    curated_files = curate_best_media_batch(all_raw_files, max_winners=config.MAX_CURATED_PHOTOS_PER_BATCH)
    results: List[Dict[str, Any]] = []

    for raw_file in curated_files:
        if not raw_file.exists():
            continue
        sidecar_txt = raw_file.with_suffix(".txt")
        sidecar_note = sidecar_txt.read_text(encoding="utf-8").strip() if sidecar_txt.exists() else ""

        ext = raw_file.suffix.lower()
        if ext in umi.VIDEO_EXTS:
            shorts = chop_video_into_shorts(raw_file)
            for short_clip in shorts:
                res = route_media_to_bot_queues(short_clip, sidecar_note=sidecar_note)
                results.append(res)
                if config.AUTO_DELETE_LOCAL_ORIGINALS_AFTER_ROUTING and short_clip != raw_file and short_clip.exists():
                    try:
                        short_clip.unlink()
                    except Exception:
                        pass
        else:
            res = route_media_to_bot_queues(raw_file, sidecar_note=sidecar_note)
            results.append(res)

        if config.AUTO_DELETE_LOCAL_ORIGINALS_AFTER_ROUTING and raw_file.exists():
            try:
                raw_file.unlink()
                if sidecar_txt.exists():
                    sidecar_txt.unlink()
            except Exception:
                pass

    logger.info(f"[+] Pipeline complete! Processed {len(results)} items.")
    return results


if __name__ == "__main__":
    run_pipeline()
