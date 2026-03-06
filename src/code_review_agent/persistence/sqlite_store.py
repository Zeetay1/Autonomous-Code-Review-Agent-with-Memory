"""SQLite persistence: review_comments and pattern_rejections."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from code_review_agent.schemas import Comment

from code_review_agent.config import get_db_path


class SQLiteStore:
    """Persist review comments and pattern rejection counts to SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        self._path = db_path or get_db_path()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS review_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    comment_text TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    pr_reference TEXT NOT NULL,
                    outcome TEXT,
                    github_comment_id TEXT,
                    code_snippet TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS pattern_rejections (
                    pattern_id TEXT PRIMARY KEY,
                    rejection_count INTEGER NOT NULL DEFAULT 0
                )
            """)

    def save_review(self, pr_reference: str, comments: List[Comment], code_snippets: Optional[List[str]] = None) -> List[int]:
        """Persist comments for a PR. code_snippets optional (one per comment) for feedback memory."""
        ids = []
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        snippets = (code_snippets or []) + [None] * len(comments)
        with self._conn() as conn:
            cur = conn.cursor()
            for i, com in enumerate(comments):
                snippet = snippets[i] if i < len(snippets) else None
                cur.execute(
                    """INSERT INTO review_comments
                       (comment_text, file_path, line_number, severity, pr_reference, outcome, code_snippet, created_at)
                       VALUES (?, ?, ?, ?, ?, NULL, ?, ?)""",
                    (com.comment_text, com.file_path, com.line_number, com.severity, pr_reference, snippet, now),
                )
                ids.append(cur.lastrowid)
        return ids

    def get_review_by_pr(self, pr_reference: str) -> List[dict]:
        """Return all comments for a PR as list of dicts (id, comment_text, file_path, line_number, severity, outcome, github_comment_id)."""
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                """SELECT id, comment_text, file_path, line_number, severity, outcome, github_comment_id
                   FROM review_comments WHERE pr_reference = ? ORDER BY id""",
                (pr_reference,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_comment_outcome(self, comment_id: int, outcome: str) -> None:
        """Set outcome (accepted/rejected) for a comment."""
        with self._conn() as c:
            c.execute("UPDATE review_comments SET outcome = ? WHERE id = ?", (outcome, comment_id))

    def set_github_comment_id(self, comment_id: int, github_comment_id: str) -> None:
        """Store GitHub API comment id for later feedback mapping."""
        with self._conn() as c:
            c.execute("UPDATE review_comments SET github_comment_id = ? WHERE id = ?", (github_comment_id, comment_id))

    def get_comment_by_github_id(self, github_comment_id: str) -> Optional[dict]:
        """Return comment row by github_comment_id (id, comment_text, file_path, line_number, severity, code_snippet, outcome)."""
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            row = c.execute(
                "SELECT id, comment_text, file_path, line_number, severity, pr_reference, outcome, code_snippet FROM review_comments WHERE github_comment_id = ?",
                (github_comment_id,),
            ).fetchone()
            return dict(row) if row else None

    def increment_pattern_rejection(self, pattern_id: str) -> None:
        """Increment rejection count for pattern (upsert)."""
        with self._conn() as c:
            c.execute(
                """INSERT INTO pattern_rejections (pattern_id, rejection_count) VALUES (?, 1)
                   ON CONFLICT(pattern_id) DO UPDATE SET rejection_count = rejection_count + 1""",
                (pattern_id,),
            )

    def get_pattern_rejection_count(self, pattern_id: str) -> int:
        """Return rejection count for pattern."""
        with self._conn() as c:
            row = c.execute(
                "SELECT rejection_count FROM pattern_rejections WHERE pattern_id = ?",
                (pattern_id,),
            ).fetchone()
            return row[0] if row else 0
