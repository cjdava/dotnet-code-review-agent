# dotnet-code-review-agent

An AI-powered code review agent for .NET pull requests. It uses Strands Agents with the OpenAI model provider, Python `@tool`-decorated tools, and validated structured output for the final review report.

## Features

- Uses a Strands `Agent(...)` with the OpenAI model provider
- Defines GitHub and checklist access as Python tools with the `@tool` decorator
- Fetches PR diff, changed files, and repo file tree from GitHub through agent tools
- Uses targeted repository lookups to verify test coverage and dependency context
- Reads `.sln` and `.csproj` files to understand solution structure, project references, and test projects
- Loads a best-practices checklist from a configurable remote URL
- Analyzes each file independently and produces structured findings
- Validates the final report with Pydantic structured output
- Normalizes findings before output by deduplicating entries and recalculating summary fields
- Returns a JSON report with severity-rated findings (LOW / MEDIUM / HIGH / CRITICAL)
- Fails the review if any HIGH or CRITICAL issues are found
- Uses deterministic model parameters (`temperature=0`, fixed seed) for more consistent runs
- Centralizes all configuration in a single `config.py` using `pydantic-settings` with `.env` file support
- Loads system and review prompts from external Markdown files in `prompts/`
- Returns structured tool errors instead of crashing on HTTP or network failures

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
- repository file contents
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

- `get_repo_file_content`
  Reads repository file contents so the agent can inspect `.sln`, `.csproj`, and source files directly.

- `get_best_practices`
  Fetches one or more best-practices checklists and merges them into a single combined ruleset. Each source is fetched independently and labeled with its URL, allowing enterprise, team, and project-level rules to all apply in one review.

### How Is The Agent Defined?

The agent is built in `build_agent()` inside `strand-agent.py`.

It is configured with:

- an OpenAI model via `OpenAIModel(...)`
- the six tools listed above
- a system prompt that tells the model how to review a PR
- a Pydantic output schema named `ReviewResult`
- `callback_handler=None` to avoid noisy default console callbacks

Conceptually, it looks like this:

```python
agent = Agent(
    model=model,
    tools=[get_pr_files, get_pr_diff, get_repo_files, find_repo_files, get_repo_file_content, get_best_practices],
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
5. Call `find_repo_files` to locate relevant tests, projects, and dependency-related files.
6. Call `get_repo_file_content` to inspect `.sln`, `.csproj`, and source files when project boundaries or references matter.
7. Produce a final `ReviewResult` object based on repo evidence and the coding standards checklist.

The tool-calling loop is handled by Strands internally. This means the application does not need to manually:

- define raw OpenAI JSON tool schemas
- parse `tool_calls` by hand
- append tool messages manually in a loop

### What Is Structured Output?

Structured output means the final answer is not just free-form text. It must match a defined schema.

The decision about whether something is actually a finding should come from the coding standards checklist, not from hardcoded policy in the prompt. The prompt tells the agent how to gather evidence; the checklist tells it what counts as a violation and what severity applies.

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

3. Create your `.env` file from the provided example and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

   Then edit `.env`:
   ```
   OPENAI_API_KEY=your-openai-api-key
   GITHUB_TOKEN=your-github-pat
   ```

   The `.env` file is automatically loaded by `config.py` at startup. You can also export these as shell environment variables — shell values take precedence over the `.env` file.

   Missing required variables (`OPENAI_API_KEY`, `GITHUB_TOKEN`) cause the app to fail immediately on startup with a clear validation error.

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

Optional variables (set in `.env` or shell, defaults shown):

```
OPENAI_MODEL=gpt-4.1-mini
LOG_LEVEL=INFO
REQUEST_TIMEOUT=30

# Single source
BEST_PRACTICES_URLS=https://raw.githubusercontent.com/cjdava/best-practices/main/code-peer-review.md

# Multiple layered sources (enterprise, team, project)
BEST_PRACTICES_URLS=https://enterprise.example.com/standards.md,https://team.example.com/rules.md,https://raw.githubusercontent.com/cjdava/best-practices/main/code-peer-review.md
```

All URLs in `BEST_PRACTICES_URLS` are fetched and merged into one checklist. If some sources fail but at least one succeeds, the tool proceeds with a warning instead of blocking the review.

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
├── .env.example                    # Template for required environment variables
├── config.py                       # Centralized configuration via pydantic-settings
├── requirements.txt                # Python dependencies
├── strand-agent.py                 # Main Strands agent entry point
├── prompts/
│   ├── system_prompt.md            # Agent system prompt (editable without code changes)
│   └── review_prompt.md            # Per-review prompt template
└── tools/
    ├── __init__.py
    ├── github_tools.py             # Strands GitHub tools
    └── best_practices_tools.py     # Strands best-practices tool
```

## Architecture

- `config.py` centralizes all configuration using `pydantic-settings`. It auto-loads a `.env` file and validates required fields on startup. `OPENAI_API_KEY` and `GITHUB_TOKEN` are `SecretStr` fields so they are never accidentally logged.
- `prompts/system_prompt.md` and `prompts/review_prompt.md` hold the agent prompts as external Markdown files. They are loaded at runtime so you can tune review behavior without touching Python code.
- `strand-agent.py` builds a Strands `Agent` with an `OpenAIModel` and wires it to the tool set and prompts.
- `get_best_practices` supports multiple checklist sources via `BEST_PRACTICES_URLS`. Each URL is fetched independently and combined under its source label. This allows enterprise, team, and project-level rules to coexist. Partial failures (one URL unreachable) degrade gracefully with a warning rather than failing the entire review.
- The tools in `tools/` use the `@tool` decorator. All tools return a structured `{status, content}` response — on HTTP errors, timeouts, or decode failures they return an error payload instead of raising, so the agent can reason about partial failures gracefully.
- `find_repo_files` enables targeted repo evidence checks instead of relying only on broad tree inspection.
- `get_repo_file_content` lets the agent inspect `.sln` and `.csproj` files before making dependency or test coverage claims.
- The system prompt is procedural: it tells the agent how to gather evidence, while the checklist remains the source of truth for findings and severity.
- The final report is validated against a Pydantic schema before being printed.
- A normalization pass deduplicates findings and recalculates summary and status.

## Notes

- `OPENAI_API_KEY` and `GITHUB_TOKEN` are required and validated at startup via `pydantic-settings`.
- Secret values are stored as `SecretStr` and accessed with `.get_secret_value()` — they will not appear in logs or stack traces.
- The model is configured for consistency using `temperature=0` and a fixed seed.
- The final review result is printed as validated JSON via `model_dump_json(indent=2)`.
- To customize the review prompt or system instructions, edit the files in `prompts/` directly — no code changes needed.
- To add or change best-practices sources, update `BEST_PRACTICES_URLS` in `.env` with a comma-separated list of URLs.
