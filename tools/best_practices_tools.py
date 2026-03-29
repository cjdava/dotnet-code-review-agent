import logging
from typing import Any

import requests
from strands import ToolContext, tool

from config import settings

logger = logging.getLogger(__name__)


@tool(context=True)
def get_best_practices(tool_context: ToolContext) -> dict[str, Any]:
    """Get the review checklist used during pull request analysis."""
    logger.info(
        "tool=%s tool_use_id=%s urls=%s",
        tool_context.tool_use["name"],
        tool_context.tool_use["toolUseId"],
        len(settings.best_practices_urls),
    )

    sections: list[str] = []
    errors: list[str] = []

    for url in settings.best_practices_urls:
        try:
            response = requests.get(url, timeout=settings.request_timeout)
            response.raise_for_status()
            sections.append(f"<!-- source: {url} -->\n{response.text[:3000]}")
        except requests.HTTPError as exc:
            logger.warning("tool=get_best_practices HTTP error status=%s url=%s", exc.response.status_code, url)
            errors.append(f"HTTP {exc.response.status_code} fetching {url}")
        except requests.Timeout:
            logger.warning("tool=get_best_practices request timed out url=%s", url)
            errors.append(f"Timeout fetching {url}")
        except requests.RequestException as exc:
            logger.warning("tool=get_best_practices request failed url=%s error=%s", url, exc)
            errors.append(f"Request failed for {url}: {exc}")

    if not sections:
        return {
            "status": "error",
            "content": [{"json": {"error": "All checklist sources failed", "details": errors}}],
        }

    combined = "\n\n---\n\n".join(sections)
    result: dict[str, Any] = {"rules": combined, "sources": len(sections)}
    if errors:
        result["warnings"] = errors

    return {
        "status": "success",
        "content": [{"json": result}],
    }