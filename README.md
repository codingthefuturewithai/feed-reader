# Feed Reader

An MCP server for managing RSS feeds and articles. Subscribe to blogs, scan for new articles, and track your reading progress — all accessible to AI assistants.

## 🚀 Quick Start

**Using Claude Code?** Run `/server-overview` to see exactly what this server can do, or `/feed-reader` to start using it immediately.

---

## Quick Start for MCP Clients

### 1. Run with Docker (Recommended)

The simplest way to run the server:

```bash
# Clone and start
git clone https://github.com/codingthefuturewithai/feed-reader.git
cd feed-reader
python scripts/docker.py start
```

Then add to Claude Code:
```bash
claude mcp add feed-reader --transport http http://localhost:19000/mcp
```

### 2. Configure your MCP client

**For Claude Desktop**: Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

```json
{
  "feed-reader": {
    "type": "http",
    "url": "http://localhost:19000/mcp"
  }
}
```

**For STDIO transport** (alternative):
```json
{
  "feed-reader": {
    "command": "uvx",
    "args": ["feed-reader-server"]
  }
}
```

### 3. Start using the tools

Once configured, you can ask your AI assistant to:
- "Add Simon Willison's blog to my feeds"
- "What's new in my feeds today?"
- "Show me articles from the last week"
- "Mark all articles as read"

## Features

- **Feed Management** - Add, remove, and list RSS/Atom feeds with auto-discovery
- **Article Tracking** - Scan for new articles, filter by date/blog/read status
- **Read Status** - Mark articles as read/unread individually or in bulk
- **Auto-Discovery** - Automatically finds RSS feeds from blog URLs
- **Multiple Transports** - STDIO and Streamable HTTP support
- **Unified Logging** - SQLite-based logging with Streamlit UI
- **Docker Support** - One-command deployment

## Available Tools

### add_blog

Add a new RSS/Atom feed to track.

**Parameters:**
- `name` (required, string): Display name for the blog
- `url` (required, string): Blog URL (RSS feed will be auto-discovered)
- `feed_url` (optional, string): Direct RSS feed URL (skips auto-discovery)
- `scrape_selector` (optional, string): CSS selector for scraping non-RSS sites

**Example:**
```json
{
  "name": "Simon Willison",
  "url": "https://simonwillison.net"
}
```

### remove_blog

Remove a feed from tracking.

**Parameters:**
- `name` (required, string): Name of the blog to remove

### list_blogs

List all tracked feeds with article counts.

**Returns:** List of blogs with unread/total article counts.

### scan_blogs

Fetch new articles from feeds.

**Parameters:**
- `blog_name` (optional, string): Scan only this blog (scans all if omitted)

### list_articles

List articles with filtering options.

**Parameters:**
- `blog_name` (optional, string): Filter by blog name
- `include_read` (optional, boolean): Include read articles (default: false)
- `limit` (optional, integer): Maximum articles to return (default: 50)
- `days` (optional, integer): Articles from last N days
- `since` (optional, string): Articles after this date (YYYY-MM-DD)
- `before` (optional, string): Articles before this date (YYYY-MM-DD)

**Example:**
```json
{
  "blog_name": "Simon Willison",
  "days": 7,
  "include_read": true
}
```

### mark_article_read

Mark a single article as read.

**Parameters:**
- `article_id` (required, integer): ID of the article to mark

### mark_article_unread

Mark an article as unread.

**Parameters:**
- `article_id` (required, integer): ID of the article to mark

### mark_all_read

Mark all articles as read.

**Parameters:**
- `blog_name` (optional, string): Only mark articles from this blog

## Docker Deployment

Run the MCP server as a Docker container for isolated, reproducible deployments.

### Quick Start

```bash
python scripts/docker.py start
```

This builds the image, starts the container, and verifies health. The MCP endpoint will be available at `http://localhost:19000/mcp`.

### Commands

| Command | Description |
|---------|-------------|
| `python scripts/docker.py start` | Build image and start container |
| `python scripts/docker.py stop` | Stop and remove container |
| `python scripts/docker.py restart` | Restart container (without rebuild) |
| `python scripts/docker.py update` | Rebuild image and restart (for code changes) |
| `python scripts/docker.py status` | Show container status |
| `python scripts/docker.py logs` | Tail container logs |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | `19000` | Host port mapped to the container |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `MCP_DNS_REBINDING_PROTECTION` | `false` | Enable DNS rebinding protection |
| `MCP_ALLOWED_HOSTS` | _(empty)_ | Comma-separated allowed Host headers |

## Logging

The server logs all activity to both stderr and a rotating log file. Log files are stored in OS-specific locations:

- **macOS**: `~/Library/Logs/mcp-servers/feed_reader.log`
- **Linux**: `~/.local/state/mcp-servers/logs/feed_reader.log`
- **Windows**: `%LOCALAPPDATA%\mcp-servers\logs\feed_reader.log`

Logs rotate at 10MB with 5 backups kept. Control verbosity with `LOG_LEVEL`:

```bash
LOG_LEVEL=DEBUG python -m feed_reader.server.app
```

## Requirements

- Python 3.11 or 3.12
- Operating Systems: Linux, macOS, Windows
- Docker (optional, for containerized deployment)

## Development

For development setup, testing, and contribution guidelines, see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Author

Tim Kitchens - codingthefuturewithai@gmail.com
