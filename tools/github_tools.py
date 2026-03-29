import base64
import binascii
import logging
from typing import Any

import requests
from strands import ToolContext, tool

from config import settings

logger = logging.getLogger(__name__)


def _github_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {settings.github_token.get_secret_value()}"}
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _success(data: Any) -> dict[str, Any]:
    return {
        "status": "success",
        "content": [{"json": data}],
    }


def _error(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "content": [{"json": {"error": message}}],
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
    try:
        response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.warning("tool=get_pr_files HTTP error status=%s url=%s", exc.response.status_code, url)
        return _error(f"GitHub API returned HTTP {exc.response.status_code} for PR {pr_number}")
    except requests.Timeout:
        logger.warning("tool=get_pr_files request timed out url=%s", url)
        return _error(f"Request timed out fetching files for PR {pr_number}")
    except requests.RequestException as exc:
        logger.warning("tool=get_pr_files request failed url=%s error=%s", url, exc)
        return _error(f"Request failed: {exc}")

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
    try:
        response = requests.get(
            url,
            headers=_github_headers({"Accept": "application/vnd.github.v3.diff"}),
            timeout=settings.request_timeout,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.warning("tool=get_pr_diff HTTP error status=%s url=%s", exc.response.status_code, url)
        return _error(f"GitHub API returned HTTP {exc.response.status_code} fetching diff for PR {pr_number}")
    except requests.Timeout:
        logger.warning("tool=get_pr_diff request timed out url=%s", url)
        return _error(f"Request timed out fetching diff for PR {pr_number}")
    except requests.RequestException as exc:
        logger.warning("tool=get_pr_diff request failed url=%s error=%s", url, exc)
        return _error(f"Request failed: {exc}")

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
    try:
        response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.warning("tool=get_repo_files HTTP error status=%s url=%s", exc.response.status_code, url)
        return _error(f"GitHub API returned HTTP {exc.response.status_code} fetching file tree for {repo}")
    except requests.Timeout:
        logger.warning("tool=get_repo_files request timed out url=%s", url)
        return _error(f"Request timed out fetching file tree for {repo}")
    except requests.RequestException as exc:
        logger.warning("tool=get_repo_files request failed url=%s error=%s", url, exc)
        return _error(f"Request failed: {exc}")

    data = response.json()
    files = [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]
    return _success({"files": files[:1000]})


@tool(context=True)
def find_repo_files(
    owner: str,
    repo: str,
    contains: str,
    suffix: str = "",
    limit: int = 200,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Find repository files by case-insensitive name/path matching.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        contains: Case-insensitive substring that must exist in file path.
        suffix: Optional case-insensitive suffix filter (for example, "Tests.cs").
        limit: Maximum number of matching file paths to return.
    """
    if tool_context is not None:
        logger.info(
            "tool=%s tool_use_id=%s owner=%s repo=%s contains=%s suffix=%s",
            tool_context.tool_use["name"],
            tool_context.tool_use["toolUseId"],
            owner,
            repo,
            contains,
            suffix,
        )

    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    try:
        response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.warning("tool=find_repo_files HTTP error status=%s url=%s", exc.response.status_code, url)
        return _error(f"GitHub API returned HTTP {exc.response.status_code} fetching file tree for {repo}")
    except requests.Timeout:
        logger.warning("tool=find_repo_files request timed out url=%s", url)
        return _error(f"Request timed out fetching file tree for {repo}")
    except requests.RequestException as exc:
        logger.warning("tool=find_repo_files request failed url=%s error=%s", url, exc)
        return _error(f"Request failed: {exc}")

    data = response.json()
    files = [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]

    contains_lower = contains.lower().strip()
    suffix_lower = suffix.lower().strip()
    normalized_limit = max(1, min(limit, 1000))

    matches = []
    for path in files:
        lower_path = path.lower()
        if contains_lower and contains_lower not in lower_path:
            continue
        if suffix_lower and not lower_path.endswith(suffix_lower):
            continue
        matches.append(path)
        if len(matches) >= normalized_limit:
            break

    return _success(
        {
            "contains": contains,
            "suffix": suffix,
            "matches": matches,
            "returned": len(matches),
        }
    )


@tool(context=True)
def get_repo_file_content(
    owner: str,
    repo: str,
    path: str,
    ref: str = "HEAD",
    max_chars: int = 12000,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Get text content for a repository file.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        path: Repository-relative file path.
        ref: Git ref to read from.
        max_chars: Maximum number of decoded characters to return.
    """
    if tool_context is not None:
        logger.info(
            "tool=%s tool_use_id=%s owner=%s repo=%s path=%s ref=%s",
            tool_context.tool_use["name"],
            tool_context.tool_use["toolUseId"],
            owner,
            repo,
            path,
            ref,
        )

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    try:
        response = requests.get(
            url,
            headers=_github_headers(),
            params={"ref": ref},
            timeout=settings.request_timeout,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code
        if status_code == 404:
            logger.warning("tool=get_repo_file_content file not found path=%s ref=%s", path, ref)
            return _error(f"File not found: {path} at ref {ref}")
        logger.warning("tool=get_repo_file_content HTTP error status=%s path=%s", status_code, path)
        return _error(f"GitHub API returned HTTP {status_code} for {path}")
    except requests.Timeout:
        logger.warning("tool=get_repo_file_content request timed out path=%s", path)
        return _error(f"Request timed out reading {path}")
    except requests.RequestException as exc:
        logger.warning("tool=get_repo_file_content request failed path=%s error=%s", path, exc)
        return _error(f"Request failed: {exc}")

    data = response.json()
    encoded_content = data.get("content", "")
    normalized_limit = max(1, min(max_chars, 50000))

    try:
        decoded_content = base64.b64decode(encoded_content).decode("utf-8", errors="replace")
    except binascii.Error as exc:
        logger.warning("tool=get_repo_file_content failed to decode content path=%s error=%s", path, exc)
        return _error(f"Failed to decode file content for {path}: not valid base64")

    return _success(
        {
            "path": path,
            "ref": ref,
            "content": decoded_content[:normalized_limit],
            "truncated": len(decoded_content) > normalized_limit,
        }
    )
