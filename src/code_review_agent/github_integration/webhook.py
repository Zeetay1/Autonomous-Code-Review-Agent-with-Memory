"""Parse GitHub webhook payloads and trigger review pipeline."""

import os
from typing import Any


def parse_pr_event(payload: dict) -> dict | None:
    """
    Parse pull_request event. Returns dict with owner, repo, pr_number, commit_id
    or None if not a supported event.
    """
    if payload.get("action") not in ("opened", "synchronize"):
        return None
    pr = payload.get("pull_request") or {}
    base = pr.get("base") or {}
    repo = base.get("repo") or {}
    full_name = repo.get("full_name") or ""
    parts = full_name.split("/", 1)
    if len(parts) != 2:
        return None
    owner, repo_name = parts
    pr_number = pr.get("number")
    head = pr.get("head") or {}
    commit_id = (head.get("sha") or "").strip()
    if not commit_id or not pr_number:
        return None
    return {"owner": owner, "repo": repo_name, "pr_number": pr_number, "commit_id": commit_id}


def get_webhook_secret() -> str | None:
    """Return GITHUB_WEBHOOK_SECRET if set."""
    return os.environ.get("GITHUB_WEBHOOK_SECRET") or None
