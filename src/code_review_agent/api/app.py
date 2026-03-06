"""FastAPI app: webhook endpoint and dashboard."""

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from code_review_agent.agent.graph import create_review_graph
from code_review_agent.agent.llm import complete as llm_complete
from code_review_agent.config import get_chroma_path, get_db_path
from code_review_agent.github_integration.client import GitHubClient
from code_review_agent.github_integration.webhook import get_webhook_secret, parse_pr_event
from code_review_agent.memory.embeddings import get_embedding_provider
from code_review_agent.memory.conventions import ConventionMemory
from code_review_agent.memory.review_history import ReviewHistoryMemory
from code_review_agent.persistence.sqlite_store import SQLiteStore
from code_review_agent.memory.review_history import pattern_id_from_snippet


def _build_services():
    """Build store, memories, and graph (lazy)."""
    store = SQLiteStore(get_db_path())
    chroma_path = get_chroma_path()
    embed = get_embedding_provider()
    convention_memory = ConventionMemory(embed, persist_directory=chroma_path)
    review_history_memory = ReviewHistoryMemory(
        embed,
        get_rejection_count=store.get_pattern_rejection_count,
        persist_directory=chroma_path,
    )
    graph = create_review_graph(convention_memory, review_history_memory, llm_complete)
    return store, convention_memory, review_history_memory, graph


_services = None


def _get_services():
    global _services
    if _services is None:
        _services = _build_services()
    return _services


def create_app(
    run_agent_fn: Optional[Callable] = None,
    github_client: Optional[GitHubClient] = None,
    store: Optional[SQLiteStore] = None,
    review_history_memory: Optional[Any] = None,
) -> FastAPI:
    """Create FastAPI app. Inject run_agent_fn, github_client, store for tests."""
    app = FastAPI(title="Code Review Agent")

    def _run_agent(diff: str):
        if run_agent_fn:
            return run_agent_fn(diff)
        _, _, _, graph = _get_services()
        return graph.invoke({"diff": diff})

    def _get_client():
        return github_client or GitHubClient(os.environ.get("GITHUB_TOKEN"))

    def _get_store():
        return store if store is not None else _get_services()[0]

    def _get_review_history_memory():
        return review_history_memory if review_history_memory is not None else _get_services()[2]

    @app.post("/webhook")
    async def webhook(request: Request) -> Response:
        body = await request.body()
        secret = get_webhook_secret()
        if secret:
            sig = request.headers.get("X-Hub-Signature-256", "")
            if not sig.startswith("sha256="):
                return Response(status_code=401)
            expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return Response(status_code=401)
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}
        if payload.get("pull_request") is None:
            return Response(status_code=200)
        parsed = parse_pr_event(payload)
        if not parsed:
            return Response(status_code=200)
        store = _get_store()
        client = _get_client()
        try:
            diff = client.get_pr_diff(parsed["owner"], parsed["repo"], parsed["pr_number"])
        except Exception:
            return Response(status_code=200)
        result = _run_agent(diff)
        formatted = result.get("formatted")
        if not formatted or not formatted.comments:
            return Response(status_code=200)
        pr_ref = f"{parsed['owner']}/{parsed['repo']}#{parsed['pr_number']}"
        comment_ids = store.save_review(pr_ref, formatted.comments)
        try:
            gh_comment_ids = client.post_inline_review_comments(
                parsed["owner"],
                parsed["repo"],
                parsed["pr_number"],
                parsed["commit_id"],
                formatted.comments,
            )
            for db_id, gh_id in zip(comment_ids, gh_comment_ids):
                store.set_github_comment_id(db_id, gh_id)
        except Exception:
            pass
        return Response(status_code=200)

    @app.post("/api/feedback")
    async def feedback(request: Request) -> Response:
        """Accept feedback for a review comment: { \"github_comment_id\": \"...\", \"outcome\": \"accepted\"|\"rejected\" }."""
        try:
            body = await request.json()
        except Exception:
            return Response(status_code=400)
        gh_id = body.get("github_comment_id")
        outcome = body.get("outcome")
        if not gh_id or outcome not in ("accepted", "rejected"):
            return Response(status_code=400)
        store = _get_store()
        row = store.get_comment_by_github_id(str(gh_id))
        if not row:
            return Response(status_code=404)
        store.update_comment_outcome(row["id"], outcome)
        code_snippet = row.get("code_snippet") or f"{row['file_path']}:{row['line_number']}"
        try:
            review_mem = _get_review_history_memory()
            review_mem.add(
                code_snippet=code_snippet,
                comment_text=row["comment_text"],
                outcome=outcome,
                file_path=row["file_path"],
                severity=row["severity"],
            )
            if outcome == "rejected":
                store.increment_pattern_rejection(pattern_id_from_snippet(code_snippet))
        except Exception:
            pass
        return Response(status_code=200)

    @app.get("/api/reviews", response_class=JSONResponse)
    async def api_reviews() -> JSONResponse:
        """Recent reviews from SQLite (pr_reference, comment count, created)."""
        store = _get_store()
        with store._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT pr_reference, COUNT(*) as cnt, MIN(created_at) as created
                   FROM review_comments GROUP BY pr_reference ORDER BY created DESC LIMIT 20"""
            )
            rows = [{"pr_reference": r[0], "comment_count": r[1], "created_at": r[2]} for r in cur.fetchall()]
        return JSONResponse(content=rows)

    @app.get("/api/stats", response_class=JSONResponse)
    async def api_stats() -> JSONResponse:
        """Comment counts by severity and pattern rejection stats."""
        store = _get_store()
        with store._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT severity, COUNT(*) FROM review_comments GROUP BY severity"""
            )
            by_severity = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*), COALESCE(SUM(rejection_count), 0) FROM pattern_rejections")
            pr_row = cur.fetchone()
            pattern_count = pr_row[0] or 0
            total_rejections = pr_row[1] or 0
        return JSONResponse(content={
            "by_severity": by_severity,
            "pattern_rejection_entries": pattern_count,
            "total_rejection_count": total_rejections,
        })

    _dashboard_path = Path(__file__).resolve().parent / "dashboard" / "index.html"

    @app.get("/dashboard", response_class=HTMLResponse)
    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        """Serve minimal dashboard HTML."""
        if _dashboard_path.exists():
            return HTMLResponse(content=_dashboard_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>Dashboard</h1><p>No dashboard file.</p>", status_code=200)

    return app


# Default app instance for uvicorn
app = create_app()
