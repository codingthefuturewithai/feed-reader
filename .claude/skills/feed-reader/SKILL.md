---
name: feed-reader
description: Manage RSS feeds and articles. Use this skill when the user wants to check feeds, see new articles, add blogs/RSS feeds, subscribe to RSS, or manage their reading list.
user-invocable: true
---

# Feed Reader Skill

Manage RSS feeds and articles through the feed-reader MCP server.

## Trigger Phrases

This skill should activate when the user says things like:
- "check my feeds", "any new articles", "what's new in my blogs"
- "add this blog/feed", "subscribe to this RSS"
- "show me articles from X", "what did [author] write recently"
- "mark articles as read", "clear my feed"
- "articles from last week", "what's new today", "recent articles"

## MCP Tools Available

Before proceeding, use ToolSearch to load these tools:
- `mcp__feed-reader__add_blog` - Add new feed (requires: name, url; optional: feed_url, scrape_selector)
- `mcp__feed-reader__remove_blog` - Remove feed (requires: name)
- `mcp__feed-reader__list_blogs` - List all feeds with article counts
- `mcp__feed-reader__scan_blogs` - Fetch new articles from feeds (optional: blog_name)
- `mcp__feed-reader__list_articles` - List articles (optional: blog_name, include_read, limit, days, since, before)
- `mcp__feed-reader__mark_article_read` - Mark single article read (requires: article_id)
- `mcp__feed-reader__mark_all_read` - Mark all articles as read (optional: blog_name)
- `mcp__feed-reader__mark_article_unread` - Mark article as unread (requires: article_id)

## Workflow

### 1. Check MCP Availability
First, use ToolSearch to load the feed-reader tools and verify they're accessible.

### 2. Route by Intent

**"What's new" / "Check feeds":**
1. Call `scan_blogs` to fetch latest articles
2. Call `list_articles` with `limit=10` (defaults to unread only)
3. Present results in formatted list

**"What's new today" / "Last 24 hours":**
1. Call `list_articles` with `days=1`
2. Present results

**"Articles from last week":**
1. Call `list_articles` with `days=7`
2. Present results

**"Articles since [date]":**
1. Call `list_articles` with `since="YYYY-MM-DD"`
2. Present results

**"Add [blog/feed]":**
1. If user provides URL, use it directly
2. If user provides blog name only, help discover the RSS URL
3. Call `add_blog` with name and url (feed_url optional - will auto-discover)
4. Confirm success

**"List feeds" / "Show my subscriptions":**
1. Call `list_blogs`
2. Present feeds with their article counts

**"Show articles" / "Articles from X":**
1. Call `list_articles` with appropriate filters (blog_name, limit, days)
2. Present results

**"Mark read" / "Clear feed":**
1. For specific article: `mark_article_read` with article_id
2. For all articles: `mark_all_read` (optionally filtered by blog_name)

### 3. Date Filtering Parameters

The `list_articles` tool supports these date filters:
- `days=N` - Articles from last N days (e.g., days=1 for last 24 hours, days=7 for last week)
- `since="YYYY-MM-DD"` - Articles published after this date
- `before="YYYY-MM-DD"` - Articles published before this date
- Can combine `since` and `before` for a date range

Note: `days` overrides `since` if both are provided.

### 4. Output Format

When listing articles, present as:

```
**Recent Articles (unread: X)**

1. **Title of Article** - *Blog Name* (Jan 28)
   → [link if available]

2. **Another Article** - *Blog Name* (Jan 27)
   → [link if available]

...
```

When listing feeds:
```
**Your Feeds (X total)**

- **Blog Name** - 5 unread, 23 total
- **Another Blog** - 2 unread, 15 total
```

### 5. Follow-up Actions

After showing unread articles, offer: "Would you like me to mark any of these as read?"

After adding a feed, offer: "Would you like me to scan for articles now?"

## Explicit Invocation

When invoked with `/feed-reader`:
- No args: Show feed summary (list_blogs) and recent unread count
- `/feed-reader scan`: Scan all feeds and show new articles
- `/feed-reader add <url>`: Add a new feed
- `/feed-reader list`: List all subscribed feeds
- `/feed-reader articles`: Show recent unread articles
- `/feed-reader today`: Show articles from last 24 hours
- `/feed-reader week`: Show articles from last 7 days

## Error Handling

- If MCP tools aren't available, inform user the feed-reader server may not be running
- If feed URL is invalid, suggest checking the URL or trying to find the RSS feed
- If no unread articles, confirm feeds are up to date
- If invalid date format, suggest using ISO format (YYYY-MM-DD)
