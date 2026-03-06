"""Agent steps: retrieve -> analyze -> generate -> format. Each reads state and returns updates."""

import json
import re
from typing import Any, Callable

from code_review_agent.schemas import (
    Comment,
    ReviewOutput,
    ReviewSummary,
    RetrievedMemory,
)
from code_review_agent.memory.retrieval import retrieve

# State keys
KEY_DIFF = "diff"
KEY_RETRIEVED_MEMORY = "retrieved_memory"
KEY_ANALYSIS = "analysis"
KEY_COMMENTS = "comments"
KEY_FORMATTED = "formatted"

# Max blocking comments per review (hard constraint)
MAX_BLOCKING = 3


def retrieve_step(
    state: dict,
    convention_memory: Any,
    review_history_memory: Any,
) -> dict:
    """Run unified retrieval on the diff snippet and set retrieved_memory."""
    diff = state.get(KEY_DIFF) or ""
    snippet = diff[:8000] if len(diff) > 8000 else diff  # cap for embedding
    mem = retrieve(
        snippet,
        convention_memory,
        review_history_memory,
        convention_top_k=5,
        past_decisions_top_k=5,
    )
    return {KEY_RETRIEVED_MEMORY: mem}


def analyze_step(state: dict, llm_complete: Callable[[str, str | None], str]) -> dict:
    """Call LLM with diff + memory to produce a structured analysis (list of issues)."""
    diff = state.get(KEY_DIFF) or ""
    mem: RetrievedMemory | None = state.get(KEY_RETRIEVED_MEMORY)
    conv_text = ""
    past_text = ""
    if mem:
        conv_text = "\n".join(c.text for c in mem.conventions[:5])
        past_text = "\n".join(
            f"- {p.outcome}: {p.comment_text}" for p in mem.past_decisions[:5]
        )
    system = (
        "You are a code reviewer. Output a JSON array of issues. Each issue: file_path, line_number, severity (nit|warning|blocking), comment_text, suggested_replacement (optional). "
        "Only output the JSON array, no other text."
    )
    prompt = f"Diff:\n{diff[:12000]}\n\nRelevant conventions:\n{conv_text}\n\nPast decisions:\n{past_text}\n\nList issues as JSON array:"
    raw = llm_complete(prompt, system)
    # Extract JSON array from response
    analysis = raw.strip()
    match = re.search(r"\[[\s\S]*\]", analysis)
    if match:
        analysis = match.group(0)
    return {KEY_ANALYSIS: analysis}


def generate_step(state: dict) -> dict:
    """Parse analysis into Comment list; if analysis is already valid JSON, parse it directly."""
    analysis = state.get(KEY_ANALYSIS) or "[]"
    comments: list[Comment] = []
    try:
        items = json.loads(analysis)
        for item in items:
            if isinstance(item, dict):
                comments.append(
                    Comment(
                        file_path=str(item.get("file_path", "")),
                        line_number=int(item.get("line_number", 0)),
                        severity=item.get("severity", "nit"),
                        comment_text=str(item.get("comment_text", "")),
                        suggested_replacement=item.get("suggested_replacement"),
                    )
                )
    except (json.JSONDecodeError, ValueError):
        pass
    return {KEY_COMMENTS: comments}


def format_step(state: dict) -> dict:
    """Enforce max 3 blocking; build ReviewSummary; set formatted ReviewOutput."""
    comments: list[Comment] = list(state.get(KEY_COMMENTS) or [])
    blocking = [c for c in comments if c.severity == "blocking"]
    if len(blocking) > MAX_BLOCKING:
        # Downgrade excess blocking to warning (by line order: keep first 3)
        blocking.sort(key=lambda c: (c.file_path, c.line_number))
        keep_blocking = {id(c) for c in blocking[:MAX_BLOCKING]}
        new_comments = []
        for c in comments:
            if c.severity == "blocking" and id(c) not in keep_blocking:
                new_comments.append(
                    Comment(
                        file_path=c.file_path,
                        line_number=c.line_number,
                        severity="warning",
                        comment_text=c.comment_text,
                        suggested_replacement=c.suggested_replacement,
                    )
                )
            else:
                new_comments.append(c)
        comments = new_comments
    bc = sum(1 for c in comments if c.severity == "blocking")
    wc = sum(1 for c in comments if c.severity == "warning")
    nc = sum(1 for c in comments if c.severity == "nit")
    summary = ReviewSummary(
        total_comments=len(comments),
        blocking_count=bc,
        warning_count=wc,
        nit_count=nc,
    )
    return {KEY_FORMATTED: ReviewOutput(comments=comments, summary=summary)}


