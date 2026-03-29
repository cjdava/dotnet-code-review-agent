import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from strands import Agent
from strands.models.openai import OpenAIModel

from config import settings
from tools.best_practices_tools import get_best_practices
from tools.github_tools import (
    find_repo_files,
    get_pr_diff,
    get_pr_files,
    get_repo_file_content,
    get_repo_files,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


class Finding(BaseModel):
    rule: str
    category: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    description: str
    code_snippet: str

    @model_validator(mode="after")
    def validate_line_range(self) -> "Finding":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class ReviewSummary(BaseModel):
    total_findings: int = Field(ge=0)
    high_or_critical: int = Field(ge=0)


class ReviewResult(BaseModel):
    run_id: str
    pr_number: int
    status: Literal["PASS", "FAIL"]
    summary: ReviewSummary
    findings: list[Finding] = Field(default_factory=list)


def build_system_prompt() -> str:
    try:
        return (PROMPTS_DIR / "system_prompt.md").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise RuntimeError(f"System prompt file not found: {PROMPTS_DIR / 'system_prompt.md'}")
    except OSError as exc:
        raise RuntimeError(f"Failed to read system prompt: {exc}") from exc


def build_review_prompt(owner: str, repo: str, pr_number: int) -> str:
    try:
        template = (PROMPTS_DIR / "review_prompt.md").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise RuntimeError(f"Review prompt file not found: {PROMPTS_DIR / 'review_prompt.md'}")
    except OSError as exc:
        raise RuntimeError(f"Failed to read review prompt: {exc}") from exc
    return template.format(owner=owner, repo=repo, pr_number=pr_number)


def build_agent() -> Agent:
    model = OpenAIModel(
        model_id=settings.openai_model,
        client_args={"api_key": settings.openai_api_key.get_secret_value()},
        params={"temperature": 0, "seed": 42},
    )
    return Agent(
        model=model,
        tools=[
            get_pr_files,
            get_pr_diff,
            get_repo_files,
            find_repo_files,
            get_repo_file_content,
            get_best_practices,
        ],
        system_prompt=build_system_prompt(),
        callback_handler=None,
        load_tools_from_directory=False,
        structured_output_model=ReviewResult,
        name="dotnet-code-review-agent",
        description="Reviews .NET pull requests against a best-practices checklist.",
    )


def normalize_review_result(result: ReviewResult, run_id: str, pr_number: int) -> ReviewResult:
    unique_findings = {
        (finding.file, finding.start_line, finding.rule): finding
        for finding in result.findings
    }
    findings = sorted(
        unique_findings.values(),
        key=lambda finding: (finding.file, finding.start_line, finding.rule),
    )
    high_or_critical = sum(
        1 for finding in findings if finding.severity in {"HIGH", "CRITICAL"}
    )
    status: Literal["PASS", "FAIL"] = "FAIL" if high_or_critical > 0 else "PASS"

    return ReviewResult(
        run_id=run_id,
        pr_number=pr_number,
        status=status,
        summary=ReviewSummary(
            total_findings=len(findings),
            high_or_critical=high_or_critical,
        ),
        findings=findings,
    )


def run_agent(owner: str, repo: str, pr_number: int, run_id: str = "LOCAL_RUN") -> ReviewResult:
    logger.info("Starting review owner=%s repo=%s pr=%s model=%s", owner, repo, pr_number, settings.openai_model)
    agent = build_agent()
    logger.debug("Agent built — invoking with review prompt")

    result = agent(
        build_review_prompt(owner, repo, pr_number),
        structured_output_model=ReviewResult,
    )

    if result.structured_output is None:
        raise ValueError("Agent returned no structured output")

    logger.debug("Raw structured output received — normalizing findings")
    normalized = normalize_review_result(result.structured_output, run_id, pr_number)
    tool_metrics = getattr(result.metrics, "tool_metrics", None)
    tool_call_count = len(tool_metrics) if tool_metrics else 0
    logger.info(
        "Completed review status=%s findings=%s high_or_critical=%s tool_calls=%s",
        normalized.status,
        normalized.summary.total_findings,
        normalized.summary.high_or_critical,
        tool_call_count,
    )
    return normalized

# ================================
# ENFORCEMENT
# ================================

def enforce(result):
    if result.status == "FAIL":
        print("❌ Review FAILED")
        return False
    else:
        print("✅ Review PASSED")
        return True


# ================================
# MAIN
# ================================

if __name__ == "__main__":

    owner = "cjdava"
    repo = "PeerReviewSample"
    pr_number = 29

    result = run_agent(owner, repo, pr_number)

    print("\n========== RESULT ==========\n")
    print(result.model_dump_json(indent=2))

    enforce(result)