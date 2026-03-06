"""LangGraph definition: retrieve -> analyze -> generate -> format -> END."""

from functools import partial
from typing import Any, Callable, TypedDict

from langgraph.constants import END
from langgraph.graph import StateGraph

from code_review_agent.agent.steps import (
    KEY_ANALYSIS,
    KEY_COMMENTS,
    KEY_DIFF,
    KEY_FORMATTED,
    KEY_RETRIEVED_MEMORY,
    analyze_step,
    format_step,
    generate_step,
    retrieve_step,
)


class ReviewState(TypedDict, total=False):
    """State for the review agent graph."""

    diff: str
    retrieved_memory: Any
    analysis: str
    comments: list
    formatted: Any


def create_review_graph(
    convention_memory: Any,
    review_history_memory: Any,
    llm_complete: Callable[[str, str | None], str],
):
    """Build and compile the review agent graph with injected memory and LLM."""
    builder = StateGraph(ReviewState)

    retrieve_node = partial(
        retrieve_step,
        convention_memory=convention_memory,
        review_history_memory=review_history_memory,
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
