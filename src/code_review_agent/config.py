"""Configuration: DB path, Chroma path, and env-based settings."""

import os
from pathlib import Path


def get_db_path() -> str:
    """SQLite database path. Use in-memory for tests when set to :memory:."""
    return os.environ.get("CODE_REVIEW_AGENT_DB_PATH", "review_agent.db")


def get_chroma_path() -> str:
    """ChromaDB persistence path. Tests can override to a temp dir."""
    return os.environ.get("CODE_REVIEW_AGENT_CHROMA_PATH", str(Path.cwd() / "chroma_data"))
