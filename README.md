# dotnet-code-review-agent

An AI-powered code review agent for .NET pull requests. Uses OpenAI's function-calling API to autonomously fetch PR data from GitHub and review it against a best-practices checklist.

## Features

- Fetches PR diff, changed files, and repo file tree from GitHub
- Loads a best-practices checklist from a remote source
- Analyzes each file independently and produces structured findings
- Returns a JSON report with severity-rated findings (LOW / MEDIUM / HIGH / CRITICAL)
- Fails the review if any HIGH or CRITICAL issues are found

## Requirements

- Python 3.10+
- An OpenAI API key
- A GitHub Personal Access Token with `repo` read permissions

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/cjdava/dotnet-code-review-agent.git
   cd dotnet-code-review-agent
   ```

2. Install dependencies:
   ```bash
   pip install openai requests
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
├── strand-agent.py        # Main agent entry point
└── tools/
    ├── __init__.py
    ├── github_tools.py    # GitHub API helpers
    └── best_practices_tools.py  # Best practices fetcher
```
