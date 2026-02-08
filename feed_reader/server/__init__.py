"""MCP server package initialization"""

from feed_reader.config import load_config
from feed_reader.server.app import create_mcp_server

# Create server instance with default configuration
server = create_mcp_server(load_config())

__all__ = ["server", "create_mcp_server"]
