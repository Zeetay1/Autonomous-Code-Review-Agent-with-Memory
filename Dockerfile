# syntax=docker/dockerfile:1

# ---- builder: resolve and install Python deps into an isolated prefix ----
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- final: slim runtime image ----
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ ./src/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    CODE_REVIEW_AGENT_DB_PATH=/data/review_agent.db \
    CODE_REVIEW_AGENT_CHROMA_PATH=/data/chroma \
    HF_HOME=/data/hf_cache

# Pre-download the sentence-transformers embedding model at build time (into
# HF_HOME) so the container never needs internet access to start.
RUN mkdir -p /data/chroma /data/hf_cache \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# huggingface_hub still does a network freshness check by default even when the
# model is cached; force it to use the cache we just baked in with zero network calls.
ENV HF_HUB_OFFLINE=1

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /data /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "code_review_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
