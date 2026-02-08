"""Feed parser service.

This module parses RSS/Atom feeds and extracts articles.
"""

import httpx
import feedparser
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from email.utils import parsedate_to_datetime

from feed_reader.log_system.unified_logger import UnifiedLogger


@dataclass
class ParsedArticle:
    """Represents a parsed article from a feed."""

    title: str
    url: str
    published_date: Optional[datetime]


async def parse_feed(feed_url: str) -> List[ParsedArticle]:
    """Parse an RSS/Atom feed and extract articles.

    Args:
        feed_url: URL of the feed to parse

    Returns:
        List of ParsedArticle objects
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"Parsing feed: {feed_url}")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "FeedReader/1.0 (RSS Feed Reader)"},
    ) as client:
        try:
            response = await client.get(feed_url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch feed: {e}")
            return []

    # Parse the feed
    feed = feedparser.parse(response.text)

    if feed.bozo and not feed.entries:
        logger.warning(f"Feed parsing error: {feed.bozo_exception}")
        return []

    articles = []
    for entry in feed.entries:
        # Extract title
        title = entry.get("title", "").strip()
        if not title:
            continue

        # Extract URL
        url = entry.get("link", "").strip()
        if not url:
            # Try alternate link
            for link in entry.get("links", []):
                if link.get("rel") == "alternate" or link.get("href"):
                    url = link.get("href", "")
                    break

        if not url:
            continue

        # Extract published date
        published_date = _parse_date(entry)

        articles.append(ParsedArticle(
            title=title,
            url=url,
            published_date=published_date,
        ))

    logger.info(f"Parsed {len(articles)} articles from feed")
    return articles


def _parse_date(entry: dict) -> Optional[datetime]:
    """Parse the publication date from a feed entry.

    Args:
        entry: Feed entry dict

    Returns:
        datetime if parsed successfully, None otherwise
    """
    # Try various date fields
    for field in ["published", "updated", "created"]:
        date_str = entry.get(field, "") or entry.get(f"{field}_parsed")

        if not date_str:
            continue

        # If it's already a time struct (from feedparser)
        if isinstance(date_str, tuple):
            try:
                return datetime(*date_str[:6])
            except (ValueError, TypeError):
                continue

        # Try RFC 2822 format (common in RSS)
        try:
            return parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            pass

        # Try ISO format
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    return None
