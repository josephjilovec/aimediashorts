"""
Bluesky Social Media Connector
Publishes curated images and updates to Bluesky using the AT Protocol REST API.
"""

import os
import sys
import logging
import requests
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from .base_connector import BaseSocialMediaConnector

logger = logging.getLogger("BlueskyConnector")


class BlueskyConnector(BaseSocialMediaConnector):
    """
    Automated Bluesky publisher via AT Protocol API.
    """

    def __init__(self, dry_run: bool = False):
        super().__init__(platform_name="bluesky", dry_run=dry_run)
        self.handle = os.environ.get("BLUESKY_HANDLE", "")
        self.app_password = os.environ.get("BLUESKY_APP_PASSWORD", "")
        self.base_url = "https://bsky.social/xrpc"
        self.access_jwt = None
        self.did = None

        if not (self.handle and self.app_password):
            if not self.dry_run:
                logger.warning(
                    "[Bluesky] Missing BLUESKY_HANDLE or BLUESKY_APP_PASSWORD. "
                    "Operating in DRY-RUN mode."
                )
                self.dry_run = True

    def _authenticate(self) -> bool:
        if self.access_jwt:
            return True
        if self.dry_run:
            return False

        url = f"{self.base_url}/com.atproto.server.createSession"
        try:
            resp = requests.post(
                url,
                json={"identifier": self.handle, "password": self.app_password},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                self.access_jwt = data.get("accessJwt")
                self.did = data.get("did")
                return True
            else:
                logger.error(f"[Bluesky] Auth failed: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[Bluesky] Auth exception: {e}")
            return False

    def _upload_blob(self, file_path: Path, mime_type: str = "image/jpeg") -> Optional[dict]:
        if not self._authenticate():
            return None

        url = f"{self.base_url}/com.atproto.repo.uploadBlob"
        headers = {
            "Authorization": f"Bearer {self.access_jwt}",
            "Content-Type": mime_type,
        }
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            resp = requests.post(url, headers=headers, data=data, timeout=60)
            if resp.status_code == 200:
                return resp.json().get("blob")
            else:
                logger.error(f"[Bluesky] Upload blob failed: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"[Bluesky] Upload blob exception: {e}")
            return None

    def post_image(self, image_path: Path, text: str) -> Optional[str]:
        if self.dry_run:
            logger.info(f"[Bluesky DRY-RUN] Posting Image '{image_path.name}' with text: {text}")
            return "simulated_bsky_uri"

        if not self._authenticate():
            return None

        blob = self._upload_blob(image_path, "image/jpeg")
        if not blob:
            return None

        url = f"{self.base_url}/com.atproto.repo.createRecord"
        headers = {
            "Authorization": f"Bearer {self.access_jwt}",
            "Content-Type": "application/json",
        }

        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "embed": {
                "$type": "app.bsky.embed.images",
                "images": [
                    {
                        "alt": image_path.stem.replace("_", " "),
                        "image": blob,
                    }
                ]
            }
        }

        payload = {
            "repo": self.did,
            "collection": "app.bsky.feed.post",
            "record": record,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                return resp.json().get("uri")
            else:
                logger.error(f"[Bluesky] Create record failed: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"[Bluesky] Create post exception: {e}")
            return None

    def post_video(self, video_path: Path, text: str) -> Optional[str]:
        # Bluesky video posting is rolling out; fallback to image preview + link or status
        logger.info(f"[Bluesky] Video short posting via Bluesky: {video_path.name}")
        return self.post_image(video_path, text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    connector = BlueskyConnector(dry_run=True)
    results = connector.publish_pending_queue(max_items=3)
    print(f"Bluesky dispatch result: {results}")
