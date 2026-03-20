import os
import json
import requests
from openai import OpenAI
from tools.github_tools import (
    get_pr_files,
    get_pr_diff,
    get_repo_files
)

from tools.best_practices_tools import get_best_practices

# ================================
# CONFIG 
# ================================

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

client = OpenAI(api_key=OPENAI_API_KEY)

# ================================
# TOOL REGISTRY (FOR LLM)
# ================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_pr_files",
            "description": "Get files changed in the pull request",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "pr_number": {"type": "integer"}
                },
                "required": ["owner", "repo", "pr_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pr_diff",
            "description": "Get code diff of the pull request",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "pr_number": {"type": "integer"}
                },
                "required": ["owner", "repo", "pr_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_repo_files",
            "description": "Get all files in repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"}
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_best_practices",
            "description": "Get engineering checklist",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# ================================
# TOOL EXECUTOR
# ================================

def run_tool(name, args):
    if name == "get_pr_files":
        return get_pr_files(args["owner"], args["repo"], args["pr_number"], GITHUB_TOKEN)

    if name == "get_pr_diff":
        return get_pr_diff(args["owner"], args["repo"], args["pr_number"], GITHUB_TOKEN)

    if name == "get_repo_files":
        return get_repo_files(args["owner"], args["repo"], GITHUB_TOKEN)

    if name == "get_best_practices":
        return get_best_practices()

    raise Exception(f"Unknown tool: {name}")

# ================================
# JSON PARSER
# ================================

def clean_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
    return text.strip()

def parse_json(text):
    return json.loads(clean_json(text))

# ================================
# AGENT LOOP
# ================================

def run_agent(owner, repo, pr_number):

    used_tools = set()

    messages = [
        {
            "role": "system",
            "content": f"""
You are a senior .NET Code Review Agent.

You have tools to:
- get_pr_files
- get_pr_diff
- get_repo_files
- get_best_practices

----------------------------------------
CORE STRATEGY (MANDATORY)
----------------------------------------

You MUST analyze the pull request PER FILE.

Process:
1. Identify all changed files
2. For EACH file:
   - analyze independently
   - detect issues
   - produce findings for that file
3. Combine all findings at the end

----------------------------------------
CRITICAL RULES
----------------------------------------

- DO NOT analyze the entire PR as one block
- DO NOT group findings across files
- DO NOT group multiple issues in one finding

✔ ONE FILE → MANY FINDINGS  
✔ ONE ISSUE → ONE FINDING  

----------------------------------------
OUTPUT CONTRACT (STRICT)
----------------------------------------

Return ONLY JSON:

{{
  "run_id": "LOCAL_RUN",
  "pr_number": {pr_number},
  "status": "PASS | FAIL",
  "summary": {{
    "total_findings": number,
    "high_or_critical": number
  }},
  "findings": [
    {{
      "rule": "string",
      "category": "string",
      "severity": "LOW | MEDIUM | HIGH | CRITICAL",
      "file": "string",
      "start_line": number,
      "end_line": number,
      "description": "string",
      "code_snippet": "string"
    }}
  ]
}}

----------------------------------------
FILE ANALYSIS RULES
----------------------------------------

- Each file must be analyzed independently
- Findings must reference ONLY the file being analyzed
- DO NOT mix findings between files

----------------------------------------
LINE RULES
----------------------------------------

- start_line REQUIRED
- end_line REQUIRED
- Use diff line numbers
- If single line → same value

----------------------------------------
SEVERITY RULES
----------------------------------------

- LOW
- MEDIUM
- HIGH
- CRITICAL

----------------------------------------
FAIL RULE
----------------------------------------

- If ANY HIGH or CRITICAL → FAIL

----------------------------------------
IMPORTANT
----------------------------------------

- Prefer MANY small findings
- NEVER group issues
- NEVER summarize multiple issues

----------------------------------------
Return ONLY JSON
"""
        },
        {
            "role": "user",
            "content": f"Review PR {pr_number} in {owner}/{repo}"
        }
    ]

    while True:

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            tools=tools,
            temperature=0
        )

        msg = response.choices[0].message

        print("\n🧠 Agent Step")
        print(msg)

        # =========================
        # TOOL CALL
        # =========================
        if msg.tool_calls:
            messages.append(msg)

            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")

                # 🚫 Prevent repeated tool calls
                if name in used_tools:
                    print(f"⚠️ Skipping repeated tool: {name}")
                    continue

                used_tools.add(name)

                print(f"🔧 Tool Call: {name}")

                try:
                    result = run_tool(name, args)
                except Exception as e:
                    result = {"error": str(e)}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)[:8000]
                })

        else:
            print("✅ Final Answer Generated")

            result = parse_json(msg.content)

            # Deduplicate
            seen = set()
            unique = []

            for f in result.get("findings", []):
                key = (f["file"], f["start_line"], f["rule"])
                if key not in seen:
                    seen.add(key)
                    unique.append(f)

            # Sort
            unique = sorted(
                unique,
                key=lambda x: (x["file"], x["start_line"], x["rule"])
            )

            # Recalculate
            high_or_critical = sum(
                1 for f in unique if f["severity"] in ["HIGH", "CRITICAL"]
            )

            result["findings"] = unique
            result["summary"] = {
                "total_findings": len(unique),
                "high_or_critical": high_or_critical
            }
            result["status"] = "FAIL" if high_or_critical > 0 else "PASS"

            return result

# ================================
# ENFORCEMENT
# ================================

def enforce(result):
    if result["status"] == "FAIL":
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
    print(json.dumps(result, indent=2))

    enforce(result)