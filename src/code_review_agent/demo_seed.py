"""Seed realistic sample review data for a public/hosted demo instance.

Not run by default -- gated behind SEED_DEMO_DATA in api/app.py's startup hook and
scripts/seed_demo_data.py's CLI entrypoint, so local dev and self-hosted instances keep
an honest empty dashboard unless a demo deployment opts in.
"""
from typing import Any

from code_review_agent.memory.review_history import pattern_id_from_snippet
from code_review_agent.persistence.sqlite_store import SQLiteStore
from code_review_agent.schemas import Comment


def seed_demo_data(store: SQLiteStore, review_history_memory: Any) -> bool:
    """Populate store + review_history_memory with a sample PR review, once.

    Idempotent: no-ops (returns False) if review_comments already has rows, so it's
    safe to call on every startup regardless of whether /data is a fresh or a
    persistent volume.
    """
    with store._conn() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM review_comments").fetchone()[0]
    if existing:
        return False

    ids = store.save_review(
        "acme/payments-service#482",
        [
            Comment(
                file_path="src/payments/charge.py", line_number=41, severity="blocking",
                comment_text=(
                    "This mutates the shared `PENDING_CHARGES` dict without a lock; "
                    "concurrent webhook deliveries for the same charge_id will race."
                ),
                suggested_replacement=None,
            ),
            Comment(
                file_path="src/payments/charge.py", line_number=88, severity="warning",
                comment_text="Bare `except Exception: pass` swallows the Stripe API error silently -- at least log it.",
                suggested_replacement=None,
            ),
            Comment(
                file_path="src/payments/retry.py", line_number=12, severity="nit",
                comment_text="Prefer `list[str]` over `List[str]` per CONVENTIONS.md (Python 3.10+ style).",
                suggested_replacement=None,
            ),
        ],
        code_snippets=[
            "PENDING_CHARGES[charge_id] = amount",
            "except Exception:\n    pass",
            "def f(x: List[str])",
        ],
    )
    store.set_github_comment_id(ids[0], "demo_gh_1001")
    store.set_github_comment_id(ids[1], "demo_gh_1002")
    store.set_github_comment_id(ids[2], "demo_gh_1003")

    ids2 = store.save_review(
        "acme/payments-service#479",
        [
            Comment(
                file_path="src/payments/webhook.py", line_number=23, severity="warning",
                comment_text="No idempotency check on webhook replay.",
                suggested_replacement=None,
            ),
        ],
        code_snippets=["def handle_webhook(event):"],
    )
    store.set_github_comment_id(ids2[0], "demo_gh_1004")

    # Simulate feedback history: the real bug got accepted; the style nit has been
    # rejected 5 times across past PRs, so the memory system stops surfacing it.
    store.update_comment_outcome(ids[0], "accepted")
    store.update_comment_outcome(ids[2], "rejected")

    style_nit_snippet = "def f(x: List[str])"
    review_history_memory.add(
        code_snippet=style_nit_snippet,
        comment_text="Prefer list[str] over List[str]",
        outcome="rejected",
        file_path="src/payments/retry.py",
        severity="nit",
    )
    pid = pattern_id_from_snippet(style_nit_snippet)
    for _ in range(5):
        store.increment_pattern_rejection(pid)

    return True
