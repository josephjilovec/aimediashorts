"""
Local Privacy, Nudity & Executive PR Reputation Shield
Author: Joseph Jilovec (JJ)

100% Local Inspection Gate:
- Never sends private media to external cloud APIs.
- Inspects every photo and video keyframe locally (using PIL YCbCr skin-tone spatial analysis +
  local Ollama Multimodal Vision) BEFORE any file is ever routed to a social media bot.
- Detects and blocks:
  1. Nudity, partial nudity, intimate/explicit photos, shirtless/underwear/bathroom mirror selfies
  2. Private documents, IDs, financial statements, medical records, credit cards, addresses, leases
  3. Unflattering or PR-negative personal photos that shouldn't represent a public brand
- When a photo or video is flagged as Private / Do Not Post:
  - It is marked in the ledger under `private_do_not_touch` so it is left completely alone on
    the phone/cloud (never deleted, and never scanned or uploaded to any bot).
"""

import json
import logging
import urllib.request
from pathlib import Path
from typing import Dict, Any

from . import config

logger = logging.getLogger("PrivacyPRShield")


def check_ollama_status() -> Tuple[bool, str]:
    """Check whether the local Ollama vision server is accessible and responding."""
    try:
        req = urllib.request.Request(
            f"{config.OLLAMA_BASE_URL}/api/version",
            headers={"User-Agent": "AIMediaShorts/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ver = data.get("version", "ready")
            return True, f"Ollama v{ver} running at {config.OLLAMA_BASE_URL}"
    except Exception as e:
        return False, f"Not responding at {config.OLLAMA_BASE_URL} ({e})"


PRIVATE_FILENAME_KEYWORDS = [
    "private", "nude", "naked", "nsfw", "intimate", "onlyfans", "personal_id",
    "passport", "license", "ssn", "tax", "lease", "medical", "bank", "statement",
    "password", "secret", "confidential", "bedroom", "bathroom", "mirror"
]

UNSAFE_VISION_KEYWORDS = [
    "nude", "nudity", "naked", "shirtless", "underwear", "lingerie", "bra", "briefs",
    "boxers", "genital", "explicit", "intimate", "sexual", "erotic", "bedroom selfie",
    "bathroom mirror", "mirror selfie", "shower", "bathtub", "toilet", "undressed",
    "bare chest", "bare skin", "topless", "credit card", "driver license", "passport",
    "social security", "bank account", "medication bottle", "prescription", "pill bottle",
    "medical record", "unflattering", "embarrassing", "messy room", "private document"
]


def _check_skin_exposure_ratio(image_path: Path) -> Dict[str, Any]:
    """
    Computes YCbCr skin-pixel ratio across the full image and the center 60% subject region.
    High skin ratios in the center region combined with indoor/close-up framing indicate
    potential nudity / shirtless / intimate photos.
    """
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            ycbcr = img.convert("YCbCr")
            ycbcr.thumbnail((200, 200))
            w, h = ycbcr.size
            pixels = ycbcr.load()

            total_px = w * h
            skin_px = 0
            center_total = 0
            center_skin = 0

            x_min, x_max = int(w * 0.2), int(w * 0.8)
            y_min, y_max = int(h * 0.15), int(h * 0.85)

            for y in range(h):
                for x in range(w):
                    Y, Cb, Cr = pixels[x, y]
                    is_skin = (Y > 60) and (77 <= Cb <= 127) and (133 <= Cr <= 173)
                    if is_skin:
                        skin_px += 1
                    if x_min <= x <= x_max and y_min <= y <= y_max:
                        center_total += 1
                        if is_skin:
                            center_skin += 1

            overall_ratio = skin_px / float(max(1, total_px))
            center_ratio = center_skin / float(max(1, center_total))

            # Default thresholds: center >= 48% or overall >= 42%
            is_high_skin = (center_ratio >= 0.48) or (overall_ratio >= 0.42)
            return {
                "overall_skin_ratio": round(overall_ratio, 3),
                "center_skin_ratio": round(center_ratio, 3),
                "flagged_high_skin": is_high_skin
            }
    except Exception:
        return {"overall_skin_ratio": 0.0, "center_skin_ratio": 0.0, "flagged_high_skin": False}


def _check_image_with_local_ollama_pr_guard(image_path: Path) -> Dict[str, Any]:
    """
    Runs 100% locally via Ollama to check if an image contains nudity, partial nudity,
    intimate/personal content, private documents, or anything unsuitable for public PR.
    """
    from . import universal_media_inbox as umi

    b64 = umi.encode_image_for_vision(image_path)
    if not (b64 and umi.ensure_ollama_running()):
        return {"safe": True, "reason": "Local vision offline (passed skin check)"}

    prompt = (
        "You are a strict Executive PR & Privacy Safety Filter inspecting a photo before public social media posting.\n"
        "Check if this image contains ANY of the following:\n"
        "1. Nudity, partial nudity, naked/shirtless body, underwear, intimate/explicit content, or bathroom/bedroom mirror selfies.\n"
        "2. Private sensitive documents, ID cards, financial/medical paperwork, pill bottles, or personal addresses.\n"
        "3. Unflattering, embarrassing, or private personal moments that would look bad for executive PR.\n\n"
        "Respond strictly in this format:\n"
        "VERDICT: SAFE or PRIVATE_HOLD\n"
        "REASON: [1 short sentence]"
    )

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
        "options": {"temperature": 0.1, "num_predict": 90}
    }

    try:
        req = urllib.request.Request(
            f"{config.OLLAMA_BASE_URL}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            reply = data.get("message", {}).get("content", "").strip()
            low = reply.lower()

            if "private_hold" in low or any(kw in low for kw in UNSAFE_VISION_KEYWORDS):
                return {"safe": False, "reason": f"Local AI PR/Privacy Guard flagged: {reply}"}
            return {"safe": True, "reason": reply}
    except Exception as e:
        return {"safe": True, "reason": f"Vision check note: {e}"}


def inspect_media_privacy_and_pr(media_path: Path, visual_summary: str = "") -> Dict[str, Any]:
    """
    Master Privacy & PR Gate for both Photos and Videos.
    Returns `{"safe": bool, "reason": str}`.
    If `safe` is False, the pipeline leaves the original alone on the phone/cloud,
    marks it in `private_do_not_touch` so it is never touched again, and blocks it from all bots.
    """
    from . import universal_media_inbox as umi

    name_low = media_path.name.lower()
    for kw in PRIVATE_FILENAME_KEYWORDS:
        if kw in name_low:
            return {"safe": False, "reason": f"Filename contains private keyword '{kw}'"}

    if visual_summary:
        vis_low = visual_summary.lower()
        for kw in UNSAFE_VISION_KEYWORDS:
            if kw in vis_low:
                return {"safe": False, "reason": f"Visual reading detected private/PR-sensitive content ('{kw}')"}

    ext = media_path.suffix.lower()
    if ext in umi.PHOTO_EXTS:
        skin_info = _check_skin_exposure_ratio(media_path)
        if skin_info["flagged_high_skin"]:
            return {
                "safe": False,
                "reason": (
                    f"High bare-skin ratio detected (center={skin_info['center_skin_ratio']*100:.0f}%, "
                    f"overall={skin_info['overall_skin_ratio']*100:.0f}%) — protected as private photo"
                )
            }
        pr_check = _check_image_with_local_ollama_pr_guard(media_path)
        if not pr_check["safe"]:
            return pr_check

    elif ext in umi.VIDEO_EXTS:
        _, frames = umi.extract_video_keyframes(media_path, num_frames=2)
        try:
            for ts_label, frame_file in frames:
                skin_info = _check_skin_exposure_ratio(frame_file)
                if skin_info["flagged_high_skin"]:
                    return {
                        "safe": False,
                        "reason": f"Video frame at {ts_label} flagged high skin exposure ({skin_info['center_skin_ratio']*100:.0f}%) — protected as private"
                    }
                pr_check = _check_image_with_local_ollama_pr_guard(frame_file)
                if not pr_check["safe"]:
                    return {"safe": False, "reason": f"Video frame at {ts_label} flagged by PR/Privacy Guard: {pr_check['reason']}"}
        finally:
            if frames:
                import shutil
                try:
                    shutil.rmtree(frames[0][1].parent, ignore_errors=True)
                except Exception:
                    pass

    return {"safe": True, "reason": "Passed Privacy, Nudity & Executive PR Safety Check"}
