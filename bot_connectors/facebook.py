"""
Facebook Page / Reels Connector
Publishes photos and 9:16 video reels to Facebook Pages via Graph API.
"""

import os
import sys
import logging
import requests
from pathlib import Path
from typing import Optional

from .base_connector import BaseSocialMediaConnector

logger = logging.getLogger("FacebookConnector")


class FacebookConnector(BaseSocialMediaConnector):
    """
    Automated Facebook Page publisher.
    Uploads curated photos to the page timeline and 9:16 video shorts as reels/videos.
    """

    def __init__(self, dry_run: bool = False):
        super().__init__(platform_name="facebook", dry_run=dry_run)
        self.page_id = os.environ.get("FACEBOOK_PAGE_ID", "")
        self.access_token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
        self.api_version = os.environ.get("FACEBOOK_GRAPH_VERSION", "v19.0")
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

        if not (self.page_id and self.access_token):
            if not self.dry_run:
                logger.warning(
                    "[Facebook] Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN. "
                    "Operating in DRY-RUN mode."
                )
                self.dry_run = True

    def post_image(self, image_path: Path, text: str) -> Optional[str]:
        if self.dry_run:
            logger.info(f"[Facebook DRY-RUN] Posting Image '{image_path.name}' with caption: {text}")
            return "simulated_fb_photo_id"

        url = f"{self.base_url}/{self.page_id}/photos"
        payload = {
            "caption": text,
            "access_token": self.access_token
        }

        try:
            with open(image_path, "rb") as img_file:
                files = {"source": (image_path.name, img_file, "image/jpeg")}
                resp = requests.post(url, data=payload, files=files, timeout=60)
            
            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                return data["id"]
            else:
                logger.error(f"[Facebook] API error posting photo: {data}")
                return None
        except Exception as e:
            logger.error(f"[Facebook] Exception posting photo {image_path.name}: {e}")
            return None

    def post_video(self, video_path: Path, text: str) -> Optional[str]:
        if self.dry_run:
            logger.info(f"[Facebook DRY-RUN] Posting Video Short '{video_path.name}' with description: {text}")
            return "simulated_fb_video_id"

        url = f"https://graph-video.facebook.com/{self.api_version}/{self.page_id}/videos"
        payload = {
            "description": text,
            "access_token": self.access_token
        }

        try:
            with open(video_path, "rb") as vid_file:
                files = {"source": (video_path.name, vid_file, "video/mp4")}
                resp = requests.post(url, data=payload, files=files, timeout=180)

            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                return data["id"]
            else:
                logger.error(f"[Facebook] API error posting video: {data}")
                return None
        except Exception as e:
            logger.error(f"[Facebook] Exception posting video {video_path.name}: {e}")
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    connector = FacebookConnector(dry_run=True)
    results = connector.publish_pending_queue(max_items=3)
    print(f"Facebook dispatch result: {results}")
