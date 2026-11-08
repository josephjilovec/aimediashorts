"""
Universal Social Media Vocabulary Guard
Author: Joseph Jilovec (JJ)

Strict Safety Rule:
Guarantees that words like 'kill', 'killer', 'killers', 'killed', 'killing', and 'kills'
are strictly filtered out of all social media posts, titles, hooks, and video captions.
"""

import re
from typing import Any

BANNED_WORD_RE = re.compile(r"\bkill(?:er|ers|ed|ing|s)?\b", re.IGNORECASE)

LLM_PROHIBITION_RULE = (
    "CRITICAL VOCABULARY RULE: NEVER use the words 'kill', 'killer', 'killers', 'killed', 'killing', or 'kills' "
    "under any circumstances. Use professional alternatives like 'eliminate', 'drain', 'bottleneck', 'halt', "
    "'shut down', 'retire', or 'standout'."
)

PHRASE_REPLACEMENTS = [
    (re.compile(r"\bsilent\s+killers?\s+of\b", re.IGNORECASE), "biggest hidden drain on"),
    (re.compile(r"\bsilent\s+killers?\b", re.IGNORECASE), "hidden drain"),
    (re.compile(r"\bserial\s+killers\b", re.IGNORECASE), "serial offenders"),
    (re.compile(r"\bserial\s+killer\b", re.IGNORECASE), "serial offender"),
    (re.compile(r"\bkiller\s+features?\b", re.IGNORECASE), "standout feature"),
    (re.compile(r"\bkiller\s+apps?\b", re.IGNORECASE), "breakthrough app"),
    (re.compile(r"\bshot\s+and\s+killed\b", re.IGNORECASE), "fatally wounded"),
]


def contains_banned_words(text: str) -> bool:
    if not text:
        return False
    return bool(BANNED_WORD_RE.search(text))


def sanitize_text(text: str) -> str:
    """
    Sanitizes text by replacing off-limit words with clean, professional contextual alternatives.
    """
    if not text or not isinstance(text, str):
        return text

    if not BANNED_WORD_RE.search(text):
        return text

    out = text
    for pattern, repl in PHRASE_REPLACEMENTS:
        out = pattern.sub(repl, out)

    def _replace_word(match: re.Match) -> str:
        word = match.group(0)
        low = word.lower()
        is_title = word[0].isupper() and (len(word) == 1 or word[1:].islower())
        is_upper = word.isupper()

        if low in ("killer", "killers"):
            rep = "major drain" if low == "killer" else "major drains"
        elif low == "kills":
            rep = "eliminates"
        elif low == "killed":
            rep = "lost their lives"
        elif low == "killing":
            rep = "eliminating"
        else:
            rep = "eliminate"

        if is_upper:
            return rep.upper()
        if is_title:
            return rep.capitalize()
        return rep

    return BANNED_WORD_RE.sub(_replace_word, out)


def sanitize_payload(payload: Any) -> Any:
    """Recursively sanitizes strings inside dictionaries or lists returned by content engines."""
    if isinstance(payload, str):
        return sanitize_text(payload)
    if isinstance(payload, dict):
        return {
            k: (
                sanitize_payload(v)
                if k not in ("path", "sidecar_path", "thumbnail_path", "image_path", "video_path", "url")
                else v
            )
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    return payload
