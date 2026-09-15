"""GitHubClient.get_pr_diff: must follow GitHub's diff_url redirect.

Regression test for a real bug found testing against a live PR: diff_url
(github.com/.../pull/N.diff) always 302s to patch-diff.githubusercontent.com, but the
client wasn't following redirects, so get_pr_diff raised on every real PR.
"""

from unittest.mock import MagicMock, patch

from code_review_agent.github_integration.client import GitHubClient


def test_get_pr_diff_follows_redirects():
    mock_pr = MagicMock(diff_url="https://github.com/o/r/pull/1.diff")
    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    mock_response = MagicMock(text="diff --git a/x.py b/x.py\n")
    mock_response.raise_for_status.return_value = None
    mock_httpx_client = MagicMock()
    mock_httpx_client.__enter__.return_value = mock_httpx_client
    mock_httpx_client.get.return_value = mock_response

    with patch("code_review_agent.github_integration.client.Github", return_value=mock_gh), \
         patch("code_review_agent.github_integration.client.httpx.Client", return_value=mock_httpx_client) as mock_client_cls:
        client = GitHubClient(token="tok")
        diff = client.get_pr_diff("o", "r", 1)

    assert diff == "diff --git a/x.py b/x.py\n"
    assert mock_client_cls.call_args.kwargs.get("follow_redirects") is True


def test_get_pr_diff_returns_empty_without_token():
    client = GitHubClient(token=None)
    assert client.get_pr_diff("o", "r", 1) == ""
