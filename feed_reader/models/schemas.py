"""Data models for feed_reader.

This module defines the core data structures for blogs and articles.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Blog:
    """Represents a blog/feed source."""

    id: int
    name: str
    url: str
    feed_url: Optional[str]
    scrape_selector: Optional[str]
    last_scanned: Optional[datetime]


@dataclass
class Article:
    """Represents an article from a blog/feed."""

    id: int
    blog_id: int
    title: str
    url: str
    published_date: Optional[datetime]
    discovered_date: Optional[datetime]
    is_read: bool
