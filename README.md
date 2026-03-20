# dotnet-code-review-agent

An AI-powered code review agent for .NET pull requests. It uses Strands Agents with the OpenAI model provider, Python `@tool`-decorated tools, and validated structured output for the final review report.

## Features

- Uses a Strands `Agent(...)` with the OpenAI model provider
- Defines GitHub and checklist access as Python tools with the `@tool` decorator
- Fetches PR diff, changed files, and repo file tree from GitHub through agent tools
- Uses targeted repository lookups to verify test coverage and dependency context
- Loads a best-practices checklist from a remote source
- Analyzes each file independently and produces structured findings
- Validates the final report with Pydantic structured output
- Normalizes findings before output by deduplicating entries and recalculating summary fields
- Returns a JSON report with severity-rated findings (LOW / MEDIUM / HIGH / CRITICAL)
- Fails the review if any HIGH or CRITICAL issues are found
- Uses deterministic model parameters (`temperature=0`, fixed seed) for more consistent runs

## Core Concepts

### What Is The Agent?

The agent is the main decision-making component of the application.

In this project, the agent is created in `strand-agent.py` with Strands:

- `Agent(...)` is the orchestration layer
- `OpenAIModel(...)` is the model provider used by the agent
- `system_prompt` defines the review behavior and constraints
- `structured_output_model=ReviewResult` tells the agent what final shape the result must follow

The agent is responsible for:

- understanding the review request
- deciding which tool to call
- deciding when it has enough context
- producing the final structured review report

### What Are Tools?

Tools are Python functions that the agent can call when it needs external information.

Without tools, the model only knows what is in the prompt. With tools, the agent can fetch live data such as:

- files changed in a pull request
- the pull request diff
- repository file paths
- the review checklist

In this project, tools are regular Python functions decorated with `@tool`. That decorator allows Strands to expose them to the agent as callable capabilities.

### What Tools Does This Project Use?

This project defines the following tools in the `tools/` directory:

- `get_pr_files`
  Gets the list of files changed in a pull request.

- `get_pr_diff`
  Gets the pull request unified diff.

- `get_repo_files`
  Gets the repository file tree so the agent can inspect broader repo context.

- `find_repo_files`
  Finds repository files by name/path matching so the agent can verify test files and dependencies.

- `get_best_practices`
  Gets the best-practices checklist used as the review baseline.

### How Is The Agent Defined?

The agent is built in `build_agent()` inside `strand-agent.py`.

It is configured with:

- an OpenAI model via `OpenAIModel(...)`
- the five tools listed above
- a system prompt that tells the model how to review a PR
- a Pydantic output schema named `ReviewResult`
- `callback_handler=None` to avoid noisy default console callbacks

Conceptually, it looks like this:

```python
agent = Agent(
    model=model,
  tools=[get_pr_files, get_pr_diff, get_repo_files, find_repo_files, get_best_practices],
    system_prompt=build_system_prompt(),
    structured_output_model=ReviewResult,
)
```

### How Does The Agent Use The Tools?

The agent receives a prompt such as:

- review PR 29 in a given repository

From there, the model follows a required evidence-gathering flow:

1. Call `get_pr_files` to see what changed.
2. Call `get_pr_diff` to inspect the code changes.
3. Call `get_best_practices` to get the review rules.
4. Call `get_repo_files` to inspect repository structure.
5. Call `find_repo_files` to verify test-file and dependency evidence for changed business/service/domain code.
6. Produce a final `ReviewResult` object.

The tool-calling loop is handled by Strands internally. This means the application does not need to manually:

- define raw OpenAI JSON tool schemas
- parse `tool_calls` by hand
- append tool messages manually in a loop

### What Is Structured Output?

Structured output means the final answer is not just free-form text. It must match a defined schema.

In this project, the schema is defined with Pydantic models:

- `Finding`
- `ReviewSummary`
- `ReviewResult`

That gives the project:

- validated field names
- validated data types
- consistent JSON output
- clearer failure behavior when the model returns invalid data

### What Happens After The Agent Responds?

After the agent returns a structured result, the application runs a normalization step.

That step:

- deduplicates findings
- sorts findings by file and line
- recalculates `total_findings`
- recalculates `high_or_critical`
- recalculates final `status`

This keeps the final output consistent even if the model returns redundant findings.

## Requirements

- Python 3.10+
- An OpenAI API key
- A GitHub Personal Access Token with `repo` read permissions
- Strands Agents SDK

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/cjdava/dotnet-code-review-agent.git
   cd dotnet-code-review-agent
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set environment variables:
   ```bash
   export OPENAI_API_KEY="your-openai-api-key"
   export GITHUB_TOKEN="your-github-pat"
   ```
   Add these to `~/.zshrc` (macOS) to persist across sessions.

## Usage

Edit the `__main__` block in `strand-agent.py` with your target repo and PR number:

```python
owner = "your-github-username"
repo = "your-repo"
pr_number = 42
```

Then run:

```bash
python strand-agent.py
```

If you are using the workspace virtual environment directly:

```bash
/Users/christianjoshuadava/Desktop/development/ai/.venv/bin/python strand-agent.py
```

Optional environment variables:

```bash
export OPENAI_MODEL="gpt-4.1-mini"
export LOG_LEVEL="INFO"
```

## Output

```json
{
  "run_id": "LOCAL_RUN",
  "pr_number": 42,
  "status": "PASS",
  "summary": {
    "total_findings": 2,
    "high_or_critical": 0
  },
  "findings": [
    {
      "rule": "...",
      "category": "...",
      "severity": "MEDIUM",
      "file": "src/MyService.cs",
      "start_line": 12,
      "end_line": 12,
      "description": "...",
      "code_snippet": "..."
    }
  ]
}
```

## Project Structure

```
dotnet-code-review-agent/
├── requirements.txt       # Python dependencies
├── strand-agent.py        # Main Strands agent entry point
└── tools/
    ├── __init__.py
    ├── github_tools.py    # Strands GitHub tools
    └── best_practices_tools.py  # Strands best-practices tool
```

## Architecture

- `strand-agent.py` builds a Strands `Agent` with an `OpenAIModel`
- The tools in `tools/` use the `@tool` decorator and return normalized tool results
- `find_repo_files` enables targeted repo evidence checks instead of relying only on broad tree inspection
- The final report is validated against a Pydantic schema before being printed
- A small normalization pass deduplicates findings and recalculates summary and status

## Notes

- `OPENAI_API_KEY` is required when the agent is created
- `GITHUB_TOKEN` is required when GitHub-backed tools are executed
- Missing environment variables now fail with clearer runtime errors instead of failing during module import
- The model is configured for consistency using `temperature=0` and a fixed seed
- The final review result is printed as validated JSON via `model_dump_json(indent=2)`
