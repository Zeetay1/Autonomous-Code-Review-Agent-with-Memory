"""Local harness: run full pipeline on sample diff and produce structured output."""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_harness_produces_structured_output():
    """Run harness on sample.diff with --mock-llm; output is structured (Summary or JSON)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    src = str(repo_root / "src")
    diff_file = repo_root / "tests" / "fixtures" / "sample.diff"
    script = repo_root / "scripts" / "run_harness.py"
    env = {
        **os.environ,
        "PYTHONPATH": src,
        "CODE_REVIEW_AGENT_DB_PATH": ":memory:",
        "CODE_REVIEW_AGENT_CHROMA_PATH": str(repo_root / "tmp_chroma_harness"),
    }
    result = subprocess.run(
        [sys.executable, str(script), str(diff_file), "--mock-llm", "--json"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, (result.stderr or result.stdout)
    out = result.stdout
    data = json.loads(out)
    assert "comments" in data
    assert "summary" in data
    assert "total_comments" in data["summary"]
    assert "blocking_count" in data["summary"]
