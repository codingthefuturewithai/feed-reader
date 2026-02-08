"""Main module for feed_reader MCP server.

This module allows the server to be run as a Python module using:
python -m feed_reader

It delegates to the server application's main function.
"""

from feed_reader.server.app import main

if __name__ == "__main__":
    main()