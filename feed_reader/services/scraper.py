"""HTML scraper service.

This module scrapes blog pages to extract article links using CSS selectors.
"""

import httpx
from bs4 import BeautifulSoup
from typing import List
from urllib.parse import urljoin

from feed_reader.services.feed_parser import ParsedArticle
from feed_reader.log_system.unified_logger import UnifiedLogger


async def scrape_blog(url: str, css_selector: str) -> List[ParsedArticle]:
    """Scrape a blog page for article links using a CSS selector.

    Args:
        url: URL of the page to scrape
        css_selector: CSS selector to find article links

    Returns:
        List of ParsedArticle objects (without published dates)
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"Scraping blog: {url} with selector: {css_selector}")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "FeedReader/1.0 (Blog Scraper)"},
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch page: {e}")
            return []

    soup = BeautifulSoup(response.text, "lxml")

    # Find all elements matching the selector
    elements = soup.select(css_selector)

    if not elements:
        logger.warning(f"No elements found matching selector: {css_selector}")
        return []

    articles = []
    seen_urls = set()

    for element in elements:
        # Find the link - either the element itself or a child <a> tag
        if element.name == "a":
            link = element
        else:
            link = element.find("a")

        if not link:
            continue

        href = link.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue

        # Resolve to absolute URL
        absolute_url = urljoin(url, href)

        # Skip duplicates
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)

        # Extract title from link text or parent element
        title = link.get_text(strip=True)
        if not title:
            # Try getting text from parent element
            title = element.get_text(strip=True)

        if not title:
            # Use URL as fallback title
            title = absolute_url.split("/")[-1] or absolute_url

        articles.append(ParsedArticle(
            title=title,
            url=absolute_url,
            published_date=None,  # Scraping doesn't provide dates
        ))

    logger.info(f"Scraped {len(articles)} articles from page")
    return articles
