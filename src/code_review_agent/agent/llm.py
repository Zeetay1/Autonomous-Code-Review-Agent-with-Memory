"""Thin wrapper around Anthropic Claude for analyze/generate steps. Injectable for tests."""

import os
from typing import Optional

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


def complete(prompt: str, system: Optional[str] = None) -> str:
    """Call Claude and return the text content of the first message. Requires ANTHROPIC_API_KEY."""
    from anthropic import Anthropic

    client = Anthropic()
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    kwargs = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    if resp.content and len(resp.content) > 0:
        block = resp.content[0]
        if hasattr(block, "text"):
            return block.text
    return ""
