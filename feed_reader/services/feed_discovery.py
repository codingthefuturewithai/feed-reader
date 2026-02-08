"""Feed discovery service.

This module discovers RSS/Atom feed URLs from a blog homepage.
"""

import httpx
from typing import Optional
from bs4 import BeautifulSoup
import feedparser

from feed_reader.log_system.unified_logger import UnifiedLogger


# Common feed paths to probe
COMMON_FEED_PATHS = [
    "/feed",
    "/rss",
    "/feed.xml",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
    "/feeds/posts/default",  # Blogger
    "/feed/",
    "/rss/",
    "/?feed=rss2",  # WordPress
    "/blog/feed",
    "/blog/rss",
]

# Feed MIME types to look for in <link> tags
FEED_MIME_TYPES = [
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
    "application/xml",
    "text/xml",
]


async def discover_feed_url(url: str) -> Optional[str]:
    """Discover the RSS/Atom feed URL for a blog.

    1. Fetches the homepage HTML
    2. Looks for <link rel="alternate"> with feed MIME types
    3. If not found, probes common feed paths
    4. Validates by attempting to parse as feed

    Args:
        url: Homepage URL of the blog

    Returns:
        Feed URL if found and valid, None otherwise
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"Discovering feed URL for: {url}")

    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Remove trailing slash for consistent path joining
    base_url = url.rstrip("/")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "FeedReader/1.0 (RSS Feed Discovery)"},
    ) as client:
        # Step 1: Fetch homepage and look for <link> tags
        try:
            response = await client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            # Look for feed links in <link> tags
            for link in soup.find_all("link", rel=lambda x: x and "alternate" in x):
                link_type = link.get("type", "").lower()
                href = link.get("href", "")

                if any(mime in link_type for mime in FEED_MIME_TYPES) and href:
                    # Resolve relative URLs
                    if href.startswith("/"):
                        feed_url = base_url + href
                    elif href.startswith("http"):
                        feed_url = href
                    else:
                        feed_url = base_url + "/" + href

                    # Validate the feed
                    if await _validate_feed(client, feed_url):
                        logger.info(f"Found feed via link tag: {feed_url}")
                        return feed_url

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch homepage: {e}")

        # Step 2: Probe common feed paths
        for path in COMMON_FEED_PATHS:
            feed_url = base_url + path
            if await _validate_feed(client, feed_url):
                logger.info(f"Found feed via path probing: {feed_url}")
                return feed_url

    logger.info(f"No feed found for: {url}")
    return None


async def _validate_feed(client: httpx.AsyncClient, feed_url: str) -> bool:
    """Validate that a URL returns a valid RSS/Atom feed.

    Args:
        client: HTTP client
        feed_url: URL to validate

    Returns:
        True if the URL returns a valid feed
    """
    try:
        response = await client.get(feed_url)
        if response.status_code != 200:
            return False

        # Try to parse as feed
        feed = feedparser.parse(response.text)

        # Check if it has entries or feed metadata
        if feed.bozo and not feed.entries:
            return False

        # Valid feed should have title or entries
        return bool(feed.feed.get("title") or feed.entries)

    except Exception:
        return False
