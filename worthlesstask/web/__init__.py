"""Local web dashboard: JSON API plus one static page."""

from .server import DEFAULT_HOST, DEFAULT_PORT, Dashboard, find_free_port, make_server, serve

__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "Dashboard", "find_free_port", "make_server", "serve"]
