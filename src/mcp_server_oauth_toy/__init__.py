"""
MCP Server OAuth Toy - A toy MCP server with OAuth authentication for testing.

This server implements:
1. OAuth 2.0 authorization code flow with PKCE
2. A simple 'whoami' MCP tool that returns the authenticated user's name
3. In-memory session storage (for testing purposes)
"""

from .server import main

__all__ = ["main"]
