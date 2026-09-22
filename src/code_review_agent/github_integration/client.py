"""GitHub API wrapper: fetch PR diff, post inline review comments."""

from typing import List, Optional

import httpx
from github import Github

from code_review_agent.schemas import Comment


class GitHubClient:
    """Wrapper for fetching PR diff and posting inline review comments."""

    def __init__(self, token: Optional[str] = None):
        self._token = token
        self._gh = Github(token) if token else None

    def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """Fetch the unified diff for a PR via the REST API's diff media type.

        Deliberately does NOT use pr.diff_url (github.com/.../pull/N.diff): that
        always 302s to patch-diff.githubusercontent.com, and httpx correctly strips
        the Authorization header on that cross-host redirect, so it would silently
        only work for public repos. Requesting the diff directly from api.github.com
        stays on one host, so auth is preserved and this works for private repos too.
        """
        if not self._token:
            return ""
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github.v3.diff",
        }
        with httpx.Client() as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    def post_inline_review_comments(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        comments: List[Comment],
    ) -> List[str]:
        """Post inline PR review comments. Returns list of GitHub comment IDs (for feedback mapping)."""
        if not self._gh or not comments:
            return []
        r = self._gh.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        commit = r.get_commit(commit_id)
        ids = []
        for c in comments:
            body = c.comment_text
            if c.suggested_replacement:
                body += f"\n\nSuggested fix:\n```suggestion\n{c.suggested_replacement}\n```"
            rc = pr.create_review_comment(body=body, commit=commit, path=c.file_path, line=c.line_number)
            ids.append(str(rc.id))
        return ids
