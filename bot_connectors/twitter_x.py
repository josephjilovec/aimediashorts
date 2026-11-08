"""
Twitter / X Social Media Connector
Publishes photos and 9:16 video shorts to Twitter / X using official API v1.1/v2 endpoints.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional

from .base_connector import BaseSocialMediaConnector

logger = logging.getLogger("TwitterConnector")


class TwitterXConnector(BaseSocialMediaConnector):
    """
    Automated Twitter/X publisher.
    Supports single photos and 9:16 vertical video clips.
    """

    def __init__(self, dry_run: bool = False):
        super().__init__(platform_name="twitter", dry_run=dry_run)
        self.api_key = os.environ.get("TWITTER_API_KEY", "")
        self.api_secret = os.environ.get("TWITTER_API_SECRET", "")
        self.access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
        self.access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")
        self.client = None
        self._init_client()

    def _init_client(self):
        if not (self.api_key and self.api_secret and self.access_token and self.access_token_secret):
            if not self.dry_run:
                logger.warning(
                    "[Twitter/X] Missing credentials (TWITTER_API_KEY, TWITTER_API_SECRET, "
                    "TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET). Operating in DRY-RUN mode."
                )
                self.dry_run = True
            return

        try:
            import tweepy
            auth = tweepy.OAuth1UserHandler(
                self.api_key, self.api_secret, self.access_token, self.access_token_secret
            )
            self.v1_api = tweepy.API(auth)
            self.v2_client = tweepy.Client(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
            )
            logger.info("[Twitter/X] Tweepy client initialized successfully.")
        except ImportError:
            logger.warning("[Twitter/X] 'tweepy' library not installed. Run 'pip install tweepy' to enable real Twitter posting.")
            self.dry_run = True
        except Exception as e:
            logger.error(f"[Twitter/X] Failed to authenticate: {e}")
            self.dry_run = True

    def post_image(self, image_path: Path, text: str) -> Optional[str]:
        if self.dry_run:
            logger.info(f"[Twitter/X DRY-RUN] Posting Image '{image_path.name}' with text: {text}")
            return "simulated_tweet_img_id"

        try:
            # Upload media via v1.1 endpoint
            media = self.v1_api.media_upload(filename=str(image_path))
            # Create tweet via v2 endpoint
            response = self.v2_client.create_tweet(text=text, media_ids=[media.media_id])
            return str(response.data["id"])
        except Exception as e:
            logger.error(f"[Twitter/X] Error posting image {image_path.name}: {e}")
            return None

    def post_video(self, video_path: Path, text: str) -> Optional[str]:
        if self.dry_run:
            logger.info(f"[Twitter/X DRY-RUN] Posting Video Short '{video_path.name}' with text: {text}")
            return "simulated_tweet_vid_id"

        try:
            # Chunked video upload via v1.1
            media = self.v1_api.media_upload(
                filename=str(video_path),
                media_category="tweet_video"
            )
            response = self.v2_client.create_tweet(text=text, media_ids=[media.media_id])
            return str(response.data["id"])
        except Exception as e:
            logger.error(f"[Twitter/X] Error posting video {video_path.name}: {e}")
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    connector = TwitterXConnector(dry_run=True)
    results = connector.publish_pending_queue(max_items=3)
    print(f"Twitter dispatch result: {results}")
