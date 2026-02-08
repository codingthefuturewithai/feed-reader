"""MCP Feed Tools Integration Tests.

This test suite validates the feed reader MCP tools work correctly when accessed
via the actual MCP client, testing the complete protocol flow.
"""

import json
import uuid
import pytest
from mcp import types
from .conftest import extract_text_content, extract_error_text


def unique_id() -> str:
    """Generate a unique ID for test isolation."""
    return str(uuid.uuid4())[:8]


# Use anyio instead of pytest-asyncio to match SDK approach
pytestmark = pytest.mark.anyio


class TestFeedToolDiscovery:
    """Test feed tool discovery functionality."""

    async def test_all_feed_tools_discoverable(self, mcp_session):
        """Verify all 8 feed tools are registered.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session
        tools_response = await session.list_tools()

        tool_names = [tool.name for tool in tools_response.tools]

        expected_tools = [
            "add_blog",
            "remove_blog",
            "list_blogs",
            "scan_blogs",
            "list_articles",
            "mark_article_read",
            "mark_all_read",
            "mark_article_unread",
        ]

        for expected in expected_tools:
            assert expected in tool_names, (
                f"Feed tool {expected} not found in {tool_names} (transport: {transport})"
            )

    async def test_no_kwargs_in_feed_tool_schemas(self, mcp_session):
        """Test that no feed tool has a 'kwargs' parameter (MCP compatibility).

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session
        tools_response = await session.list_tools()

        feed_tool_names = [
            "add_blog", "remove_blog", "list_blogs", "scan_blogs",
            "list_articles", "mark_article_read", "mark_all_read", "mark_article_unread",
        ]

        for tool in tools_response.tools:
            if tool.name in feed_tool_names:
                if tool.inputSchema:
                    properties = tool.inputSchema.get("properties", {})
                    assert "kwargs" not in properties, (
                        f"Feed tool {tool.name} has kwargs parameter which breaks MCP compatibility (transport: {transport})"
                    )

    async def test_feed_tools_have_descriptions(self, mcp_session):
        """Test that all feed tools have descriptions.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session
        tools_response = await session.list_tools()

        feed_tool_names = [
            "add_blog", "remove_blog", "list_blogs", "scan_blogs",
            "list_articles", "mark_article_read", "mark_all_read", "mark_article_unread",
        ]

        for tool in tools_response.tools:
            if tool.name in feed_tool_names:
                assert tool.description, (
                    f"Feed tool {tool.name} missing description (transport: {transport})"
                )


class TestListBlogsExecution:
    """Test list_blogs tool execution."""

    async def test_list_blogs_empty(self, mcp_session):
        """Test list_blogs returns empty list when no blogs exist.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_blogs", {})

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert "count" in data
        assert "blogs" in data
        assert isinstance(data["blogs"], list)


class TestAddBlogExecution:
    """Test add_blog tool execution."""

    async def test_add_blog_requires_name_and_url(self, mcp_session):
        """Test add_blog requires name and url parameters.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        # Missing both - should error
        result = await session.call_tool("add_blog", {})

        assert result.isError, "Should error when required parameters are missing"

    async def test_add_blog_with_feed_url(self, mcp_session):
        """Test add_blog with explicit feed URL.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session
        test_id = unique_id()

        result = await session.call_tool("add_blog", {
            "name": f"Test Blog {test_id}",
            "url": f"https://example-{test_id}.com/test-feed-url",
            "feed_url": f"https://example-{test_id}.com/feed.xml",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert "blog" in data
        assert data["blog"]["name"] == f"Test Blog {test_id}"
        assert data["blog"]["feed_url"] == f"https://example-{test_id}.com/feed.xml"

    async def test_add_blog_with_scrape_selector(self, mcp_session):
        """Test add_blog with scrape selector instead of feed URL.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session
        test_id = unique_id()

        result = await session.call_tool("add_blog", {
            "name": f"Scrape Blog {test_id}",
            "url": f"https://example-scrape-{test_id}.com/scrape-test",
            "scrape_selector": "article.post a",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert data["blog"]["scrape_selector"] == "article.post a"


class TestRemoveBlogExecution:
    """Test remove_blog tool execution."""

    async def test_remove_blog_not_found(self, mcp_session):
        """Test remove_blog returns error for non-existent blog.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("remove_blog", {
            "name": "Nonexistent Blog 12345",
        })

        assert not result.isError, f"Tool should return success=False, not error: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is False
        assert "error" in data or "not found" in str(data).lower()


class TestBlogLifecycle:
    """Test complete blog lifecycle: add → list → remove."""

    async def test_blog_lifecycle(self, mcp_session):
        """Test adding, listing, and removing a blog.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session
        test_id = unique_id()
        blog_name = f"Lifecycle Test Blog {test_id}"

        # Step 1: Add blog
        add_result = await session.call_tool("add_blog", {
            "name": blog_name,
            "url": f"https://lifecycle-test-{test_id}.com",
            "feed_url": f"https://lifecycle-test-{test_id}.com/feed.xml",
        })

        assert not add_result.isError, f"Add failed: {add_result}"
        add_data = json.loads(extract_text_content(add_result))
        assert add_data["success"] is True

        # Step 2: List blogs - should include our blog
        list_result = await session.call_tool("list_blogs", {})
        assert not list_result.isError, f"List failed: {list_result}"
        list_data = json.loads(extract_text_content(list_result))

        blog_names = [b["name"] for b in list_data["blogs"]]
        assert blog_name in blog_names, f"Blog not found in list: {blog_names}"

        # Step 3: Remove blog
        remove_result = await session.call_tool("remove_blog", {"name": blog_name})
        assert not remove_result.isError, f"Remove failed: {remove_result}"
        remove_data = json.loads(extract_text_content(remove_result))
        assert remove_data["success"] is True

        # Step 4: Verify blog is gone
        verify_result = await session.call_tool("list_blogs", {})
        verify_data = json.loads(extract_text_content(verify_result))

        remaining_names = [b["name"] for b in verify_data["blogs"]]
        assert blog_name not in remaining_names, f"Blog still exists after removal: {remaining_names}"


class TestListArticlesExecution:
    """Test list_articles tool execution."""

    async def test_list_articles_empty(self, mcp_session):
        """Test list_articles returns empty list when no articles exist.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {})

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert "count" in data
        assert "articles" in data
        assert isinstance(data["articles"], list)

    async def test_list_articles_with_filters(self, mcp_session):
        """Test list_articles with optional filters.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {
            "include_read": "true",
            "limit": "10",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True


class TestMarkArticleReadExecution:
    """Test mark_article_read tool execution."""

    async def test_mark_article_read_not_found(self, mcp_session):
        """Test mark_article_read with non-existent article ID.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("mark_article_read", {
            "article_id": "99999",
        })

        assert not result.isError, f"Tool should return success=False, not error: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is False
        assert "error" in data or "not found" in str(data).lower()


class TestMarkArticleUnreadExecution:
    """Test mark_article_unread tool execution."""

    async def test_mark_article_unread_not_found(self, mcp_session):
        """Test mark_article_unread with non-existent article ID.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("mark_article_unread", {
            "article_id": "99999",
        })

        assert not result.isError, f"Tool should return success=False, not error: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is False


class TestMarkAllReadExecution:
    """Test mark_all_read tool execution."""

    async def test_mark_all_read_no_articles(self, mcp_session):
        """Test mark_all_read when there are no unread articles.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("mark_all_read", {})

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert "articles_marked_read" in data

    async def test_mark_all_read_nonexistent_blog(self, mcp_session):
        """Test mark_all_read with non-existent blog filter.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("mark_all_read", {
            "blog_name": "Nonexistent Blog 99999",
        })

        assert not result.isError, f"Tool should return success=False, not error: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is False


class TestScanBlogsExecution:
    """Test scan_blogs tool execution."""

    async def test_scan_blogs_no_blogs(self, mcp_session):
        """Test scan_blogs when there are no blogs configured.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("scan_blogs", {})

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert "blogs_scanned" in data
        assert "total_new_articles" in data

    async def test_scan_blogs_nonexistent_blog(self, mcp_session):
        """Test scan_blogs with non-existent blog name.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("scan_blogs", {
            "blog_name": "Nonexistent Blog 99999",
        })

        assert not result.isError, f"Tool should return success=False, not error: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is False


class TestArticleReadStatusLifecycle:
    """Test article read/unread status lifecycle."""

    async def test_article_status_requires_valid_id(self, mcp_session):
        """Test that article status tools handle invalid IDs gracefully.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        # Test mark_article_read with invalid ID
        read_result = await session.call_tool("mark_article_read", {
            "article_id": "999999",
        })
        read_data = json.loads(extract_text_content(read_result))
        assert read_data["success"] is False

        # Test mark_article_unread with invalid ID
        unread_result = await session.call_tool("mark_article_unread", {
            "article_id": "999999",
        })
        unread_data = json.loads(extract_text_content(unread_result))
        assert unread_data["success"] is False


class TestParameterConversion:
    """Test that parameter type conversion works correctly for feed tools."""

    async def test_list_articles_string_parameters(self, mcp_session):
        """Test that string parameters are correctly converted.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        # MCP sends parameters as strings, test they're converted
        result = await session.call_tool("list_articles", {
            "include_read": "true",
            "limit": "25",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True

    async def test_mark_article_read_string_id(self, mcp_session):
        """Test that article_id string is correctly converted to int.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        # Even though ID doesn't exist, this tests type conversion
        result = await session.call_tool("mark_article_read", {
            "article_id": "12345",
        })

        # Should not error on type conversion
        assert not result.isError, f"Type conversion failed: {result}"


class TestListArticlesDateFiltering:
    """Test list_articles date filtering parameters."""

    async def test_list_articles_with_days_parameter(self, mcp_session):
        """Test list_articles with days parameter for recent articles.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {
            "days": "7",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert "filters_applied" in data
        assert data["filters_applied"]["days"] == 7

    async def test_list_articles_with_since_parameter(self, mcp_session):
        """Test list_articles with since parameter for date range.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {
            "since": "2025-01-01",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert "filters_applied" in data
        assert data["filters_applied"]["since"] == "2025-01-01"

    async def test_list_articles_with_before_parameter(self, mcp_session):
        """Test list_articles with before parameter for date range.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {
            "before": "2025-12-31",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert "filters_applied" in data
        assert data["filters_applied"]["before"] == "2025-12-31"

    async def test_list_articles_with_date_range(self, mcp_session):
        """Test list_articles with both since and before for a date range.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {
            "since": "2025-01-01",
            "before": "2025-06-30",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert data["filters_applied"]["since"] == "2025-01-01"
        assert data["filters_applied"]["before"] == "2025-06-30"

    async def test_list_articles_with_datetime_format(self, mcp_session):
        """Test list_articles accepts full ISO datetime format.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {
            "since": "2025-01-01T00:00:00",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True

    async def test_list_articles_invalid_date_format(self, mcp_session):
        """Test list_articles returns error for invalid date format.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {
            "since": "not-a-date",
        })

        assert not result.isError, f"Tool should return success=False, not MCP error: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is False
        assert "error" in data
        assert "Invalid" in data["error"]

    async def test_list_articles_combined_filters(self, mcp_session):
        """Test list_articles with date filtering combined with other filters.

        This test runs with both STDIO and Streamable HTTP transports.
        """
        session, transport = mcp_session

        result = await session.call_tool("list_articles", {
            "days": "30",
            "include_read": "true",
            "limit": "10",
        })

        assert not result.isError, f"Tool execution failed: {result}"

        text_content = extract_text_content(result)
        data = json.loads(text_content)

        assert data["success"] is True
        assert data["filters_applied"]["days"] == 30
        assert data["filters_applied"]["include_read"] is True
        assert data["filters_applied"]["limit"] == 10


# Test runner for direct execution
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
