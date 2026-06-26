"""Backward-compatible entrypoint. Prefer workspace_agent_relay_mcp.app.build_app."""

from .app import build_app

__all__ = ["build_app"]
