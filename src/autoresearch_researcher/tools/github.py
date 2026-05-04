"""GitHub metadata fetcher tool."""

import os
import re
from typing import Optional

import httpx


def fetch_github_metadata(github_url: str) -> Optional[dict]:
    """
    Fetch metadata from GitHub API for a given repository URL.
    Returns dict with last_commit, stars, open_issues or None on failure.
    """
    match = re.search(r"github\.com/([^/]+/[^/\s#?]+)", github_url)
    if not match:
        return None

    repo = match.group(1).rstrip("/").removesuffix(".git")
    api_url = f"https://api.github.com/repos/{repo}"

    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(api_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            # Get last commit date from default branch
            branch = data.get("default_branch", "main")
            commits_url = f"https://api.github.com/repos/{repo}/commits/{branch}"
            commit_resp = client.get(commits_url, headers=headers)
            last_commit = None
            if commit_resp.status_code == 200:
                commit_data = commit_resp.json()
                last_commit = (
                    commit_data.get("commit", {})
                    .get("committer", {})
                    .get("date", None)
                )

            return {
                "stars": data.get("stargazers_count"),
                "open_issues": data.get("open_issues_count"),
                "last_commit": last_commit,
                "license": data.get("license", {}).get("spdx_id") if data.get("license") else None,
            }
    except Exception:
        return None
