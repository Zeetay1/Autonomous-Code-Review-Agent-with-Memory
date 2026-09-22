"""LangGraph definition: retrieve -> analyze -> generate -> format -> END."""

from functools import partial
from typing import Any, Callable, TypedDict

from langgraph.constants import END
from langgraph.graph import StateGraph

from code_review_agent.agent.steps import (
    KEY_ANALYSIS,
    KEY_COMMENTS,
    KEY_DIFF,
    KEY_EXISTING_PR_COMMENTS,
    KEY_FORMATTED,
    KEY_PR_REFERENCE,
    KEY_RETRIEVED_MEMORY,
    GetExistingPrComments,
    analyze_step,
    format_step,
    generate_step,
    retrieve_step,
)


class ReviewState(TypedDict, total=False):
    """State for the review agent graph."""

    diff: str
    pr_reference: str
    retrieved_memory: Any
    existing_pr_comments: list
    analysis: str
    comments: list
    formatted: Any


def create_review_graph(
    convention_memory: Any,
    review_history_memory: Any,
    llm_complete: Callable[[str, str | None], str],
    get_existing_pr_comments: "GetExistingPrComments | None" = None,
):
    """Build and compile the review agent graph with injected memory and LLM.

    get_existing_pr_comments (optional): looks up comment text already posted on a
    PR, so the agent avoids repeating itself across multiple pushes to the same PR.
    """
    builder = StateGraph(ReviewState)

    retrieve_node = partial(
        retrieve_step,
        convention_memory=convention_memory,
        review_history_memory=review_history_memory,
        get_existing_pr_comments=get_existing_pr_comments,
    )
    analyze_node = partial(analyze_step, llm_complete=llm_complete)

    builder.add_node("retrieve", retrieve_node)
    builder.add_node("analyze", analyze_node)
    builder.add_node("generate", generate_step)
    builder.add_node("format", format_step)

    builder.add_edge("retrieve", "analyze")
    builder.add_edge("analyze", "generate")
    builder.add_edge("generate", "format")
    builder.add_edge("format", END)

    builder.set_entry_point("retrieve")

    return builder.compile()
