"""
Mastodon Social Media Connector
Publishes photos and 9:16 video shorts to Mastodon or Fediverse instances.
"""

import os
import sys
import logging
import requests
from pathlib import Path
from typing import Optional

from .base_connector import BaseSocialMediaConnector

logger = logging.getLogger("MastodonConnector")


class MastodonConnector(BaseSocialMediaConnector):
    """
    Automated Mastodon / Fediverse publisher.
    """

    def __init__(self, dry_run: bool = False):
        super().__init__(platform_name="mastodon", dry_run=dry_run)
        self.instance_url = os.environ.get("MASTODON_INSTANCE_URL", "https://mastodon.social").rstrip("/")
        self.access_token = os.environ.get("MASTODON_ACCESS_TOKEN", "")

        if not self.access_token:
            if not self.dry_run:
                logger.warning(
                    "[Mastodon] Missing MASTODON_ACCESS_TOKEN. Operating in DRY-RUN mode."
                )
                self.dry_run = True

    def _upload_media(self, file_path: Path, is_video: bool = False) -> Optional[str]:
        if self.dry_run:
            return "simulated_mastodon_media_id"

        url = f"{self.instance_url}/api/v2/media"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        mime = "video/mp4" if is_video else "image/jpeg"

        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, mime)}
                resp = requests.post(url, headers=headers, files=files, timeout=120)
            if resp.status_code in (200, 202):
                return resp.json().get("id")
            else:
                logger.error(f"[Mastodon] Media upload error: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"[Mastodon] Media upload exception: {e}")
            return None

    def _post_status(self, text: str, media_id: str) -> Optional[str]:
        if self.dry_run:
            logger.info(f"[Mastodon DRY-RUN] Status: '{text}' (Media ID: {media_id})")
            return "simulated_mastodon_status_id"

        url = f"{self.instance_url}/api/v1/statuses"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        payload = {
            "status": text,
            "media_ids": [media_id]
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("id")
            else:
                logger.error(f"[Mastodon] Status post error: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"[Mastodon] Status post exception: {e}")
            return None

    def post_image(self, image_path: Path, text: str) -> Optional[str]:
        media_id = self._upload_media(image_path, is_video=False)
        if not media_id:
            return None
        return self._post_status(text, media_id)

    def post_video(self, video_path: Path, text: str) -> Optional[str]:
        media_id = self._upload_media(video_path, is_video=True)
        if not media_id:
            return None
        return self._post_status(text, media_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    connector = MastodonConnector(dry_run=True)
    results = connector.publish_pending_queue(max_items=3)
    print(f"Mastodon dispatch result: {results}")
