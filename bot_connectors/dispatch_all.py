"""
Unified Social Media Bot Dispatcher
Iterates over all enabled social network connectors and publishes pending media from ALL_BOTS_MEDIA_INBOX.
"""

import sys
import logging
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import config
from core import vocabulary_guard
from bot_connectors.twitter_x import TwitterXConnector
from bot_connectors.facebook import FacebookConnector
from bot_connectors.bluesky import BlueskyConnector
from bot_connectors.mastodon import MastodonConnector
from bot_connectors.tumblr import TumblrConnector

logger = logging.getLogger("UnifiedDispatcher")


def dispatch_all(dry_run: bool = False, max_per_network: int = 5):
    config.ensure_workspace()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    logger.info("=" * 60)
    logger.info("Starting Unified Social Media Dispatch")
    logger.info(f"Mode: {'DRY RUN (simulation)' if dry_run else 'LIVE PUBLISH'}")
    logger.info("=" * 60)

    connectors = [
        TwitterXConnector(dry_run=dry_run),
        FacebookConnector(dry_run=dry_run),
        BlueskyConnector(dry_run=dry_run),
        MastodonConnector(dry_run=dry_run),
        TumblrConnector(dry_run=dry_run),
    ]

    summary = {}
    for conn in connectors:
        logger.info(f"\n---> Processing platform: {conn.platform_name.upper()}")
        try:
            res = conn.publish_pending_queue(max_items=max_per_network)
            summary[conn.platform_name] = res
        except Exception as e:
            logger.error(f"Error during {conn.platform_name} dispatch: {e}")
            summary[conn.platform_name] = [{"error": str(e)}]

    logger.info("\n" + "=" * 60)
    logger.info("Dispatch Cycle Complete")
    logger.info("=" * 60)
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Unified Social Media Dispatcher")
    parser.add_argument("--dry-run", action="store_true", help="Simulate posting without publishing to networks")
    parser.add_argument("--max", type=int, default=5, help="Maximum items to post per network per cycle")
    args = parser.parse_args()

    dispatch_all(dry_run=args.dry_run, max_per_network=args.max)
