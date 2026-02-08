"""Unit tests for feed services.

Tests for feed discovery, feed parsing, and HTML scraping services.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from feed_reader.services.feed_discovery import discover_feed_url, _validate_feed
from feed_reader.services.feed_parser import parse_feed, ParsedArticle, _parse_date
from feed_reader.services.scraper import scrape_blog


# Mark all tests as async
pytestmark = pytest.mark.anyio


class TestFeedDiscovery:
    """Tests for feed URL discovery."""

    async def test_discover_feed_from_link_tag(self):
        """Test discovery via <link rel="alternate"> tag."""
        html = """
        <html>
        <head>
            <link rel="alternate" type="application/rss+xml" href="/feed.xml">
        </head>
        <body></body>
        </html>
        """

        rss_feed = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test Blog</title>
                <item><title>Post 1</title><link>https://example.com/post1</link></item>
            </channel>
        </rss>
        """

        mock_response_html = MagicMock()
        mock_response_html.status_code = 200
        mock_response_html.text = html
        mock_response_html.raise_for_status = MagicMock()

        mock_response_feed = MagicMock()
        mock_response_feed.status_code = 200
        mock_response_feed.text = rss_feed
        mock_response_feed.raise_for_status = MagicMock()

        async def mock_get(url, **kwargs):
            if url.endswith("/feed.xml"):
                return mock_response_feed
            return mock_response_html

        with patch("feed_reader.services.feed_discovery.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await discover_feed_url("https://example.com")

            assert result == "https://example.com/feed.xml"

    async def test_discover_feed_via_path_probing(self):
        """Test discovery via common path probing when no link tag exists."""
        html = "<html><head></head><body></body></html>"

        rss_feed = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test Blog</title>
                <item><title>Post 1</title><link>https://example.com/post1</link></item>
            </channel>
        </rss>
        """

        mock_response_html = MagicMock()
        mock_response_html.status_code = 200
        mock_response_html.text = html
        mock_response_html.raise_for_status = MagicMock()

        mock_response_feed = MagicMock()
        mock_response_feed.status_code = 200
        mock_response_feed.text = rss_feed

        mock_response_404 = MagicMock()
        mock_response_404.status_code = 404

        async def mock_get(url, **kwargs):
            if url == "https://example.com":
                return mock_response_html
            elif url == "https://example.com/feed":
                return mock_response_feed
            return mock_response_404

        with patch("feed_reader.services.feed_discovery.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await discover_feed_url("https://example.com")

            assert result == "https://example.com/feed"

    async def test_discover_feed_none_found(self):
        """Test returns None when no feed is found."""
        html = "<html><head></head><body></body></html>"

        mock_response_html = MagicMock()
        mock_response_html.status_code = 200
        mock_response_html.text = html
        mock_response_html.raise_for_status = MagicMock()

        mock_response_404 = MagicMock()
        mock_response_404.status_code = 404

        async def mock_get(url, **kwargs):
            if url == "https://example.com":
                return mock_response_html
            return mock_response_404

        with patch("feed_reader.services.feed_discovery.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await discover_feed_url("https://example.com")

            assert result is None

    async def test_discover_adds_https_if_missing(self):
        """Test that https:// is added if protocol is missing."""
        html = "<html><head></head><body></body></html>"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_response_404 = MagicMock()
        mock_response_404.status_code = 404

        captured_urls = []

        async def mock_get(url, **kwargs):
            captured_urls.append(url)
            if "example.com" in url and "/" not in url.replace("https://", "").replace("http://", ""):
                return mock_response
            return mock_response_404

        with patch("feed_reader.services.feed_discovery.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            await discover_feed_url("example.com")

            # First URL should have https://
            assert captured_urls[0] == "https://example.com"


class TestFeedParser:
    """Tests for RSS/Atom feed parsing."""

    async def test_parse_rss_feed(self):
        """Test parsing a standard RSS 2.0 feed."""
        rss_feed = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test Blog</title>
                <item>
                    <title>First Post</title>
                    <link>https://example.com/post1</link>
                    <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
                </item>
                <item>
                    <title>Second Post</title>
                    <link>https://example.com/post2</link>
                </item>
            </channel>
        </rss>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = rss_feed
        mock_response.raise_for_status = MagicMock()

        with patch("feed_reader.services.feed_parser.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await parse_feed("https://example.com/feed.xml")

            assert len(articles) == 2
            assert articles[0].title == "First Post"
            assert articles[0].url == "https://example.com/post1"
            assert articles[0].published_date is not None
            assert articles[1].title == "Second Post"
            assert articles[1].published_date is None

    async def test_parse_atom_feed(self):
        """Test parsing an Atom feed."""
        atom_feed = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>Test Blog</title>
            <entry>
                <title>Atom Post</title>
                <link href="https://example.com/atom-post"/>
                <updated>2024-01-15T10:30:00Z</updated>
            </entry>
        </feed>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = atom_feed
        mock_response.raise_for_status = MagicMock()

        with patch("feed_reader.services.feed_parser.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await parse_feed("https://example.com/atom.xml")

            assert len(articles) == 1
            assert articles[0].title == "Atom Post"
            assert articles[0].url == "https://example.com/atom-post"

    async def test_parse_feed_skips_missing_title(self):
        """Test that entries without title are skipped."""
        rss_feed = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test Blog</title>
                <item>
                    <link>https://example.com/no-title</link>
                </item>
                <item>
                    <title>Has Title</title>
                    <link>https://example.com/has-title</link>
                </item>
            </channel>
        </rss>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = rss_feed
        mock_response.raise_for_status = MagicMock()

        with patch("feed_reader.services.feed_parser.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await parse_feed("https://example.com/feed.xml")

            assert len(articles) == 1
            assert articles[0].title == "Has Title"

    async def test_parse_feed_http_error(self):
        """Test handling of HTTP errors."""
        import httpx

        with patch("feed_reader.services.feed_parser.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await parse_feed("https://example.com/feed.xml")

            assert articles == []

    def test_parse_date_rfc2822(self):
        """Test parsing RFC 2822 date format."""
        entry = {"published": "Mon, 01 Jan 2024 12:00:00 GMT"}
        result = _parse_date(entry)
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_parse_date_iso_format(self):
        """Test parsing ISO format date."""
        entry = {"published": "2024-01-15T10:30:00Z"}
        result = _parse_date(entry)
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_invalid(self):
        """Test handling of invalid date."""
        entry = {"published": "not a date"}
        result = _parse_date(entry)
        assert result is None


class TestScraper:
    """Tests for HTML scraping."""

    async def test_scrape_blog_with_direct_links(self):
        """Test scraping when selector matches <a> tags directly."""
        html = """
        <html>
        <body>
            <div class="posts">
                <a href="/post1" class="post-link">First Post</a>
                <a href="/post2" class="post-link">Second Post</a>
                <a href="#" class="post-link">Skip This</a>
            </div>
        </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_reader.services.scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await scrape_blog("https://example.com", "a.post-link")

            assert len(articles) == 2
            assert articles[0].title == "First Post"
            assert articles[0].url == "https://example.com/post1"
            assert articles[1].title == "Second Post"
            assert articles[1].url == "https://example.com/post2"

    async def test_scrape_blog_with_parent_elements(self):
        """Test scraping when selector matches parent elements containing links."""
        html = """
        <html>
        <body>
            <article class="post">
                <h2><a href="/article1">Article One</a></h2>
            </article>
            <article class="post">
                <h2><a href="/article2">Article Two</a></h2>
            </article>
        </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_reader.services.scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await scrape_blog("https://example.com", "article.post")

            assert len(articles) == 2
            assert articles[0].url == "https://example.com/article1"

    async def test_scrape_blog_deduplicates_urls(self):
        """Test that duplicate URLs are removed."""
        html = """
        <html>
        <body>
            <a href="/same-post" class="link">First Link</a>
            <a href="/same-post" class="link">Duplicate Link</a>
            <a href="/other-post" class="link">Other Post</a>
        </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_reader.services.scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await scrape_blog("https://example.com", "a.link")

            assert len(articles) == 2

    async def test_scrape_blog_no_matches(self):
        """Test scraping returns empty list when no elements match."""
        html = "<html><body><p>No posts here</p></body></html>"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_reader.services.scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await scrape_blog("https://example.com", "article.post")

            assert articles == []

    async def test_scrape_blog_http_error(self):
        """Test handling of HTTP errors during scraping."""
        import httpx

        with patch("feed_reader.services.scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            articles = await scrape_blog("https://example.com", "a.post-link")

            assert articles == []
