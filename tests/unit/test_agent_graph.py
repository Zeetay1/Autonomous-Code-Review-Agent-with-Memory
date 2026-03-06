"""Phase 2: LangGraph end-to-end with mocked LLM; structured output validation."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_review_agent.agent.graph import create_review_graph
from code_review_agent.schemas import ReviewOutput


@pytest.fixture
def sample_diff():
    """Sample diff content from fixtures."""
    path = Path(__file__).resolve().parent.parent / "fixtures" / "sample.diff"
    return path.read_text()


def test_agent_runs_e2e_on_sample_diff(
    convention_memory,
    review_history_memory,
    fixtures_docs_path,
    sample_diff,
):
    """Agent runs end-to-end on a sample diff file without errors; produces ReviewOutput."""
    convention_memory.index_file(fixtures_docs_path / "CONVENTIONS.md")
    mock_llm = MagicMock(
        return_value='[{"file_path":"src/foo.py","line_number":2,"severity":"warning","comment_text":"Add type hints for process_data and input."}]'
    )
    graph = create_review_graph(
        convention_memory,
        review_history_memory,
        mock_llm,
    )
    initial = {"diff": sample_diff}
    result = graph.invoke(initial)
    assert "formatted" in result
    ro = result["formatted"]
    assert ro is not None
    assert isinstance(ro, ReviewOutput)
    assert hasattr(ro, "comments")
    assert hasattr(ro, "summary")
    assert ro.summary.total_comments >= 0
    assert ro.summary.blocking_count <= 3
