# Autonomous Code Review Agent with Memory

A stateful code-review agent that reviews pull-request diffs against a project's own
conventions, remembers which of its past comments developers accepted or rejected, and
uses that history to stop repeating feedback nobody wants. It is built to demonstrate an
LLM agent with **persistent, queryable memory** rather than a stateless prompt-in/text-out
wrapper around an LLM.

The core problem this solves: a naive LLM reviewer re-flags the same "issue" on every PR
even after a human has explicitly rejected it, and it has no way to learn a codebase's
unwritten conventions beyond what fits in a single prompt. This agent embeds convention
docs and past review comments into a vector store, retrieves the relevant subset for each
new diff, and down-weights (and eventually excludes) patterns that have been rejected
repeatedly — so the agent's behavior visibly improves as it accumulates feedback.

## Architecture

```
GitHub PR event
      |
      v
POST /webhook  (FastAPI) --- verifies HMAC signature ---> parse_pr_event()
      |
      v
GitHubClient.get_pr_diff()  (PyGithub + httpx)
      |
      v
LangGraph pipeline:  retrieve -> analyze -> generate -> format
      |                  |          |          |
      |                  |          |          +--> cap blocking comments at 3, build ReviewOutput
      |                  |          +--> Claude (Anthropic API) reviews diff + retrieved memory
      |                  +--> ConventionMemory.query()      (Chroma: docs indexed by section)
      |                       ReviewHistoryMemory.query()   (Chroma: past comments, outcome-weighted)
      v
GitHubClient.post_inline_review_comments()  --> inline PR comments
      |
      v
SQLiteStore  (review_comments, pattern_rejections)
      ^
      |
POST /api/feedback  <-- developer accepts/rejects a comment on GitHub
      |
      +--> ReviewHistoryMemory.add()  (writes the outcome back into the vector store)
      +--> after 5 rejections of the same normalized pattern, it is excluded from
           future retrieval entirely (see REJECTION_THRESHOLD in review_history.py)

GET /dashboard  --> reads SQLiteStore directly (recent reviews, counts by severity)
```

**Key components**

| Component | Responsibility |
|---|---|
| `agent/graph.py`, `agent/steps.py` | LangGraph state machine: retrieve → analyze → generate → format |
| `memory/conventions.py` | Chunks project docs by `##`/`###` section, embeds and indexes them in Chroma |
| `memory/review_history.py` | Stores past comments with outcomes; down-weights rejected patterns (`0.2x`) vs accepted (`1.0x`) and excludes a pattern once it hits 5 rejections |
| `memory/retrieval.py` | Single entry point that merges both memory queries for a diff snippet |
| `persistence/sqlite_store.py` | Source of truth for comments, outcomes, and per-pattern rejection counts |
| `github_integration/` | Webhook signature verification, PR event parsing, diff fetch, inline comment posting |
| `api/app.py` | FastAPI app: `/webhook`, `/api/feedback`, `/api/reviews`, `/api/stats`, `/dashboard` |

## Tech stack

Python 3.12 · LangGraph · ChromaDB (vector store) · sentence-transformers
(`all-MiniLM-L6-v2` embeddings) · Anthropic API (Claude) · FastAPI + Uvicorn · PyGithub +
httpx · SQLite · pytest · Docker.

## Quickstart

**Docker (recommended — no local Python setup):**

```bash
docker compose up --build
```

Then open `http://localhost:8000/dashboard`. The dashboard, `/api/reviews`, and
`/api/stats` work with no configuration. To also let the container review real PRs and
post GitHub comments, set `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, and
`ANTHROPIC_API_KEY` in a `.env` file before running (see [Limitations](#limitations--whats-next)).

The image bakes in the embedding model at build time and runs with `HF_HUB_OFFLINE=1`,
so the container needs no internet access at all to start or serve requests (verified
with `docker run --network none`). Startup takes ~10-15s while it loads the embedding
model into memory; the dashboard and API are fully responsive once
`Application startup complete` appears in the logs.

**Local dev alternative:**

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows; use `source .venv/bin/activate` on Linux/macOS
pip install -r requirements.txt

set PYTHONPATH=src          # `export PYTHONPATH=src` on Linux/macOS
uvicorn code_review_agent.api.app:app --reload
```

## Example usage

The agent can be run directly on any diff file, no GitHub or API key required, via the
local harness with a mocked LLM:

```bash
set PYTHONPATH=src
python scripts/run_harness.py tests/fixtures/sample.diff --mock-llm --json
```

Actual output (diff is `tests/fixtures/sample.diff`, `--mock-llm` swaps in a canned
response so the retrieve/analyze/generate/format pipeline still runs end to end without
an API key):

```json
{
  "comments": [
    {
      "file_path": "a.py",
      "line_number": 1,
      "severity": "nit",
      "comment_text": "Sample",
      "suggested_replacement": null
    }
  ],
  "summary": {
    "total_comments": 1,
    "blocking_count": 0,
    "warning_count": 0,
    "nit_count": 1
  }
}
```

With a real `ANTHROPIC_API_KEY` set, drop `--mock-llm` and Claude reviews the actual diff
content against retrieved conventions and past-decision memory.

**Feedback-loop demo** — shows the memory actually changing agent behavior: a pattern
rejected 5 times stops being retrieved at all.

```bash
set PYTHONPATH=src
python scripts/demo_feedback_loop.py
```

```
OK: After 5 rejections, retrieval no longer surfaces the pattern.
```

**Feedback API**, used by GitHub comment reactions/replies in production:

```bash
curl -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"github_comment_id": "123456789", "outcome": "rejected"}'
```

## How to run tests

```bash
set PYTHONPATH=src           # `export PYTHONPATH=src` on Linux/macOS
pytest tests/ -v
```

23 tests, no network access or API keys required — all LLM calls, embeddings, and Chroma
storage are mocked/in-memory in the test suite (`tests/conftest.py`). Same command runs
in CI (`.github/workflows/ci.yml`) on every push/PR to `main`.

## Limitations / what's next

- **No conversation-level review context.** Each diff is reviewed independently; the agent
  doesn't see prior comments on the *same* PR when a new commit is pushed, so it can
  repeat itself within one PR even though it learns across PRs via `ReviewHistoryMemory`.
- **`sentence-transformers` pulls in `torch`**, which is most of the Docker image's ~2.7GB
  (down from ~9.3GB by pinning the CPU-only torch build instead of the default wheel,
  which bundles ~6GB of unused CUDA runtime libs — see `requirements.txt`). Shrinking
  further would mean swapping local embeddings for a hosted embeddings API (e.g. Voyage
  or OpenAI embeddings), trading image size for a per-request network dependency.
- **The webhook trusts `pull_request.base.repo.full_name`** from the payload for routing;
  this is standard for GitHub's own webhook payloads but means the deployment must bind
  the webhook secret per-repo (already supported via `GITHUB_WEBHOOK_SECRET`) rather than
  trusting payload contents alone.
- **`MAX_BLOCKING = 3`** and **`REJECTION_THRESHOLD = 5`** (`agent/steps.py`,
  `memory/review_history.py`) are fixed constants, not tuned or configurable per repo yet
  — reasonable defaults for a demo, but a real deployment would want these as
  per-repo settings.
- **SQLite and Chroma are both local files.** Fine for a single-instance demo; a multi-instance
  production deployment would need Postgres + a hosted vector store (or Chroma's
  server mode) instead of `docker-compose.yml`'s single-volume setup.
