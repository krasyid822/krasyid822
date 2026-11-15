import os
import re
import sys
import time
import requests
from datetime import datetime, timezone

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    print("ERROR: GITHUB_TOKEN tidak ditemukan.")
    sys.exit(1)

USERNAME = "krasyid822"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": f"{USERNAME}-profile-audit",
    "Accept": "application/vnd.github+json"
}

# Kueri 1: Mengambil metrik kontribusi & PR eksternal (hingga 100 repo PR)
PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
      pullRequestContributionsByRepository(maxRepositories: 100) {
        repository {
          owner { login }
        }
        contributions(first: 50) {
          nodes {
            pullRequest {
              merged
            }
          }
        }
      }
    }
  }
}
"""

# Kueri 2: Mengambil repositori secara bertahap (10 repo per halaman, 50 commit per repo)
REPOS_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 10, after: $cursor, isFork: false, ownerAffiliations: OWNER, orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 50) {
                nodes {
                  additions
                  deletions
                  messageHeadline
                }
              }
            }
          }
        }
        workflowsDir: object(expression: "HEAD:.github/workflows") { id }
        testsDir1: object(expression: "HEAD:tests") { id }
        testsDir2: object(expression: "HEAD:test") { id }
        testsDir3: object(expression: "HEAD:__tests__") { id }
      }
    }
  }
}
"""

def execute_graphql(query, variables, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.post(
                "https://api.github.com/graphql",
                json={"query": query, "variables": variables},
                headers=HEADERS,
                timeout=30
            )
            if res.status_code == 200:
                payload = res.json()
                if "errors" in payload:
                    print(f"GraphQL Error: {payload['errors']}")
                    sys.exit(1)
                return payload["data"]
            
            if res.status_code in (502, 503, 504):
                print(f"[Percobaan {attempt}/{max_retries}] HTTP {res.status_code}. Menunggu {attempt * 4} detik...")
                time.sleep(attempt * 4)
                continue
            
            print(f"HTTP Error {res.status_code}: {res.text}")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"[Percobaan {attempt}/{max_retries}] Koneksi gagal: {e}")
            if attempt < max_retries:
                time.sleep(attempt * 4)
            else:
                sys.exit(1)
    sys.exit(1)

def run_audit():
    # Tahap 1: Audit Profil & PR Eksternal
    profile_data = execute_graphql(PROFILE_QUERY, {"login": USERNAME})["user"]
    contrib = profile_data["contributionsCollection"]
    
    ext_merged_prs = 0
    for repo_contrib in contrib["pullRequestContributionsByRepository"]:
        repo_owner = repo_contrib["repository"]["owner"]["login"]
        if repo_owner.lower() != USERNAME.lower():
            for pr in repo_contrib["contributions"]["nodes"]:
                if pr["pullRequest"] and pr["pullRequest"]["merged"]:
                    ext_merged_prs += 1

    # Tahap 2: Audit Repositori secara bertahap (Pagination hingga 50 repo)
    all_repos = []
    cursor = None
    max_pages = 5  # 5 halaman x 10 repo = 50 repo orisinal terbaru

    for page in range(max_pages):
        repo_data = execute_graphql(REPOS_QUERY, {"login": USERNAME, "cursor": cursor})["user"]["repositories"]
        all_repos.extend(repo_data["nodes"])
        
        if not repo_data["pageInfo"]["hasNextPage"]:
            break
        cursor = repo_data["pageInfo"]["endCursor"]
        time.sleep(0.5)  # Jeda singkat agar tidak memicu rate-limit sekunder

    total_additions = 0
    total_deletions = 0
    ci_cd_repos = 0
    tested_repos = 0
    meaningful_commits = 0
    total_sampled_commits = 0

    for repo in all_repos:
        if repo.get("workflowsDir") is not None:
            ci_cd_repos += 1
        
        if any(repo.get(k) is not None for k in ("testsDir1", "testsDir2", "testsDir3")):
            tested_repos += 1
        
        branch = repo.get("defaultBranchRef")
        if branch and branch.get("target"):
            commits = branch["target"]["history"]["nodes"]
            for c in commits:
                total_sampled_commits += 1
                total_additions += c["additions"]
                total_deletions += c["deletions"]
                msg = c["messageHeadline"].strip()
                if len(msg) > 15 and not msg.lower().startswith(("update", "fix", "wip", "test")):
                    meaningful_commits += 1

    refactor_ratio = round((total_deletions / total_additions * 100), 1) if total_additions > 0 else 0
    commit_hygiene = round((meaningful_commits / total_sampled_commits * 100), 1) if total_sampled_commits > 0 else 0

    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    markdown_output = f"""
| Metrik Evaluasi Teknis | Nilai Terverifikasi | Cakupan & Indikator Kualitas |
| :--- | :--- | :--- |
| **External Merged PRs** | `{ext_merged_prs} PRs` | Kode lolos *review* di repositori luar (hingga 100 repo) |
| **Code Reviews Performed** | `{contrib['totalPullRequestReviewContributions']} Reviews` | Audit & tinjauan kode terhadap kontributor lain |
| **Refactoring Ratio** | `{refactor_ratio}%` (`-{total_deletions}` / `+{total_additions}` baris) | Rasio pembersihan kode usang dari `{total_sampled_commits}` *commit* |
| **Commit Message Hygiene** | `{commit_hygiene}%` | Log perubahan deskriptif (`>15` karakter, non-generik) |
| **Repo dengan CI/CD Aktif** | `{ci_cd_repos} dari {len(all_repos)} repo` | Otomasi *pipeline* (`.github/workflows`) |
| **Repo dengan Struktur Test** | `{tested_repos} dari {len(all_repos)} repo` | Keberadaan direktori `test/`, `tests/`, atau `__tests__/` |

*Diaudit otomatis dari **{len(all_repos)} repositori orisinal** & **{total_sampled_commits} commit** via GitHub GraphQL API pada `{now_utc}`*
"""
    return markdown_output.strip()

def update_readme(new_content):
    with open("README.md", "r", encoding="utf-8") as f:
        readme = f.read()
    
    pattern = r"(<!-- AUDIT_START -->)(.*?)(<!-- AUDIT_END -->)"
    if not re.search(pattern, readme, flags=re.DOTALL):
        print("ERROR: Tag <!-- AUDIT_START --> dan <!-- AUDIT_END --> tidak ditemukan di README.md.")
        sys.exit(1)

    updated = re.sub(pattern, rf"\1\n{new_content}\n\3", readme, flags=re.DOTALL)
    
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(updated)

if __name__ == "__main__":
    report = run_audit()
    update_readme(report)
    print("Audit penuh berhasil diperbarui ke README.md")
