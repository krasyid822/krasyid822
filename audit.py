import os
import re
import sys
import requests
from datetime import datetime, timezone

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    print("ERROR: GITHUB_TOKEN tidak ditemukan di environment variables.")
    sys.exit(1)

USERNAME = "krasyid822"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": f"{USERNAME}-profile-audit",
    "Accept": "application/vnd.github+json"
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
      pullRequestContributionsByRepository(maxRepositories: 20) {
        repository {
          nameWithOwner
          isPrivate
          owner { login }
          stargazerCount
        }
        contributions(first: 50) {
          nodes {
            pullRequest {
              merged
              additions
              deletions
            }
          }
        }
      }
    }
    repositories(first: 30, isFork: false, ownerAffiliations: OWNER, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        isPrivate
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 30) {
                nodes {
                  additions
                  deletions
                  messageHeadline
                }
              }
            }
          }
        }
        object(expression: "HEAD:.github/workflows") {
          id
        }
      }
    }
  }
}
"""

def run_audit():
    res = requests.post(
        "https://api.github.com/graphql",
        json={"query": QUERY, "variables": {"login": USERNAME}},
        headers=HEADERS,
        timeout=30
    )
    
    # Validasi status HTTP sebelum parsing JSON
    if res.status_code != 200:
        print(f"HTTP Error {res.status_code}: {res.text}")
        sys.exit(1)

    payload = res.json()
    if "errors" in payload:
        print(f"GraphQL Error: {payload['errors']}")
        sys.exit(1)

    data = payload.get("data", {}).get("user")
    if not data:
        print("ERROR: Data user tidak ditemukan atau token tidak memiliki izin 'read:user'.")
        sys.exit(1)
    
    contrib = data["contributionsCollection"]
    repos = data["repositories"]["nodes"]
    
    # 1. Hitung External Merged PRs
    ext_merged_prs = 0
    for repo_contrib in contrib["pullRequestContributionsByRepository"]:
        repo_owner = repo_contrib["repository"]["owner"]["login"]
        if repo_owner.lower() != USERNAME.lower():
            for pr in repo_contrib["contributions"]["nodes"]:
                if pr["pullRequest"]["merged"]:
                    ext_merged_prs += 1

    # 2. Analisis Kualitas Commit & Infrastruktur Repo Orisinal
    total_additions = 0
    total_deletions = 0
    ci_cd_repos = 0
    meaningful_commits = 0
    total_sampled_commits = 0

    for repo in repos:
        if repo["object"] is not None:
            ci_cd_repos += 1
        
        branch = repo["defaultBranchRef"]
        if branch and branch["target"]:
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
| Metrik Evaluasi Teknis | Nilai Terverifikasi | Indikator Kualitas |
| :--- | :--- | :--- |
| **External Merged PRs** | `{ext_merged_prs} PRs` | Kode lolos *review* di repositori eksternal |
| **Code Reviews Performed** | `{contrib['totalPullRequestReviewContributions']} Reviews` | Kemampuan membaca & mengaudit kode orang lain |
| **Refactoring Ratio** | `{refactor_ratio}%` (`-{total_deletions}` / `+{total_additions}` baris) | Rasio penghapusan kode usang vs penambahan baru |
| **Commit Message Hygiene** | `{commit_hygiene}%` | Konsistensi penulisan log perubahan yang deskriptif |
| **Repo dengan CI/CD Aktif** | `{ci_cd_repos} dari {len(repos)} repo` | Penerapan otomasi *build/test* (`.github/workflows`) |

*Terakhir diaudit secara otomatis via GitHub GraphQL API pada: `{now_utc}`*
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
    print("Audit berhasil diperbarui ke README.md")
