"""Pydantic models: Comment, ReviewSummary, memory entries, and agent state."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Comment(BaseModel):
    """A single inline review comment."""

    file_path: str
    line_number: int
    severity: Literal["nit", "warning", "blocking"]
    comment_text: str
    suggested_replacement: Optional[str] = None


class ReviewSummary(BaseModel):
    """Counts of comments by severity."""

    total_comments: int
    blocking_count: int
    warning_count: int
    nit_count: int


class ReviewOutput(BaseModel):
    """Full review: comments and summary."""

    comments: list[Comment]
    summary: ReviewSummary


class ConventionEntry(BaseModel):
    """A chunk of codebase documentation."""

    text: str
    source_doc: str
    section: Optional[str] = None


class PastDecisionEntry(BaseModel):
    """A past review comment with outcome (for memory retrieval)."""

    code_snippet: str
    comment_text: str
    outcome: Literal["accepted", "rejected"]
    file_path: str
    severity: str
    pattern_id: Optional[str] = None


class RetrievedMemory(BaseModel):
    """
    Unified memory context returned by retrieval.
    conventions: relevant doc chunks for the code snippet.
    past_decisions: relevant past comments (accepted/rejected) with down-weighting applied.
    """

    conventions: list[ConventionEntry] = Field(default_factory=list)
    past_decisions: list[PastDecisionEntry] = Field(default_factory=list)
