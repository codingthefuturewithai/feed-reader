"""Storage layer for feed_reader."""

from .database import (
    get_database,
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

__all__ = [
    "get_database",
    "init_database",
    "add_blog",
    "remove_blog",
    "get_blog_by_name",
    "list_blogs",
    "add_articles",
    "get_existing_article_urls",
    "list_articles",
    "mark_article_read",
    "mark_article_unread",
    "mark_all_read",
    "update_last_scanned",
]
