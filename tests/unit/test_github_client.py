"""GitHubClient.get_pr_diff: fetches the diff directly from api.github.com.

Regression context: an earlier version used pr.diff_url (github.com/.../pull/N.diff),
which always 302s to patch-diff.githubusercontent.com. httpx correctly strips the
Authorization header on that cross-host redirect, so it silently only worked for public
repos and raised on every real PR when followed naively. Fetching the diff media type
directly from api.github.com stays on one host, so auth survives and private repos work.
"""

from unittest.mock import MagicMock, patch

from code_review_agent.github_integration.client import GitHubClient


def test_get_pr_diff_uses_api_diff_media_type_with_auth():
    mock_response = MagicMock(text="diff --git a/x.py b/x.py\n")
    mock_response.raise_for_status.return_value = None
    mock_httpx_client = MagicMock()
    mock_httpx_client.__enter__.return_value = mock_httpx_client
    mock_httpx_client.get.return_value = mock_response

    with patch("code_review_agent.github_integration.client.httpx.Client", return_value=mock_httpx_client):
        client = GitHubClient(token="tok")
        diff = client.get_pr_diff("o", "r", 1)

    assert diff == "diff --git a/x.py b/x.py\n"
    call_args, call_kwargs = mock_httpx_client.get.call_args
    assert call_args[0] == "https://api.github.com/repos/o/r/pulls/1"
    assert call_kwargs["headers"]["Authorization"] == "Bearer tok"
    assert call_kwargs["headers"]["Accept"] == "application/vnd.github.v3.diff"


def test_get_pr_diff_returns_empty_without_token():
    client = GitHubClient(token=None)
    assert client.get_pr_diff("o", "r", 1) == ""
