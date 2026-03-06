"""Phase 3: Webhook returns 200 and triggers agent + persistence with mock payload."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from code_review_agent.api.app import create_app
from code_review_agent.persistence.sqlite_store import SQLiteStore
from code_review_agent.schemas import Comment, ReviewOutput, ReviewSummary


@pytest.fixture
def sample_diff():
    path = Path(__file__).resolve().parent.parent / "fixtures" / "sample.diff"
    return path.read_text()


@pytest.fixture
def mock_github_client(sample_diff):
    client = MagicMock()
    client.get_pr_diff.return_value = sample_diff
    client.post_inline_review_comments.return_value = []
    return client


@pytest.fixture
def mock_agent_result():
    return {
        "formatted": ReviewOutput(
            comments=[
                Comment(file_path="src/foo.py", line_number=2, severity="warning", comment_text="Add type hints", suggested_replacement=None),
            ],
            summary=ReviewSummary(total_comments=1, blocking_count=0, warning_count=1, nit_count=0),
        ),
    }


def test_webhook_returns_200_and_persists(
    tmp_path,
    mock_github_client,
    mock_agent_result,
):
    """Webhook with valid PR payload returns 200 and persists comments to SQLite."""
    store = SQLiteStore(str(tmp_path / "webhook_test.db"))
    app = create_app(
        run_agent_fn=lambda diff: mock_agent_result,
        github_client=mock_github_client,
        store=store,
    )
    client = TestClient(app)
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 1,
            "base": {"repo": {"full_name": "owner/repo"}},
            "head": {"sha": "abc123"},
        },
    }
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 200
    rows = store.get_review_by_pr("owner/repo#1")
    assert len(rows) == 1
    assert rows[0]["comment_text"] == "Add type hints"
    mock_github_client.get_pr_diff.assert_called_once_with("owner", "repo", 1)
