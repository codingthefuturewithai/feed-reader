# Feed Reader MCP Server - Specification

## 1. Overview

### Problem Statement

RSS feed management with proper read/unread article tracking is a common need, but existing RSS MCP servers lack this feature. BlogWatcher (Go CLI) solves this problem elegantly with feed discovery, RSS/Atom parsing, HTML scraping fallback, and SQLite-based read state tracking.

This specification defines a **native Python MCP server** that reimplements BlogWatcher's core functionality, providing direct integration with Claude Desktop, Claude Code, Cursor, and other MCP clients.

### Goals

1. Expose 8 MCP tools for complete RSS feed management
2. Native Python implementation (not a CLI wrapper)
3. SQLite storage at `~/.feed_reader/feed_reader.db`
4. Clean, well-typed tool interfaces suitable for LLM consumption
5. Automatic feed URL discovery from blog homepages
6. HTML scraping fallback when RSS feeds are unavailable

### Non-Goals

- Web UI or REST API
- Managing multiple user databases
- Article content fetching (full text extraction)
- OPML import/export
- Scheduled background scanning

### Project Status

**This project has been scaffolded** using `codingthefuturewithai/mcp-cookie-cutter`. The basic MCP server structure already exists.

### CRITICAL: Design Pattern Compliance

**All MCP tools, unit tests, and integration tests MUST follow the established design patterns already present in this scaffolded project.**

This is a hard requirement with no exceptions:

1. **Tool Implementation Patterns** - Tools must be structured exactly as the existing example tools demonstrate (decorators, function signatures, return types, error handling patterns)
2. **Test Patterns** - Unit and integration tests must follow the existing test organization, fixtures, and assertion patterns
3. **Project Structure** - Use the exact directory layout that exists; do not reorganize or rename directories
4. **Server Registration** - Register tools using the same pattern the existing tools use
5. **Dependency Injection** - If the project uses DI patterns for services/storage, follow them

**Before implementing any tool or test:**
1. Study the existing example implementations in this project
2. Identify the patterns used (decorators, base classes, protocols, etc.)
3. Replicate those patterns exactly for Feed Reader tools

**It is NOT permitted to:**
- Invent alternative patterns that "seem better"
- Skip patterns because they seem unnecessary
- Partially follow patterns
- Refactor the existing project structure

The existing patterns exist for consistency across MCP servers. Violating them creates maintenance burden and inconsistency.

---

## 2. MCP Tools Specification

### Tool 1: `add_blog`

**Description:** Add a new blog/RSS feed to track.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Unique identifier for the blog (e.g., "simonwillison") |
| `url` | string | Yes | Blog homepage URL or direct RSS feed URL |
| `feed_url` | string | No | Explicit RSS/Atom feed URL if different from main URL |
| `scrape_selector` | string | No | CSS selector for scraping if RSS unavailable |

**Returns:**
```json
{
  "success": true,
  "blog": {
    "id": 1,
    "name": "simonwillison",
    "url": "https://simonwillison.net",
    "feed_url": "https://simonwillison.net/atom/everything/",
    "scrape_selector": null
  },
  "message": "Added blog 'simonwillison' with feed URL: https://simonwillison.net/atom/everything/"
}
```

**Behavior:**
1. If `feed_url` not provided, attempt feed discovery from `url`
2. If discovery fails and no `scrape_selector`, return error with suggestion
3. Store blog in database

**BlogWatcher Reference:** `rss.DiscoverFeedURL()` in `internal/rss/rss.go:62-116`

---

### Tool 2: `remove_blog`

**Description:** Remove a blog and all its tracked articles from the database.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Name of the blog to remove |

**Returns:**
```json
{
  "success": true,
  "message": "Removed blog 'simonwillison' and 47 articles"
}
```

**BlogWatcher Reference:** `Database.RemoveBlog()` in `internal/storage/database.go:143-157`

---

### Tool 3: `list_blogs`

**Description:** List all configured blogs/feeds with article counts.

**Parameters:** None

**Returns:**
```json
{
  "blogs": [
    {
      "id": 1,
      "name": "simonwillison",
      "url": "https://simonwillison.net",
      "feed_url": "https://simonwillison.net/atom/everything/",
      "scrape_selector": null,
      "total_articles": 30,
      "unread_articles": 5,
      "last_scanned": "2026-01-28T10:30:00Z"
    }
  ],
  "total_blogs": 1,
  "total_unread": 5
}
```

**BlogWatcher Reference:** `Database.ListBlogs()` in `internal/storage/database.go:112-131`

---

### Tool 4: `scan_blogs`

**Description:** Fetch new articles from all blogs or a specific blog.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `blog_name` | string | No | Specific blog to scan (omit for all blogs) |

**Returns:**
```json
{
  "scanned": 9,
  "new_articles": 12,
  "blogs_updated": [
    {"name": "simonwillison", "new": 3},
    {"name": "latentspace", "new": 9}
  ],
  "errors": []
}
```

**Behavior:**
1. For each blog, check if `feed_url` exists → use RSS parsing
2. If no `feed_url` but `scrape_selector` exists → use HTML scraping
3. Deduplicate against existing articles by URL
4. Insert new articles with `is_read = false`
5. Update `last_scanned` timestamp

**BlogWatcher References:**
- RSS parsing: `rss.ParseFeed()` in `internal/rss/rss.go:27-60`
- HTML scraping: `scraper.ScrapeBlog()` in `internal/scraper/scraper.go:28-80`
- Deduplication: `Database.GetExistingArticleURLs()` in `internal/storage/database.go:212-247`
- Bulk insert: `Database.AddArticlesBulk()` in `internal/storage/database.go:176-210`

---

### Tool 5: `list_articles`

**Description:** List articles, optionally filtered by blog and read status.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `blog_name` | string | No | Filter to specific blog |
| `include_read` | boolean | No | Include already-read articles (default: false) |
| `limit` | integer | No | Maximum articles to return (default: 50) |

**Returns:**
```json
{
  "articles": [
    {
      "id": 241,
      "title": "One Human + One Agent = One Browser From Scratch",
      "url": "https://simonwillison.net/2026/Jan/27/one-human-one-agent/",
      "blog_name": "simonwillison",
      "published": "2026-01-27T16:58:00Z",
      "discovered": "2026-01-28T10:30:00Z",
      "is_read": false
    }
  ],
  "total": 1,
  "showing": "unread"
}
```

**BlogWatcher Reference:** `Database.ListArticles()` in `internal/storage/database.go:249-279`

---

### Tool 6: `mark_article_read`

**Description:** Mark a specific article as read.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `article_id` | integer | Yes | ID of the article to mark as read |

**Returns:**
```json
{
  "success": true,
  "article": {
    "id": 241,
    "title": "One Human + One Agent = One Browser From Scratch"
  },
  "message": "Marked article as read"
}
```

**BlogWatcher Reference:** `Database.MarkArticleRead()` in `internal/storage/database.go:281-291`

---

### Tool 7: `mark_all_read`

**Description:** Mark all articles as read, optionally filtered to a specific blog.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `blog_name` | string | No | Only mark articles from this blog as read |

**Returns:**
```json
{
  "success": true,
  "marked_read": 47,
  "blog_filter": null,
  "message": "Marked 47 articles as read"
}
```

**Implementation Note:** Requires custom SQL query not directly in BlogWatcher - use `UPDATE articles SET is_read = 1 WHERE is_read = 0 [AND blog_id = ?]`

---

### Tool 8: `mark_article_unread`

**Description:** Mark a specific article as unread.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `article_id` | integer | Yes | ID of the article to mark as unread |

**Returns:**
```json
{
  "success": true,
  "article": {
    "id": 241,
    "title": "One Human + One Agent = One Browser From Scratch"
  },
  "message": "Marked article as unread"
}
```

**BlogWatcher Reference:** `Database.MarkArticleUnread()` in `internal/storage/database.go:293-303`

---

## 3. Data Models

### Blog Model

```python
@dataclass
class Blog:
    id: int
    name: str
    url: str
    feed_url: str | None
    scrape_selector: str | None
    last_scanned: datetime | None
```

### Article Model

```python
@dataclass
class Article:
    id: int
    blog_id: int
    title: str
    url: str
    published_date: datetime | None
    discovered_date: datetime | None
    is_read: bool
```

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS blogs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL UNIQUE,
    feed_url TEXT,
    scrape_selector TEXT,
    last_scanned TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    blog_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    published_date TIMESTAMP,
    discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (blog_id) REFERENCES blogs(id)
);
```

**Database Location:** `~/.feed_reader/feed_reader.db`

**Note:** Added `UNIQUE` constraint on `blogs.name` (BlogWatcher has it on `url` only). This prevents duplicate blog names which improves UX.

---

## 4. Core Features & BlogWatcher References

### Feed Discovery

**Purpose:** Automatically find RSS/Atom feed URL from a blog homepage.

**BlogWatcher Implementation:** `rss.DiscoverFeedURL()` (`internal/rss/rss.go:62-116`)

**Algorithm:**
1. Fetch the blog homepage HTML
2. Look for `<link rel="alternate">` tags with feed MIME types:
   - `application/rss+xml`
   - `application/atom+xml`
   - `application/feed+json`
   - `application/xml`
   - `text/xml`
3. If no link tags found, probe common paths:
   - `/feed`, `/feed/`, `/rss`, `/rss/`
   - `/feed.xml`, `/rss.xml`, `/atom.xml`, `/index.xml`
4. Validate each candidate by attempting to parse it as a feed
5. Return first valid feed URL, or empty string if none found

**Python Implementation:**
- Use `httpx` for HTTP requests
- Use `beautifulsoup4` for HTML parsing
- Use `feedparser` for feed validation

### RSS/Atom Parsing

**Purpose:** Parse RSS/Atom feeds and extract articles.

**BlogWatcher Implementation:** `rss.ParseFeed()` (`internal/rss/rss.go:27-60`)

**Extracted Fields:**
- `title` - Article title (skip if empty)
- `url` - Article link (skip if empty)
- `published_date` - Use `published` or fall back to `updated`

**Python Implementation:**
- Use `feedparser` library (handles RSS 1.0, 2.0, Atom, etc.)

### HTML Scraping

**Purpose:** Extract article links when RSS feed is unavailable.

**BlogWatcher Implementation:** `scraper.ScrapeBlog()` (`internal/scraper/scraper.go:28-80`)

**Algorithm:**
1. Fetch blog homepage HTML
2. Find all elements matching CSS selector
3. For each element:
   - If element is `<a>`, use it directly
   - Otherwise, find first `<a>` descendant
4. Extract `href` and resolve to absolute URL
5. Extract title from: link text → `title` attribute → parent text
6. Deduplicate by URL

**Python Implementation:**
- Use `httpx` for HTTP requests
- Use `beautifulsoup4` with CSS selectors

### Deduplication

**Purpose:** Avoid inserting duplicate articles during scan.

**BlogWatcher Implementation:** `Database.GetExistingArticleURLs()` (`internal/storage/database.go:212-247`)

**Algorithm:**
1. Collect all article URLs from feed/scrape
2. Query database for which URLs already exist (chunked for SQLite limits)
3. Filter out existing URLs before insert

**Python Implementation:**
- Same chunked query approach (SQLite has ~999 parameter limit)

---

## 5. Project Structure

### IMPORTANT: Follow Existing Structure

The project has already been scaffolded. **Study the existing structure and patterns before adding any code.**

**Before implementing:**
1. Examine the existing project structure
2. Study the example tool implementations already present
3. Add Feed Reader tools following the exact same patterns
4. Add services/storage in locations consistent with existing conventions

### Illustrative Structure (defer to actual project structure)

```
feed_reader/
├── pyproject.toml
├── README.md
├── src/
│   └── feed_reader/
│       ├── __init__.py
│       ├── server.py          # MCP server entry point
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── add_blog.py
│       │   ├── remove_blog.py
│       │   ├── list_blogs.py
│       │   ├── scan_blogs.py
│       │   ├── list_articles.py
│       │   ├── mark_article_read.py
│       │   ├── mark_all_read.py
│       │   └── mark_article_unread.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── feed_discovery.py   # DiscoverFeedURL equivalent
│       │   ├── feed_parser.py      # ParseFeed equivalent
│       │   └── scraper.py          # ScrapeBlog equivalent
│       ├── storage/
│       │   ├── __init__.py
│       │   └── database.py         # SQLite operations
│       └── models/
│           ├── __init__.py
│           └── schemas.py          # Blog, Article dataclasses
└── tests/
    └── ...
```

### Directory Responsibilities

| Directory | Purpose |
|-----------|---------|
| `tools/` | MCP tool definitions - one file per tool |
| `services/` | Core business logic (feed discovery, parsing, scraping) |
| `storage/` | Database access layer |
| `models/` | Data models and schemas |

**Note:** If the cookiecutter template uses different directory names or organization (e.g., no separate `tools/` directory, or tools defined inline in `server.py`), follow the template's pattern instead.

---

## 6. Dependencies

```toml
[project]
dependencies = [
    "mcp>=1.0.0",
    "feedparser>=6.0.0",      # RSS/Atom parsing
    "beautifulsoup4>=4.12.0", # HTML parsing for discovery & scraping
    "httpx>=0.27.0",          # Async HTTP client
    "aiosqlite>=0.19.0",      # Async SQLite
    "lxml>=5.0.0",            # Fast HTML parser for BeautifulSoup
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

### Dependency Rationale

| Package | Purpose | BlogWatcher Equivalent |
|---------|---------|------------------------|
| `feedparser` | Parse RSS/Atom feeds | `gofeed` |
| `beautifulsoup4` | Parse HTML for discovery/scraping | `goquery` |
| `httpx` | Async HTTP requests | `net/http` |
| `aiosqlite` | Async SQLite access | `modernc.org/sqlite` |
| `lxml` | Fast HTML parser backend | N/A |

---

## 7. Development Phases

### Phase 1: Pattern Study & Dependencies
- **Study the existing example tools and tests thoroughly**
- Document the patterns used (decorators, registration, error handling, test fixtures)
- Add required dependencies to pyproject.toml (feedparser, beautifulsoup4, httpx, aiosqlite, lxml)

### Phase 2: Storage Layer
- Implement SQLite database initialization
- Implement Blog CRUD operations
- Implement Article CRUD operations
- Implement deduplication query

### Phase 3: Services
- Implement feed discovery service
- Implement RSS/Atom parser service
- Implement HTML scraper service

### Phase 4: MCP Tools (following template patterns exactly)
- Implement `add_blog` (uses feed discovery) - **match template's tool pattern**
- Implement `remove_blog`
- Implement `list_blogs`
- Implement `scan_blogs` (uses parser + scraper)
- Implement `list_articles`
- Implement `mark_article_read`
- Implement `mark_all_read`
- Implement `mark_article_unread`

### Phase 5: Testing & Polish (following template test patterns exactly)
- Add unit tests for services - **use template's test fixtures and patterns**
- Add integration tests for tools - **use template's integration test approach**
- Test with Claude Desktop / Claude Code
- Error handling refinement

---

## 8. Error Handling

### Error Categories

| Error Type | Example | Response |
|------------|---------|----------|
| Blog not found | `remove_blog("nonexistent")` | `{"success": false, "error": "Blog 'nonexistent' not found", "available_blogs": ["simonwillison", "latentspace"]}` |
| Article not found | `mark_article_read(99999)` | `{"success": false, "error": "Article with ID 99999 not found"}` |
| Feed discovery failed | `add_blog(url="https://example.com")` | `{"success": false, "error": "Could not discover feed URL for https://example.com. Provide feed_url or scrape_selector parameter."}` |
| Network error | Timeout during scan | Include in `errors` array, continue with other blogs |
| Duplicate blog | `add_blog(name="existing")` | `{"success": false, "error": "Blog with name 'existing' already exists"}` |

---

## 9. Example Usage Scenarios

### Adding a blog with auto-discovery
```
User: "Add Simon Willison's blog"
Agent: [calls add_blog(name="simonwillison", url="https://simonwillison.net")]
→ Feed discovered at https://simonwillison.net/atom/everything/
```

### Checking for new articles
```
User: "What new articles do I have?"
Agent: [calls list_articles(include_read=false)]
→ Shows 12 unread articles across feeds
```

### Reading and marking done
```
User: "Show me the Simon Willison articles and mark them as read"
Agent: [calls list_articles(blog_name="simonwillison")]
Agent: [calls mark_all_read(blog_name="simonwillison")]
→ Marked 5 articles as read
```

### Adding a blog without RSS (scraping)
```
User: "Add Anthropic's engineering blog"
Agent: [calls add_blog(name="anthropic", url="https://www.anthropic.com/engineering")]
→ No feed found
Agent: [calls add_blog(name="anthropic", url="https://www.anthropic.com/engineering", scrape_selector="article a")]
→ Added with scrape selector
```
