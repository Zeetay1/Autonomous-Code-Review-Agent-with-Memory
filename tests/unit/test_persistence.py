"""Phase 3: SQLite persistence for review comments and pattern rejections."""

import pytest

from code_review_agent.persistence.sqlite_store import SQLiteStore
from code_review_agent.schemas import Comment


@pytest.fixture
def sqlite_store(tmp_path):
    """SQLite store using a temp file."""
    return SQLiteStore(str(tmp_path / "test.db"))


def test_save_review_and_get_by_pr(sqlite_store):
    """Save review comments and retrieve by PR reference."""
    comments = [
        Comment(file_path="a.py", line_number=1, severity="blocking", comment_text="Fix", suggested_replacement=None),
        Comment(file_path="b.py", line_number=2, severity="nit", comment_text="Optional", suggested_replacement=None),
    ]
    ids = sqlite_store.save_review("owner/repo#42", comments)
    assert len(ids) == 2
    rows = sqlite_store.get_review_by_pr("owner/repo#42")
    assert len(rows) == 2
    assert rows[0]["comment_text"] == "Fix"
    assert rows[0]["severity"] == "blocking"
    assert rows[0]["outcome"] is None


def test_update_comment_outcome(sqlite_store):
    """Updating outcome persists."""
    ids = sqlite_store.save_review("o/r#1", [
        Comment(file_path="x.py", line_number=1, severity="warning", comment_text="Hi", suggested_replacement=None),
    ])
    sqlite_store.update_comment_outcome(ids[0], "accepted")
    rows = sqlite_store.get_review_by_pr("o/r#1")
    assert rows[0]["outcome"] == "accepted"


def test_pattern_rejection_increment_and_get(sqlite_store):
    """Increment and get pattern rejection count."""
    assert sqlite_store.get_pattern_rejection_count("pid1") == 0
    sqlite_store.increment_pattern_rejection("pid1")
    sqlite_store.increment_pattern_rejection("pid1")
    assert sqlite_store.get_pattern_rejection_count("pid1") == 2
