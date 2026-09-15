"""LLM provider selection: LLM_PROVIDER routes to Anthropic (default) or Groq."""

from unittest.mock import MagicMock, patch

from code_review_agent.agent import llm


def test_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="anthropic response")]
    )
    with patch("anthropic.Anthropic", return_value=mock_client):
        result = llm.complete("prompt", system="sys")
    assert result == "anthropic response"
    mock_client.messages.create.assert_called_once()
    assert mock_client.messages.create.call_args.kwargs["model"] == llm.DEFAULT_ANTHROPIC_MODEL


def test_routes_to_groq_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="groq response"))]
    )
    with patch("groq.Groq", return_value=mock_client):
        result = llm.complete("prompt", system="sys")
    assert result == "groq response"
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == llm.DEFAULT_GROQ_MODEL
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "prompt"},
    ]


def test_groq_model_is_configurable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "custom-model")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))]
    )
    with patch("groq.Groq", return_value=mock_client):
        llm.complete("prompt")
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "custom-model"


def test_provider_selection_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "GROQ")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))]
    )
    with patch("groq.Groq", return_value=mock_client):
        result = llm.complete("prompt")
    assert result == "ok"
