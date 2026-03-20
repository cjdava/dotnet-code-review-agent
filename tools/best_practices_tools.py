import requests

def get_best_practices():
    url = "https://raw.githubusercontent.com/cjdava/best-practices/main/code-peer-review.md"
    return requests.get(url).text[:3000]