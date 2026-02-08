"""Feed reader MCP tools.

This module provides MCP tools for managing RSS feeds and articles.

NOTE: Never use Optional parameters in MCP tools - they break MCP clients.
Use empty string "" for optional strings and 0 for optional integers.
"""

from datetime import datetime
from typing import Any, Dict
from mcp.server.fastmcp import Context

from feed_reader.log_system.unified_logger import UnifiedLogger
from feed_reader.storage import database
from feed_reader.services.feed_discovery import discover_feed_url
from feed_reader.services.feed_parser import parse_feed
from feed_reader.services.scraper import scrape_blog


async def add_blog(
    name: str,
    url: str,
    feed_url: str = "",
    scrape_selector: str = "",
    ctx: Context = None,
) -> Dict[str, Any]:
    """Add a new blog or RSS feed to track.

    If no feed_url is provided, the tool will attempt to auto-discover the RSS/Atom
    feed from the blog's homepage by looking for standard feed link tags.

    Args:
        name: Unique display name for the blog (used for filtering and display)
        url: Homepage URL of the blog (will be normalized to https:// if no scheme)
        feed_url: Direct RSS/Atom feed URL (empty string to auto-discover)
        scrape_selector: CSS selector for HTML scraping as fallback if no feed available
        ctx: MCP Context object (injected automatically)

    Returns:
        Dictionary with:
        - success: bool
        - blog: object with id, name, url, feed_url, scrape_selector
        - feed_discovered: bool indicating if feed was auto-discovered
        - error: string if success is False
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"add_blog called: name={name}, url={url}")

    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Auto-discover feed if not provided
    discovered_feed = None
    if not feed_url:
        logger.info("Attempting feed auto-discovery...")
        discovered_feed = await discover_feed_url(url)
        if discovered_feed:
            feed_url = discovered_feed
            logger.info(f"Discovered feed: {feed_url}")

    # Validate that we have either a feed URL or scrape selector
    if not feed_url and not scrape_selector:
        return {
            "success": False,
            "error": f"Could not auto-discover feed for {url}. Please provide a feed_url or scrape_selector.",
        }

    try:
        blog = await database.add_blog(
            name=name,
            url=url,
            feed_url=feed_url or None,  # Convert empty string to None for database
            scrape_selector=scrape_selector or None,  # Convert empty string to None for database
        )

        return {
            "success": True,
            "blog": {
                "id": blog.id,
                "name": blog.name,
                "url": blog.url,
                "feed_url": blog.feed_url,
                "scrape_selector": blog.scrape_selector,
            },
            "feed_discovered": discovered_feed is not None,
        }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
        }


async def remove_blog(name: str, ctx: Context = None) -> Dict[str, Any]:
    """Remove a blog and all its tracked articles from the database.

    This permanently deletes the blog and all associated articles. This action
    cannot be undone.

    Args:
        name: Name of the blog to remove (case-sensitive, must match exactly)
        ctx: MCP Context object (injected automatically)

    Returns:
        Dictionary with:
        - success: bool
        - message: confirmation string if successful
        - articles_deleted: count of articles removed
        - error: string if blog not found
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"remove_blog called: name={name}")

    success, article_count = await database.remove_blog(name)

    if success:
        return {
            "success": True,
            "message": f"Removed blog '{name}' and {article_count} articles",
            "articles_deleted": article_count,
        }
    else:
        return {
            "success": False,
            "error": f"Blog '{name}' not found",
        }


async def list_blogs(ctx: Context = None) -> Dict[str, Any]:
    """List all configured blogs/feeds with article counts.

    Returns summary information about each tracked blog including total and
    unread article counts, last scan time, and feed configuration.

    Args:
        ctx: MCP Context object (injected automatically)

    Returns:
        Dictionary with:
        - success: bool
        - count: number of blogs
        - blogs: list of blog objects with id, name, url, feed_url, scrape_selector,
          last_scanned, total_articles, unread_articles
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info("list_blogs called")

    blogs = await database.list_blogs()

    return {
        "success": True,
        "count": len(blogs),
        "blogs": blogs,
    }


async def scan_blogs(
    blog_name: str = "",
    ctx: Context = None,
) -> Dict[str, Any]:
    """Fetch new articles from RSS feeds and add them to the database.

    Scans all configured blogs or a specific blog. For each blog, fetches the
    RSS/Atom feed (or scrapes HTML if configured), identifies new articles by
    URL, and stores them. Duplicate URLs are automatically skipped.

    Args:
        blog_name: Scan only this blog (empty string scans all blogs)
        ctx: MCP Context object (injected automatically)

    Returns:
        Dictionary with:
        - success: bool
        - blogs_scanned: number of blogs processed
        - total_new_articles: total new articles added across all blogs
        - results: list of per-blog results with blog name, new_articles count, errors
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"scan_blogs called: blog_name={blog_name}")

    # Get blogs to scan
    if blog_name:
        blog = await database.get_blog_by_name(blog_name)
        if not blog:
            return {
                "success": False,
                "error": f"Blog '{blog_name}' not found",
            }
        blogs_to_scan = [blog]
    else:
        all_blogs = await database.list_blogs()
        # Convert dict results to Blog-like objects
        from feed_reader.models.schemas import Blog
        blogs_to_scan = [
            Blog(
                id=b["id"],
                name=b["name"],
                url=b["url"],
                feed_url=b["feed_url"],
                scrape_selector=b["scrape_selector"],
                last_scanned=None,
            )
            for b in all_blogs
        ]

    results = []
    total_new = 0

    for blog in blogs_to_scan:
        scan_result = {"blog": blog.name, "new_articles": 0, "errors": []}

        try:
            articles = []

            # Try feed first
            if blog.feed_url:
                parsed = await parse_feed(blog.feed_url)
                articles = [
                    {
                        "title": a.title,
                        "url": a.url,
                        "published_date": a.published_date.isoformat() if a.published_date else None,
                    }
                    for a in parsed
                ]

            # Fall back to scraping if no feed or no articles
            if not articles and blog.scrape_selector:
                scraped = await scrape_blog(blog.url, blog.scrape_selector)
                articles = [
                    {
                        "title": a.title,
                        "url": a.url,
                        "published_date": None,
                    }
                    for a in scraped
                ]

            if articles:
                added = await database.add_articles(blog.id, articles)
                scan_result["new_articles"] = added
                total_new += added

            # Update last scanned timestamp
            await database.update_last_scanned(blog.id)

        except Exception as e:
            logger.error(f"Error scanning {blog.name}: {e}")
            scan_result["errors"].append(str(e))

        results.append(scan_result)

    return {
        "success": True,
        "blogs_scanned": len(blogs_to_scan),
        "total_new_articles": total_new,
        "results": results,
    }


async def list_articles(
    blog_name: str = "",
    include_read: bool = False,
    limit: int = 50,
    since: str = "",
    before: str = "",
    days: int = 0,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List articles with optional filters for blog, read status, and date range.

    Date filtering uses published_date when available, falling back to
    discovered_date for articles without a published_date. Results are
    ordered by date (newest first).

    Args:
        blog_name: Filter to articles from this blog only (empty string for all blogs)
        include_read: Include articles marked as read (default: False, only unread)
        limit: Maximum number of articles to return (default: 50)
        since: Only articles published after this date (ISO format: "2025-01-01" or "2025-01-01T00:00:00", empty string for no filter)
        before: Only articles published before this date (ISO format: "2025-01-01" or "2025-01-01T00:00:00", empty string for no filter)
        days: Shorthand for "last N days" - if > 0, overrides `since` parameter (0 means no filter)
        ctx: MCP Context object (injected automatically)

    Returns:
        Dictionary with:
        - success: bool
        - count: number of articles returned
        - articles: list of article objects with id, title, url, dates, read status
        - filters_applied: summary of active filters

    Examples:
        - list_articles(days=1) -> articles from last 24 hours
        - list_articles(days=7) -> articles from last week
        - list_articles(since="2025-01-01") -> articles since Jan 1, 2025
        - list_articles(blog_name="Simon Willison", days=7) -> last week from one blog
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"list_articles called: blog_name={blog_name}, include_read={include_read}, limit={limit}, since={since}, before={before}, days={days}")

    # Parse date strings to datetime objects
    since_dt = None
    before_dt = None

    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid 'since' date format: {since}. Use ISO format like '2025-01-01' or '2025-01-01T00:00:00'",
            }

    if before:
        try:
            before_dt = datetime.fromisoformat(before)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid 'before' date format: {before}. Use ISO format like '2025-01-01' or '2025-01-01T00:00:00'",
            }

    # Convert empty/zero values to None for database layer
    articles = await database.list_articles(
        blog_name=blog_name or None,
        include_read=include_read,
        limit=limit,
        since=since_dt,
        before=before_dt,
        days=days if days > 0 else None,
    )

    # Build filters summary for response
    filters_applied = {
        "blog_name": blog_name or None,
        "include_read": include_read,
        "limit": limit,
        "days": days if days > 0 else None,
        "since": since or None,
        "before": before or None,
    }

    return {
        "success": True,
        "count": len(articles),
        "filters_applied": filters_applied,
        "articles": [
            {
                "id": a.id,
                "blog_id": a.blog_id,
                "title": a.title,
                "url": a.url,
                "published_date": a.published_date.isoformat() if a.published_date else None,
                "discovered_date": a.discovered_date.isoformat() if a.discovered_date else None,
                "is_read": a.is_read,
            }
            for a in articles
        ],
    }


async def mark_article_read(article_id: int, ctx: Context = None) -> Dict[str, Any]:
    """Mark a specific article as read.

    Updates the article's is_read status to true. Use this to track which
    articles you've already reviewed.

    Args:
        article_id: Database ID of the article (from list_articles response)
        ctx: MCP Context object (injected automatically)

    Returns:
        Dictionary with:
        - success: bool
        - article: object with id, title, url, is_read (if found)
        - error: string if article not found
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"mark_article_read called: article_id={article_id}")

    article = await database.mark_article_read(article_id)

    if article:
        return {
            "success": True,
            "article": {
                "id": article.id,
                "title": article.title,
                "url": article.url,
                "is_read": article.is_read,
            },
        }
    else:
        return {
            "success": False,
            "error": f"Article with id {article_id} not found",
        }


async def mark_all_read(
    blog_name: str = "",
    ctx: Context = None,
) -> Dict[str, Any]:
    """Mark all unread articles as read, optionally filtered to a specific blog.

    Bulk operation to clear your unread queue. Can mark all articles across
    all blogs, or just articles from a specific blog.

    Args:
        blog_name: Only mark articles from this blog (empty string marks all blogs)
        ctx: MCP Context object (injected automatically)

    Returns:
        Dictionary with:
        - success: bool
        - articles_marked_read: count of articles updated
        - blog_filter: the blog_name filter if provided, null otherwise
        - error: string if specified blog not found
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"mark_all_read called: blog_name={blog_name}")

    # Convert empty string to None for database layer
    count = await database.mark_all_read(blog_name or None)

    if blog_name and count == 0:
        # Check if blog exists
        blog = await database.get_blog_by_name(blog_name)
        if not blog:
            return {
                "success": False,
                "error": f"Blog '{blog_name}' not found",
            }

    return {
        "success": True,
        "articles_marked_read": count,
        "blog_filter": blog_name or None,
    }


async def mark_article_unread(article_id: int, ctx: Context = None) -> Dict[str, Any]:
    """Mark a specific article as unread.

    Reverts an article's read status back to unread. Use this if you want
    to revisit an article later.

    Args:
        article_id: Database ID of the article (from list_articles response)
        ctx: MCP Context object (injected automatically)

    Returns:
        Dictionary with:
        - success: bool
        - article: object with id, title, url, is_read (if found)
        - error: string if article not found
    """
    logger = UnifiedLogger.get_logger(__name__)
    logger.info(f"mark_article_unread called: article_id={article_id}")

    article = await database.mark_article_unread(article_id)

    if article:
        return {
            "success": True,
            "article": {
                "id": article.id,
                "title": article.title,
                "url": article.url,
                "is_read": article.is_read,
            },
        }
    else:
        return {
            "success": False,
            "error": f"Article with id {article_id} not found",
        }


# List of feed tools for registration
feed_tools = [
    add_blog,
    remove_blog,
    list_blogs,
    scan_blogs,
    list_articles,
    mark_article_read,
    mark_all_read,
    mark_article_unread,
]
