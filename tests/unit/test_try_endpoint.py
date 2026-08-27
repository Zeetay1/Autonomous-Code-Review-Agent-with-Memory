"""POST /api/try: public 'try it yourself' endpoint (diff in, review out, rate-limited)."""

import pytest
from fastapi.testclient import TestClient

from code_review_agent.api import app as app_module
from code_review_agent.api.app import create_app
from code_review_agent.persistence.sqlite_store import SQLiteStore
from code_review_agent.schemas import Comment, ReviewOutput, ReviewSummary


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """Rate-limit counters are module-level (shared across requests in one process);
    reset between tests so they don't interfere with each other."""
    app_module._try_request_times.clear()
    app_module._try_daily_count["day"] = None
    app_module._try_daily_count["count"] = 0
    yield


@pytest.fixture
def mock_agent_result():
    return {
        "formatted": ReviewOutput(
            comments=[
                Comment(file_path="a.py", line_number=1, severity="nit", comment_text="Sample", suggested_replacement=None),
            ],
            summary=ReviewSummary(total_comments=1, blocking_count=0, warning_count=0, nit_count=1),
        ),
    }


def test_try_returns_review_output_for_valid_diff(mock_agent_result):
    app = create_app(run_agent_fn=lambda diff: mock_agent_result)
    client = TestClient(app)
    resp = client.post("/api/try", json={"diff": "diff --git a/a.py b/a.py\n+x = 1\n"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total_comments"] == 1
    assert data["comments"][0]["comment_text"] == "Sample"


def test_try_rejects_empty_diff():
    app = create_app(run_agent_fn=lambda diff: {"formatted": None})
    client = TestClient(app)
    resp = client.post("/api/try", json={"diff": "   "})
    assert resp.status_code == 400


def test_try_rejects_oversized_diff():
    app = create_app(run_agent_fn=lambda diff: {"formatted": None})
    client = TestClient(app)
    huge = "x" * (app_module.TRY_MAX_DIFF_CHARS + 1)
    resp = client.post("/api/try", json={"diff": huge})
    assert resp.status_code == 400


def test_try_surfaces_agent_failure_as_502():
    def _raise(diff):
        raise RuntimeError("no ANTHROPIC_API_KEY")

    app = create_app(run_agent_fn=_raise)
    client = TestClient(app)
    resp = client.post("/api/try", json={"diff": "some diff"})
    assert resp.status_code == 502


def test_try_enforces_per_ip_rate_limit(mock_agent_result):
    app = create_app(run_agent_fn=lambda diff: mock_agent_result)
    client = TestClient(app)
    for _ in range(app_module.TRY_RATE_LIMIT_PER_IP):
        resp = client.post("/api/try", json={"diff": "x"})
        assert resp.status_code == 200
    resp = client.post("/api/try", json={"diff": "x"})
    assert resp.status_code == 429


def test_try_does_not_persist_to_review_store(tmp_path, mock_agent_result):
    store = SQLiteStore(str(tmp_path / "try_endpoint.db"))
    app = create_app(run_agent_fn=lambda diff: mock_agent_result, store=store)
    client = TestClient(app)
    resp = client.post("/api/try", json={"diff": "x"})
    assert resp.status_code == 200
    assert store.get_review_by_pr("") == []
    with store._conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM review_comments").fetchone()[0]
    assert count == 0
