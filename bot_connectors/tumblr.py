"""
Tumblr Social Media Connector
Publishes photos and 9:16 video shorts to Tumblr blogs via API v2.
"""

import os
import sys
import time
import uuid
import hmac
import hashlib
import base64
import logging
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests

from .base_connector import BaseSocialMediaConnector

logger = logging.getLogger("TumblrConnector")


def percent_encode(val: Any) -> str:
    return urllib.parse.quote(str(val), safe="~-._")


class TumblrConnector(BaseSocialMediaConnector):
    """
    Automated Tumblr publisher.
    Uploads curated photos and native 9:16 video shorts via Tumblr API v2.
    """

    def __init__(self, dry_run: bool = False):
        super().__init__(platform_name="tumblr", dry_run=dry_run)
        self.consumer_key = os.environ.get("TUMBLR_CONSUMER_KEY", "")
        self.consumer_secret = os.environ.get("TUMBLR_CONSUMER_SECRET", "")
        self.oauth_token = os.environ.get("TUMBLR_OAUTH_TOKEN", "")
        self.oauth_token_secret = os.environ.get("TUMBLR_OAUTH_TOKEN_SECRET", "")
        self.blog_identifier = os.environ.get("TUMBLR_BLOG_IDENTIFIER", "")
        self.base_url = "https://api.tumblr.com/v2"

        if not (self.consumer_key and self.consumer_secret and self.oauth_token and self.oauth_token_secret and self.blog_identifier):
            if not self.dry_run:
                logger.warning(
                    "[Tumblr] Missing credentials (TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, "
                    "TUMBLR_OAUTH_TOKEN, TUMBLR_OAUTH_TOKEN_SECRET, TUMBLR_BLOG_IDENTIFIER). "
                    "Operating in DRY-RUN mode."
                )
                self.dry_run = True

    def _generate_oauth_header(self, method: str, url: str) -> str:
        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_version": "1.0",
            "oauth_token": self.oauth_token,
        }

        sorted_pairs = sorted(
            [(percent_encode(k), percent_encode(v)) for k, v in oauth_params.items()]
        )
        param_str = "&".join(f"{k}={v}" for k, v in sorted_pairs)

        url_parts = urllib.parse.urlsplit(url)
        clean_url = f"{url_parts.scheme}://{url_parts.netloc}{url_parts.path}"

        base_string = "&".join([
            method.upper(),
            percent_encode(clean_url),
            percent_encode(param_str)
        ])

        key = f"{percent_encode(self.consumer_secret)}&{percent_encode(self.oauth_token_secret)}"
        raw_sig = hmac.new(key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
        sig = base64.b64encode(raw_sig).decode("utf-8")
        oauth_params["oauth_signature"] = sig

        header_pairs = [f'{k}="{percent_encode(v)}"' for k, v in sorted(oauth_params.items())]
        return f"OAuth {', '.join(header_pairs)}"

    def post_image(self, image_path: Path, text: str) -> Optional[str]:
        if self.dry_run:
            logger.info(f"[Tumblr DRY-RUN] Posting Image '{image_path.name}' with caption: {text[:60]}...")
            return "simulated_tumblr_photo_id"

        url = f"{self.base_url}/blog/{self.blog_identifier}/post"
        auth_header = self._generate_oauth_header("POST", url)
        headers = {
            "Authorization": auth_header,
            "User-Agent": "AIMediaShorts/1.0",
        }
        form_data = {
            "type": "photo",
            "caption": f"<p>{text}</p>",
            "state": "published"
        }

        try:
            with open(image_path, "rb") as f:
                files = {"data": (image_path.name, f, "image/jpeg")}
                resp = requests.post(url, headers=headers, data=form_data, files=files, timeout=60)
            data = resp.json()
            if data.get("meta", {}).get("status") in [200, 201]:
                return str(data.get("response", {}).get("id"))
            else:
                logger.error(f"[Tumblr] Image upload failed: {data}")
                return None
        except Exception as e:
            logger.error(f"[Tumblr] Image upload exception: {e}")
            return None

    def post_video(self, video_path: Path, text: str) -> Optional[str]:
        if self.dry_run:
            logger.info(f"[Tumblr DRY-RUN] Posting Video Short '{video_path.name}' with caption: {text[:60]}...")
            return "simulated_tumblr_video_id"

        url = f"{self.base_url}/blog/{self.blog_identifier}/post"
        auth_header = self._generate_oauth_header("POST", url)
        headers = {
            "Authorization": auth_header,
            "User-Agent": "AIMediaShorts/1.0",
        }
        form_data = {
            "type": "video",
            "caption": f"<p>{text}</p>",
            "state": "published"
        }

        try:
            logger.info(f"[Tumblr] Uploading video file '{video_path.name}' to Tumblr servers...")
            with open(video_path, "rb") as f:
                files = {"data": (video_path.name, f, "video/mp4")}
                resp = requests.post(url, headers=headers, data=form_data, files=files, timeout=180)
            data = resp.json()
            if data.get("meta", {}).get("status") in [200, 201]:
                post_id = str(data.get("response", {}).get("id"))
                post_state = data.get("response", {}).get("state", "published")
                if post_state == "transcoding":
                    logger.info(f"[+] Video accepted by Tumblr! (Status: Transcoding/Buffering). Post ID: {post_id}")
                else:
                    logger.info(f"[+] Video posted successfully! Post ID: {post_id}")
                return post_id
            else:
                logger.error(f"[Tumblr] Video upload failed: {data}")
                return None
        except Exception as e:
            logger.error(f"[Tumblr] Video upload exception: {e}")
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    connector = TumblrConnector(dry_run=True)
    results = connector.publish_pending_queue(max_items=3)
    print(f"Tumblr dispatch result: {results}")
