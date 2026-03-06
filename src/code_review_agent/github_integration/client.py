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
        """Fetch the unified diff for a PR. Uses diff_url with auth."""
        if not self._gh:
            return ""
        r = self._gh.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        diff_url = pr.diff_url
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        with httpx.Client() as client:
            resp = client.get(diff_url, headers=headers)
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
