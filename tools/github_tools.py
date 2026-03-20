import logging
import os
from typing import Any

import requests
from strands import ToolContext, tool

REQUEST_TIMEOUT = 30

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _github_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_require_env('GITHUB_TOKEN')}"}
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _success(data: Any) -> dict[str, Any]:
    return {
        "status": "success",
        "content": [{"json": data}],
    }


@tool(context=True)
def get_pr_files(owner: str, repo: str, pr_number: int, tool_context: ToolContext) -> dict[str, Any]:
    """Get changed files for a pull request.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        pr_number: Pull request number.
    """
    logger.info(
        "tool=%s tool_use_id=%s owner=%s repo=%s pr=%s",
        tool_context.tool_use["name"],
        tool_context.tool_use["toolUseId"],
        owner,
        repo,
        pr_number,
    )

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    response = requests.get(url, headers=_github_headers(), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    files = response.json()
    summarized_files = [
        {
            "filename": item["filename"],
            "status": item.get("status"),
            "additions": item.get("additions", 0),
            "deletions": item.get("deletions", 0),
            "changes": item.get("changes", 0),
        }
        for item in files
    ]
    return _success({"files": summarized_files})


@tool(context=True)
def get_pr_diff(owner: str, repo: str, pr_number: int, tool_context: ToolContext) -> dict[str, Any]:
    """Get the unified diff for a pull request.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        pr_number: Pull request number.
    """
    logger.info(
        "tool=%s tool_use_id=%s owner=%s repo=%s pr=%s",
        tool_context.tool_use["name"],
        tool_context.tool_use["toolUseId"],
        owner,
        repo,
        pr_number,
    )

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    response = requests.get(
        url,
        headers=_github_headers({"Accept": "application/vnd.github.v3.diff"}),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return _success({"diff": response.text[:8000]})


@tool(context=True)
def get_repo_files(owner: str, repo: str, tool_context: ToolContext) -> dict[str, Any]:
    """Get the repository file tree for repository context.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
    """
    logger.info(
        "tool=%s tool_use_id=%s owner=%s repo=%s",
        tool_context.tool_use["name"],
        tool_context.tool_use["toolUseId"],
        owner,
        repo,
    )

    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    response = requests.get(url, headers=_github_headers(), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    data = response.json()
    files = [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]
    return _success({"files": files[:1000]})
