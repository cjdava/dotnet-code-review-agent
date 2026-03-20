import logging
from typing import Any

import requests
from strands import ToolContext, tool

REQUEST_TIMEOUT = 30

logger = logging.getLogger(__name__)


@tool(context=True)
def get_best_practices(tool_context: ToolContext) -> dict[str, Any]:
    """Get the review checklist used during pull request analysis."""
    logger.info(
        "tool=%s tool_use_id=%s",
        tool_context.tool_use["name"],
        tool_context.tool_use["toolUseId"],
    )

    url = "https://raw.githubusercontent.com/cjdava/best-practices/main/code-peer-review.md"
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return {
        "status": "success",
        "content": [{"json": {"rules": response.text[:3000]}}],
    }