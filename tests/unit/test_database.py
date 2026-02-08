"""Unit tests for database operations.

Tests for the storage layer using in-memory SQLite.
"""

import pytest
import aiosqlite
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, AsyncMock

from feed_reader.storage.database import (
    init_database,
    add_blog,
    remove_blog,
    get_blog_by_name,
    list_blogs,
    add_articles,
    get_existing_article_urls,
    list_articles,
    mark_article_read,
    mark_article_unread,
    mark_all_read,
    update_last_scanned,
)
from feed_reader.models.schemas import Blog, Article


# Mark all tests as async
pytestmark = pytest.mark.anyio


@pytest.fixture
async def in_memory_db():
    """Create an in-memory database for testing."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_database(db)

    # Patch get_database to return our in-memory connection
    with patch("feed_reader.storage.database.get_database", AsyncMock(return_value=db)):
        yield db

    await db.close()


class TestDatabaseInitialization:
    """Tests for database schema initialization."""

    async def test_init_creates_tables(self, in_memory_db):
        """Test that initialization creates the required tables."""
        cursor = await in_memory_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in await cursor.fetchall()]

        assert "blogs" in tables
        assert "articles" in tables

    async def test_init_creates_indexes(self, in_memory_db):
        """Test that initialization creates indexes."""
        cursor = await in_memory_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = [row[0] for row in await cursor.fetchall()]

        assert "idx_articles_blog_id" in indexes
        assert "idx_articles_is_read" in indexes

    async def test_init_is_idempotent(self, in_memory_db):
        """Test that calling init multiple times doesn't cause errors."""
        # Should not raise
        await init_database(in_memory_db)
        await init_database(in_memory_db)


class TestBlogOperations:
    """Tests for blog CRUD operations."""

    async def test_add_blog_minimal(self, in_memory_db):
        """Test adding a blog with minimal required fields."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        assert blog.id is not None
        assert blog.name == "Test Blog"
        assert blog.url == "https://example.com"
        assert blog.feed_url is None
        assert blog.scrape_selector is None
        assert blog.last_scanned is None

    async def test_add_blog_with_feed_url(self, in_memory_db):
        """Test adding a blog with feed URL."""
        blog = await add_blog(
            name="Test Blog",
            url="https://example.com",
            feed_url="https://example.com/feed.xml",
        )

        assert blog.feed_url == "https://example.com/feed.xml"

    async def test_add_blog_with_scrape_selector(self, in_memory_db):
        """Test adding a blog with scrape selector."""
        blog = await add_blog(
            name="Test Blog",
            url="https://example.com",
            scrape_selector="article.post a",
        )

        assert blog.scrape_selector == "article.post a"

    async def test_add_blog_duplicate_name_raises(self, in_memory_db):
        """Test that duplicate blog names raise ValueError."""
        await add_blog(name="Test Blog", url="https://example.com")

        with pytest.raises(ValueError, match="already exists"):
            await add_blog(name="Test Blog", url="https://other.com")

    async def test_add_blog_duplicate_url_raises(self, in_memory_db):
        """Test that duplicate URLs raise ValueError."""
        await add_blog(name="Blog One", url="https://example.com")

        with pytest.raises(ValueError, match="already exists"):
            await add_blog(name="Blog Two", url="https://example.com")

    async def test_get_blog_by_name_found(self, in_memory_db):
        """Test retrieving an existing blog by name."""
        await add_blog(name="Test Blog", url="https://example.com")

        blog = await get_blog_by_name("Test Blog")

        assert blog is not None
        assert blog.name == "Test Blog"
        assert blog.url == "https://example.com"

    async def test_get_blog_by_name_not_found(self, in_memory_db):
        """Test retrieving a non-existent blog returns None."""
        blog = await get_blog_by_name("Nonexistent")

        assert blog is None

    async def test_list_blogs_empty(self, in_memory_db):
        """Test listing blogs when none exist."""
        blogs = await list_blogs()

        assert blogs == []

    async def test_list_blogs_with_counts(self, in_memory_db):
        """Test listing blogs includes article counts."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        # Add some articles
        await add_articles(
            blog.id,
            [
                {"title": "Post 1", "url": "https://example.com/1"},
                {"title": "Post 2", "url": "https://example.com/2"},
            ],
        )

        # Mark one as read
        await in_memory_db.execute(
            "UPDATE articles SET is_read = 1 WHERE url = ?",
            ("https://example.com/1",),
        )
        await in_memory_db.commit()

        blogs = await list_blogs()

        assert len(blogs) == 1
        assert blogs[0]["name"] == "Test Blog"
        assert blogs[0]["total_articles"] == 2
        assert blogs[0]["unread_articles"] == 1

    async def test_remove_blog_success(self, in_memory_db):
        """Test removing an existing blog."""
        blog = await add_blog(name="Test Blog", url="https://example.com")
        await add_articles(
            blog.id,
            [
                {"title": "Post 1", "url": "https://example.com/1"},
                {"title": "Post 2", "url": "https://example.com/2"},
            ],
        )

        success, article_count = await remove_blog("Test Blog")

        assert success is True
        assert article_count == 2

        # Verify blog is gone
        assert await get_blog_by_name("Test Blog") is None

    async def test_remove_blog_not_found(self, in_memory_db):
        """Test removing a non-existent blog."""
        success, article_count = await remove_blog("Nonexistent")

        assert success is False
        assert article_count == 0


class TestArticleOperations:
    """Tests for article CRUD operations."""

    async def test_add_articles(self, in_memory_db):
        """Test adding articles to a blog."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        count = await add_articles(
            blog.id,
            [
                {"title": "Post 1", "url": "https://example.com/1"},
                {"title": "Post 2", "url": "https://example.com/2"},
            ],
        )

        assert count == 2

    async def test_add_articles_with_dates(self, in_memory_db):
        """Test adding articles with published dates."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        count = await add_articles(
            blog.id,
            [
                {
                    "title": "Post 1",
                    "url": "https://example.com/1",
                    "published_date": "2024-01-15T10:30:00",
                },
            ],
        )

        assert count == 1

        articles = await list_articles(include_read=True)
        assert articles[0].published_date is not None

    async def test_add_articles_skips_duplicates(self, in_memory_db):
        """Test that duplicate URLs are skipped."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        # Add first batch
        await add_articles(
            blog.id,
            [{"title": "Post 1", "url": "https://example.com/1"}],
        )

        # Add second batch with duplicate
        count = await add_articles(
            blog.id,
            [
                {"title": "Post 1 Again", "url": "https://example.com/1"},
                {"title": "Post 2", "url": "https://example.com/2"},
            ],
        )

        assert count == 1  # Only new one added

    async def test_get_existing_article_urls(self, in_memory_db):
        """Test checking for existing article URLs."""
        blog = await add_blog(name="Test Blog", url="https://example.com")
        await add_articles(
            blog.id,
            [
                {"title": "Post 1", "url": "https://example.com/1"},
                {"title": "Post 2", "url": "https://example.com/2"},
            ],
        )

        existing = await get_existing_article_urls(
            blog.id,
            [
                "https://example.com/1",  # exists
                "https://example.com/3",  # doesn't exist
            ],
        )

        assert existing == {"https://example.com/1"}

    async def test_get_existing_article_urls_empty(self, in_memory_db):
        """Test checking for existing URLs with empty list."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        existing = await get_existing_article_urls(blog.id, [])

        assert existing == set()

    async def test_list_articles_default(self, in_memory_db):
        """Test listing unread articles by default."""
        blog = await add_blog(name="Test Blog", url="https://example.com")
        await add_articles(
            blog.id,
            [
                {"title": "Post 1", "url": "https://example.com/1"},
                {"title": "Post 2", "url": "https://example.com/2"},
            ],
        )

        # Mark one as read
        await in_memory_db.execute(
            "UPDATE articles SET is_read = 1 WHERE url = ?",
            ("https://example.com/1",),
        )
        await in_memory_db.commit()

        articles = await list_articles()

        assert len(articles) == 1
        assert articles[0].url == "https://example.com/2"

    async def test_list_articles_include_read(self, in_memory_db):
        """Test listing all articles including read ones."""
        blog = await add_blog(name="Test Blog", url="https://example.com")
        await add_articles(
            blog.id,
            [
                {"title": "Post 1", "url": "https://example.com/1"},
                {"title": "Post 2", "url": "https://example.com/2"},
            ],
        )

        # Mark one as read
        await in_memory_db.execute(
            "UPDATE articles SET is_read = 1 WHERE url = ?",
            ("https://example.com/1",),
        )
        await in_memory_db.commit()

        articles = await list_articles(include_read=True)

        assert len(articles) == 2

    async def test_list_articles_filter_by_blog(self, in_memory_db):
        """Test filtering articles by blog name."""
        blog1 = await add_blog(name="Blog One", url="https://one.com")
        blog2 = await add_blog(name="Blog Two", url="https://two.com")

        await add_articles(blog1.id, [{"title": "Post 1", "url": "https://one.com/1"}])
        await add_articles(blog2.id, [{"title": "Post 2", "url": "https://two.com/1"}])

        articles = await list_articles(blog_name="Blog One")

        assert len(articles) == 1
        assert articles[0].url == "https://one.com/1"

    async def test_list_articles_limit(self, in_memory_db):
        """Test limiting the number of articles returned."""
        blog = await add_blog(name="Test Blog", url="https://example.com")
        await add_articles(
            blog.id,
            [
                {"title": f"Post {i}", "url": f"https://example.com/{i}"}
                for i in range(10)
            ],
        )

        articles = await list_articles(limit=3)

        assert len(articles) == 3


class TestArticleReadStatus:
    """Tests for marking articles as read/unread."""

    async def test_mark_article_read(self, in_memory_db):
        """Test marking an article as read."""
        blog = await add_blog(name="Test Blog", url="https://example.com")
        await add_articles(
            blog.id,
            [{"title": "Post 1", "url": "https://example.com/1"}],
        )

        # Get article ID
        cursor = await in_memory_db.execute("SELECT id FROM articles LIMIT 1")
        row = await cursor.fetchone()
        article_id = row["id"]

        article = await mark_article_read(article_id)

        assert article is not None
        assert article.is_read is True

    async def test_mark_article_read_not_found(self, in_memory_db):
        """Test marking a non-existent article as read."""
        article = await mark_article_read(99999)

        assert article is None

    async def test_mark_article_unread(self, in_memory_db):
        """Test marking an article as unread."""
        blog = await add_blog(name="Test Blog", url="https://example.com")
        await add_articles(
            blog.id,
            [{"title": "Post 1", "url": "https://example.com/1"}],
        )

        # Get article ID and mark as read first
        cursor = await in_memory_db.execute("SELECT id FROM articles LIMIT 1")
        row = await cursor.fetchone()
        article_id = row["id"]
        await mark_article_read(article_id)

        # Now mark as unread
        article = await mark_article_unread(article_id)

        assert article is not None
        assert article.is_read is False

    async def test_mark_all_read(self, in_memory_db):
        """Test marking all articles as read."""
        blog = await add_blog(name="Test Blog", url="https://example.com")
        await add_articles(
            blog.id,
            [
                {"title": "Post 1", "url": "https://example.com/1"},
                {"title": "Post 2", "url": "https://example.com/2"},
                {"title": "Post 3", "url": "https://example.com/3"},
            ],
        )

        count = await mark_all_read()

        assert count == 3

        # Verify all are read
        articles = await list_articles(include_read=True)
        assert all(a.is_read for a in articles)

    async def test_mark_all_read_filtered_by_blog(self, in_memory_db):
        """Test marking all articles as read for a specific blog."""
        blog1 = await add_blog(name="Blog One", url="https://one.com")
        blog2 = await add_blog(name="Blog Two", url="https://two.com")

        await add_articles(blog1.id, [{"title": "Post 1", "url": "https://one.com/1"}])
        await add_articles(blog2.id, [{"title": "Post 2", "url": "https://two.com/1"}])

        count = await mark_all_read(blog_name="Blog One")

        assert count == 1

        # Blog One should have read articles, Blog Two should not
        articles_one = await list_articles(blog_name="Blog One", include_read=True)
        articles_two = await list_articles(blog_name="Blog Two")

        assert all(a.is_read for a in articles_one)
        assert len(articles_two) == 1  # Still unread

    async def test_mark_all_read_nonexistent_blog(self, in_memory_db):
        """Test marking all read for a non-existent blog."""
        count = await mark_all_read(blog_name="Nonexistent")

        assert count == 0


class TestLastScanned:
    """Tests for last_scanned timestamp updates."""

    async def test_update_last_scanned(self, in_memory_db):
        """Test updating the last_scanned timestamp."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        assert blog.last_scanned is None

        await update_last_scanned(blog.id)

        updated_blog = await get_blog_by_name("Test Blog")

        assert updated_blog.last_scanned is not None
        assert isinstance(updated_blog.last_scanned, datetime)


class TestArticleDateFiltering:
    """Tests for list_articles date filtering functionality."""

    async def test_list_articles_since_filter(self, in_memory_db):
        """Test filtering articles since a specific date."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        # Add articles with different dates
        now = datetime.now()
        old_date = (now - timedelta(days=30)).isoformat()
        recent_date = (now - timedelta(days=2)).isoformat()

        await add_articles(
            blog.id,
            [
                {"title": "Old Post", "url": "https://example.com/old", "published_date": old_date},
                {"title": "Recent Post", "url": "https://example.com/recent", "published_date": recent_date},
            ],
        )

        # Filter to last 7 days
        since_date = now - timedelta(days=7)
        articles = await list_articles(since=since_date)

        assert len(articles) == 1
        assert articles[0].title == "Recent Post"

    async def test_list_articles_before_filter(self, in_memory_db):
        """Test filtering articles before a specific date."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        now = datetime.now()
        old_date = (now - timedelta(days=30)).isoformat()
        recent_date = (now - timedelta(days=2)).isoformat()

        await add_articles(
            blog.id,
            [
                {"title": "Old Post", "url": "https://example.com/old", "published_date": old_date},
                {"title": "Recent Post", "url": "https://example.com/recent", "published_date": recent_date},
            ],
        )

        # Filter to before 7 days ago
        before_date = now - timedelta(days=7)
        articles = await list_articles(before=before_date, include_read=True)

        assert len(articles) == 1
        assert articles[0].title == "Old Post"

    async def test_list_articles_date_range(self, in_memory_db):
        """Test filtering articles within a date range."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        now = datetime.now()
        very_old_date = (now - timedelta(days=60)).isoformat()
        middle_date = (now - timedelta(days=15)).isoformat()
        recent_date = (now - timedelta(days=2)).isoformat()

        await add_articles(
            blog.id,
            [
                {"title": "Very Old Post", "url": "https://example.com/very-old", "published_date": very_old_date},
                {"title": "Middle Post", "url": "https://example.com/middle", "published_date": middle_date},
                {"title": "Recent Post", "url": "https://example.com/recent", "published_date": recent_date},
            ],
        )

        # Filter to between 30 and 7 days ago
        since_date = now - timedelta(days=30)
        before_date = now - timedelta(days=7)
        articles = await list_articles(since=since_date, before=before_date, include_read=True)

        assert len(articles) == 1
        assert articles[0].title == "Middle Post"

    async def test_list_articles_days_shorthand(self, in_memory_db):
        """Test the days parameter shorthand for recent articles."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        now = datetime.now()
        old_date = (now - timedelta(days=30)).isoformat()
        recent_date = (now - timedelta(days=2)).isoformat()

        await add_articles(
            blog.id,
            [
                {"title": "Old Post", "url": "https://example.com/old", "published_date": old_date},
                {"title": "Recent Post", "url": "https://example.com/recent", "published_date": recent_date},
            ],
        )

        # Use days=7 shorthand
        articles = await list_articles(days=7)

        assert len(articles) == 1
        assert articles[0].title == "Recent Post"

    async def test_list_articles_days_overrides_since(self, in_memory_db):
        """Test that days parameter overrides since parameter."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        now = datetime.now()
        recent_date = (now - timedelta(days=2)).isoformat()

        await add_articles(
            blog.id,
            [
                {"title": "Recent Post", "url": "https://example.com/recent", "published_date": recent_date},
            ],
        )

        # days=7 should override since from 60 days ago
        since_date = now - timedelta(days=60)
        articles = await list_articles(since=since_date, days=7)

        # Should still find the article (days=7 takes precedence)
        assert len(articles) == 1

    async def test_list_articles_fallback_to_discovered_date(self, in_memory_db):
        """Test that articles without published_date use discovered_date for filtering."""
        blog = await add_blog(name="Test Blog", url="https://example.com")

        # Add article without published_date - discovered_date will be set to now
        await add_articles(
            blog.id,
            [
                {"title": "No Pub Date", "url": "https://example.com/no-date"},
            ],
        )

        # Filter to last 7 days - should find it via discovered_date
        articles = await list_articles(days=7)

        assert len(articles) == 1
        assert articles[0].title == "No Pub Date"

    async def test_list_articles_combined_filters(self, in_memory_db):
        """Test date filtering combined with other filters (blog_name, include_read)."""
        blog1 = await add_blog(name="Blog One", url="https://one.com")
        blog2 = await add_blog(name="Blog Two", url="https://two.com")

        now = datetime.now()
        recent_date = (now - timedelta(days=2)).isoformat()

        await add_articles(blog1.id, [{"title": "Blog1 Post", "url": "https://one.com/1", "published_date": recent_date}])
        await add_articles(blog2.id, [{"title": "Blog2 Post", "url": "https://two.com/1", "published_date": recent_date}])

        # Filter by blog name AND days
        articles = await list_articles(blog_name="Blog One", days=7)

        assert len(articles) == 1
        assert articles[0].title == "Blog1 Post"
