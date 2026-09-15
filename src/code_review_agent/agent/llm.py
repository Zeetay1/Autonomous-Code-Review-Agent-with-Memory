"""Thin wrapper around an LLM provider for analyze/generate steps. Injectable for tests.

Anthropic Claude is the default; Groq is a supported alternative (e.g. for testing
without Anthropic credits) via LLM_PROVIDER=groq.
"""

import os
from typing import Optional

DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


def complete(prompt: str, system: Optional[str] = None) -> str:
    """Call the configured LLM provider and return the text of its response.

    Provider is chosen via LLM_PROVIDER ("anthropic", the default, or "groq").
    Requires ANTHROPIC_API_KEY or GROQ_API_KEY respectively.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "groq":
        return _complete_groq(prompt, system)
    return _complete_anthropic(prompt, system)


def _complete_anthropic(prompt: str, system: Optional[str]) -> str:
    from anthropic import Anthropic

    client = Anthropic()
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    kwargs = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    if resp.content and len(resp.content) > 0:
        block = resp.content[0]
        if hasattr(block, "text"):
            return block.text
    return ""


def _complete_groq(prompt: str, system: Optional[str]) -> str:
    from groq import Groq

    client = Groq()
    model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(model=model, messages=messages, max_tokens=4096)
    if resp.choices and len(resp.choices) > 0:
        return resp.choices[0].message.content or ""
    return ""
