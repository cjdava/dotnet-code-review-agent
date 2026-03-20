import json
import logging
import os
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from strands import Agent
from strands.models.openai import OpenAIModel

from tools.best_practices_tools import get_best_practices
from tools.github_tools import get_pr_diff, get_pr_files, get_repo_files

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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
    return """
You are a senior .NET code review agent.

Operating rules:
- Use the available tools to gather pull request context before deciding.
- Analyze the pull request per file, not as one undifferentiated block.
- Only report concrete issues supported by the fetched diff, file list, repo context, or checklist.
- Do not invent missing code or hidden context.
- One issue must produce one finding.
- Findings must point to the modified file they belong to.
- Use diff line numbers for start_line and end_line.
- Set status to FAIL if any finding is HIGH or CRITICAL. Otherwise set PASS.
- If no issues exist, return an empty findings list.

Recommended workflow:
1. Get changed files.
2. Get the PR diff.
3. Get the best-practices checklist.
4. Optionally inspect repo files for architectural context.
5. Produce the final structured report.
""".strip()


def build_review_prompt(owner: str, repo: str, pr_number: int) -> str:
    return f"""
Review pull request {pr_number} in repository {owner}/{repo}.

Requirements:
- Analyze changed files independently.
- Prefer many precise findings over broad summaries.
- Do not report style nits unless they clearly violate the checklist or create risk.
- Keep code_snippet short and directly relevant.
""".strip()


def build_agent() -> Agent:
    model = OpenAIModel(
        model_id=OPENAI_MODEL,
        client_args={"api_key": require_env("OPENAI_API_KEY")},
        params={"temperature": 0},
    )
    return Agent(
        model=model,
        tools=[get_pr_files, get_pr_diff, get_repo_files, get_best_practices],
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
    logger.info("Starting review owner=%s repo=%s pr=%s model=%s", owner, repo, pr_number, OPENAI_MODEL)
    agent = build_agent()
    result = agent(
        build_review_prompt(owner, repo, pr_number),
        structured_output_model=ReviewResult,
    )

    if result.structured_output is None:
        raise ValueError("Agent returned no structured output")

    normalized = normalize_review_result(result.structured_output, run_id, pr_number)
    tool_metrics = getattr(result.metrics, "tool_metrics", None)
    tool_call_count = len(tool_metrics) if tool_metrics else 0
    logger.info(
        "Completed review status=%s findings=%s tool_calls=%s",
        normalized.status,
        normalized.summary.total_findings,
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