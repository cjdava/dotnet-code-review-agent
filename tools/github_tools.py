import requests

# ================================
# GITHUB TOOLS
# ================================

def get_pr_files(owner, repo, pr_number, token):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers = {"Authorization": f"Bearer {token}"}
    return requests.get(url, headers=headers).json()

def get_pr_diff(owner, repo, pr_number, token):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3.diff"
    }
    return requests.get(url, headers=headers).text[:8000]

def get_repo_files(owner, repo, token):
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    headers = {"Authorization": f"Bearer {token}"}
    data = requests.get(url, headers=headers).json()
    return [f["path"] for f in data.get("tree", []) if f["type"] == "blob"]

def get_best_practices():
    url = "https://raw.githubusercontent.com/cjdava/best-practices/main/code-peer-review.md"
    return requests.get(url).text[:3000]
