"""Database storage for feed_reader.

This module provides async SQLite database operations for managing blogs and articles.
Database location: ~/.feed_reader/feed_reader.db (or FEED_READER_DB_PATH env var)
"""

import os
import aiosqlite
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set, Tuple

from feed_reader.models.schemas import Blog, Article


def _get_db_path() -> Path:
    """Get the database path, respecting FEED_READER_DB_PATH env var for testing."""
    env_path = os.environ.get("FEED_READER_DB_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / ".feed_reader" / "feed_reader.db"


# Singleton connection
_db_connection: Optional[aiosqlite.Connection] = None


async def get_database() -> aiosqlite.Connection:
    """Get or create a singleton database connection.

    Returns:
        Active database connection
    """
    global _db_connection

    if _db_connection is None:
        db_path = _get_db_path()
        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        _db_connection = await aiosqlite.connect(db_path)
        _db_connection.row_factory = aiosqlite.Row
        await init_database(_db_connection)

    return _db_connection


async def init_database(db: Optional[aiosqlite.Connection] = None) -> None:
    """Initialize database tables if they don't exist.

    Args:
        db: Optional database connection (uses singleton if not provided)
    """
    if db is None:
        db = await get_database()

    await db.execute("""
        CREATE TABLE IF NOT EXISTS blogs (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL UNIQUE,
            feed_url TEXT,
            scrape_selector TEXT,
            last_scanned TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY,
            blog_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            published_date TIMESTAMP,
            discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (blog_id) REFERENCES blogs(id) ON DELETE CASCADE
        )
    """)

    # Create index for faster lookups
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_blog_id ON articles(blog_id)
    """)

    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_is_read ON articles(is_read)
    """)

    await db.commit()


async def add_blog(
    name: str,
    url: str,
    feed_url: Optional[str] = None,
    scrape_selector: Optional[str] = None,
) -> Blog:
    """Add a new blog to the database.

    Args:
        name: Unique name for the blog
        url: Homepage URL of the blog
        feed_url: Optional RSS/Atom feed URL
        scrape_selector: Optional CSS selector for HTML scraping

    Returns:
        The created Blog object

    Raises:
        ValueError: If blog with same name or URL already exists
    """
    db = await get_database()

    try:
        cursor = await db.execute(
            """
            INSERT INTO blogs (name, url, feed_url, scrape_selector)
            VALUES (?, ?, ?, ?)
            """,
            (name, url, feed_url, scrape_selector),
        )
        await db.commit()

        return Blog(
            id=cursor.lastrowid,
            name=name,
            url=url,
            feed_url=feed_url,
            scrape_selector=scrape_selector,
            last_scanned=None,
        )
    except aiosqlite.IntegrityError as e:
        raise ValueError(f"Blog with name '{name}' or URL '{url}' already exists") from e


async def remove_blog(name: str) -> Tuple[bool, int]:
    """Remove a blog and all its articles.

    Args:
        name: Name of the blog to remove

    Returns:
        Tuple of (success, article_count_deleted)
    """
    db = await get_database()

    # Get blog id first
    cursor = await db.execute("SELECT id FROM blogs WHERE name = ?", (name,))
    row = await cursor.fetchone()

    if row is None:
        return (False, 0)

    blog_id = row["id"]

    # Count articles to be deleted
    cursor = await db.execute(
        "SELECT COUNT(*) as count FROM articles WHERE blog_id = ?", (blog_id,)
    )
    count_row = await cursor.fetchone()
    article_count = count_row["count"]

    # Delete articles first (foreign key constraint)
    await db.execute("DELETE FROM articles WHERE blog_id = ?", (blog_id,))

    # Delete blog
    await db.execute("DELETE FROM blogs WHERE id = ?", (blog_id,))
    await db.commit()

    return (True, article_count)


async def get_blog_by_name(name: str) -> Optional[Blog]:
    """Get a blog by its name.

    Args:
        name: Name of the blog

    Returns:
        Blog object if found, None otherwise
    """
    db = await get_database()

    cursor = await db.execute("SELECT * FROM blogs WHERE name = ?", (name,))
    row = await cursor.fetchone()

    if row is None:
        return None

    return Blog(
        id=row["id"],
        name=row["name"],
        url=row["url"],
        feed_url=row["feed_url"],
        scrape_selector=row["scrape_selector"],
        last_scanned=datetime.fromisoformat(row["last_scanned"])
        if row["last_scanned"]
        else None,
    )


async def list_blogs() -> List[dict]:
    """List all blogs with article counts.

    Returns:
        List of dicts with blog info and article counts
    """
    db = await get_database()

    cursor = await db.execute("""
        SELECT b.*,
               COUNT(a.id) as total_articles,
               SUM(CASE WHEN a.is_read = 0 THEN 1 ELSE 0 END) as unread_articles
        FROM blogs b
        LEFT JOIN articles a ON b.id = a.blog_id
        GROUP BY b.id
        ORDER BY b.name
    """)

    blogs = []
    async for row in cursor:
        blogs.append({
            "id": row["id"],
            "name": row["name"],
            "url": row["url"],
            "feed_url": row["feed_url"],
            "scrape_selector": row["scrape_selector"],
            "last_scanned": row["last_scanned"],
            "total_articles": row["total_articles"],
            "unread_articles": row["unread_articles"] or 0,
        })

    return blogs


async def add_articles(blog_id: int, articles: List[dict]) -> int:
    """Add new articles to the database, skipping duplicates.

    Args:
        blog_id: ID of the blog these articles belong to
        articles: List of article dicts with title, url, published_date

    Returns:
        Number of articles actually added (excludes duplicates)
    """
    db = await get_database()
    added_count = 0

    for article in articles:
        try:
            await db.execute(
                """
                INSERT INTO articles (blog_id, title, url, published_date)
                VALUES (?, ?, ?, ?)
                """,
                (
                    blog_id,
                    article["title"],
                    article["url"],
                    article.get("published_date"),
                ),
            )
            added_count += 1
        except aiosqlite.IntegrityError:
            # Duplicate URL, skip
            pass

    await db.commit()
    return added_count


async def get_existing_article_urls(blog_id: int, urls: List[str]) -> Set[str]:
    """Get URLs that already exist in the database for a blog.

    Args:
        blog_id: ID of the blog
        urls: List of URLs to check

    Returns:
        Set of URLs that already exist
    """
    if not urls:
        return set()

    db = await get_database()

    placeholders = ",".join("?" * len(urls))
    cursor = await db.execute(
        f"""
        SELECT url FROM articles
        WHERE blog_id = ? AND url IN ({placeholders})
        """,
        [blog_id] + urls,
    )

    existing = set()
    async for row in cursor:
        existing.add(row["url"])

    return existing


async def list_articles(
    blog_name: Optional[str] = None,
    include_read: bool = False,
    limit: int = 50,
    since: Optional[datetime] = None,
    before: Optional[datetime] = None,
    days: Optional[int] = None,
) -> List[Article]:
    """List articles with optional filters for blog, read status, and date range.

    Date filtering uses published_date when available, falling back to
    discovered_date for articles without a published_date.

    Args:
        blog_name: Optional blog name to filter by
        include_read: Whether to include read articles (default: False)
        limit: Maximum number of articles to return (default: 50)
        since: Only return articles published/discovered after this datetime
        before: Only return articles published/discovered before this datetime
        days: Shorthand for "last N days" - overrides `since` if provided

    Returns:
        List of Article objects, ordered by date (newest first)
    """
    db = await get_database()

    # Handle `days` shorthand - converts to `since`
    if days is not None:
        since = datetime.now() - timedelta(days=days)

    query = """
        SELECT a.*, b.name as blog_name
        FROM articles a
        JOIN blogs b ON a.blog_id = b.id
        WHERE 1=1
    """
    params: List = []

    if blog_name:
        query += " AND b.name = ?"
        params.append(blog_name)

    if not include_read:
        query += " AND a.is_read = 0"

    # Date filtering: use published_date if available, otherwise discovered_date
    if since:
        query += " AND COALESCE(a.published_date, a.discovered_date) >= ?"
        params.append(since.isoformat())

    if before:
        query += " AND COALESCE(a.published_date, a.discovered_date) < ?"
        params.append(before.isoformat())

    query += " ORDER BY COALESCE(a.published_date, a.discovered_date) DESC, a.id DESC LIMIT ?"
    params.append(limit)

    cursor = await db.execute(query, params)

    articles = []
    async for row in cursor:
        articles.append(Article(
            id=row["id"],
            blog_id=row["blog_id"],
            title=row["title"],
            url=row["url"],
            published_date=datetime.fromisoformat(row["published_date"])
            if row["published_date"]
            else None,
            discovered_date=datetime.fromisoformat(row["discovered_date"])
            if row["discovered_date"]
            else None,
            is_read=bool(row["is_read"]),
        ))

    return articles


async def mark_article_read(article_id: int) -> Optional[Article]:
    """Mark an article as read.

    Args:
        article_id: ID of the article

    Returns:
        Updated Article object if found, None otherwise
    """
    db = await get_database()

    await db.execute(
        "UPDATE articles SET is_read = 1 WHERE id = ?",
        (article_id,),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = await cursor.fetchone()

    if row is None:
        return None

    return Article(
        id=row["id"],
        blog_id=row["blog_id"],
        title=row["title"],
        url=row["url"],
        published_date=datetime.fromisoformat(row["published_date"])
        if row["published_date"]
        else None,
        discovered_date=datetime.fromisoformat(row["discovered_date"])
        if row["discovered_date"]
        else None,
        is_read=bool(row["is_read"]),
    )


async def mark_article_unread(article_id: int) -> Optional[Article]:
    """Mark an article as unread.

    Args:
        article_id: ID of the article

    Returns:
        Updated Article object if found, None otherwise
    """
    db = await get_database()

    await db.execute(
        "UPDATE articles SET is_read = 0 WHERE id = ?",
        (article_id,),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = await cursor.fetchone()

    if row is None:
        return None

    return Article(
        id=row["id"],
        blog_id=row["blog_id"],
        title=row["title"],
        url=row["url"],
        published_date=datetime.fromisoformat(row["published_date"])
        if row["published_date"]
        else None,
        discovered_date=datetime.fromisoformat(row["discovered_date"])
        if row["discovered_date"]
        else None,
        is_read=bool(row["is_read"]),
    )


async def mark_all_read(blog_name: Optional[str] = None) -> int:
    """Mark all articles as read, optionally filtered by blog.

    Args:
        blog_name: Optional blog name to filter by

    Returns:
        Number of articles marked as read
    """
    db = await get_database()

    if blog_name:
        # Get blog id
        cursor = await db.execute("SELECT id FROM blogs WHERE name = ?", (blog_name,))
        row = await cursor.fetchone()
        if row is None:
            return 0
        blog_id = row["id"]

        cursor = await db.execute(
            "UPDATE articles SET is_read = 1 WHERE blog_id = ? AND is_read = 0",
            (blog_id,),
        )
    else:
        cursor = await db.execute(
            "UPDATE articles SET is_read = 1 WHERE is_read = 0"
        )

    await db.commit()
    return cursor.rowcount


async def update_last_scanned(blog_id: int) -> None:
    """Update the last_scanned timestamp for a blog.

    Args:
        blog_id: ID of the blog
    """
    db = await get_database()

    await db.execute(
        "UPDATE blogs SET last_scanned = ? WHERE id = ?",
        (datetime.now().isoformat(), blog_id),
    )
    await db.commit()


async def close_database() -> None:
    """Close the database connection."""
    global _db_connection

    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None
