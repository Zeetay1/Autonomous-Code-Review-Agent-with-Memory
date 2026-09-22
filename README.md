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
repeatedly, so the agent's behavior visibly improves as it accumulates feedback.

## Architecture

```
GitHub PR event
      |
      v
POST /webhook  (FastAPI) --- verifies HMAC signature ---> parse_pr_event()
      |
      v
GitHubClient.get_pr_diff()  (REST API diff media type, not diff_url -- see note below)
      |
      v
LangGraph pipeline:  retrieve -> analyze -> generate -> format
      |                  |          |          |
      |                  |          |          +--> cap blocking comments (MAX_BLOCKING_COMMENTS), build ReviewOutput
      |                  |          +--> Claude or Groq reviews diff + retrieved memory + this PR's own past comments
      |                  +--> ConventionMemory.query()        (Chroma: docs indexed by section)
      |                       ReviewHistoryMemory.query()     (Chroma: past comments, outcome-weighted)
      |                       SQLiteStore.get_review_by_pr()  (this PR's own prior comments, so a second
      |                                                        push to the same PR doesn't repeat itself)
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
      +--> after REJECTION_THRESHOLD rejections of the same normalized pattern, it is
           excluded from future retrieval entirely (memory/review_history.py)

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

**Two independent kinds of memory:** `ReviewHistoryMemory` tracks accepted/rejected
*patterns* permanently, across every PR in the repo (the `REJECTION_THRESHOLD`
exclusion). Separately, each PR also remembers its *own* prior comments
(`SQLiteStore.get_review_by_pr`, threaded into `retrieve_step` as `pr_reference`), purely
so pushing a second commit to the same PR doesn't re-flag what it already said on the
first pass. This one resets per PR; it's not a permanent exclusion like the other.

## Tech stack

Python 3.12 · LangGraph · ChromaDB (vector store) · sentence-transformers
(`all-MiniLM-L6-v2` embeddings) · Anthropic API (Claude), with Groq as a pluggable
alternative (`LLM_PROVIDER=groq`) · FastAPI + Uvicorn · PyGithub + httpx · SQLite ·
pytest · Docker.

## Quickstart

**Docker (recommended, no local Python setup):**

```bash
docker compose up --build
```

Then open `http://localhost:8000/dashboard`. The dashboard, `/api/reviews`, and
`/api/stats` work with no configuration, but start empty until something is reviewed.
Run `python scripts/seed_demo_data.py` (needs `PYTHONPATH=src`) to populate it with a
realistic sample PR review, including a pattern already past the rejection threshold.
No API key needed, since it writes directly to the store rather than calling an LLM.

The image bakes in the embedding model at build time and runs with `HF_HUB_OFFLINE=1`,
so the container needs no internet access at all to start or serve requests (verified
with `docker run --network none`). Startup takes ~10-15s while it loads the embedding
model into memory; the dashboard and API are fully responsive once
`Application startup complete` appears in the logs.

**Connecting it to a real GitHub repo** (optional; the dashboard/demo above needs none
of this):

1. Copy `.env.example` to `.env` and fill in `GITHUB_TOKEN` (repo scope, or fine-grained
   with Contents: read + Pull requests: read/write) and either `ANTHROPIC_API_KEY` or
   `LLM_PROVIDER=groq` + `GROQ_API_KEY`.
2. Your instance needs a URL GitHub can actually reach; `localhost` doesn't count. For
   local testing, expose it with a tunnel (e.g. `ngrok http 8000` or
   `npx localtunnel --port 8000`); for real use, deploy it somewhere with a stable public
   URL.
3. On the target repo: **Settings → Webhooks → Add webhook** → Payload URL =
   `https://<your-url>/webhook`, content type `application/json`, event: "Pull requests".
   Set the same value as `GITHUB_WEBHOOK_SECRET` in `.env` so payloads are verified.
4. Open or push to a PR on that repo. It gets reviewed for real, with inline comments
   posted directly on GitHub. (This exact flow is what found and fixed the redirect bug
   in `GitHubClient.get_pr_diff`, verified against a live PR, not just mocked.)

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

**Feedback-loop demo**: shows the memory actually changing agent behavior. A pattern
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

35 tests, no network access or API keys required. All LLM calls, embeddings, and Chroma
storage are mocked/in-memory in the test suite (`tests/conftest.py`). Same command runs
in CI (`.github/workflows/ci.yml`) on every push/PR to `main`.

## Limitations

- **Private repos are untested.** `get_pr_diff` fetches from `api.github.com` directly
  (not `pr.diff_url`, which redirects and drops the auth header), so auth should
  survive, but this is only verified against a public PR, not an actual private repo.
- **`torch` still dominates the Docker image (~2.7GB)**, even after pinning the CPU-only
  build (down from ~9.3GB, see `requirements.txt`). Shrinking further means swapping
  local embeddings for a hosted API, trading image size for a network dependency.
- **The webhook trusts `pull_request.base.repo.full_name`** for routing, standard for
  GitHub payloads, but means each deployment must set its own `GITHUB_WEBHOOK_SECRET`
  rather than trusting payload contents alone.
- **SQLite and Chroma are local files**, fine for one instance; multi-instance production
  would need Postgres and a hosted vector store instead.
- **PR-level dedup only sees this agent's own past comments** (via SQLite), not a human
  reviewer's or another tool's.

`MAX_BLOCKING_COMMENTS` (default 3) and `REJECTION_THRESHOLD` (default 5) are
configurable via environment variables, not hardcoded.
