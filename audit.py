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

# Kueri 1: Super cepat (< 300ms) menggunakan Search Index untuk seluruh PR sepanjang masa
PROFILE_QUERY = """
query($login: String!, $prSearchQuery: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
    }
  }
  mergedPrs: search(query: $prSearchQuery, type: ISSUE, first: 100) {
    issueCount
    nodes {
      ... on PullRequest {
        repository {
          owner { login }
        }
      }
    }
  }
}
"""

# Kueri 2: 5 repo per batch + 1x Tree lookup di root (memangkas 75% beban Git object lookup)
REPOS_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 5, after: $cursor, isFork: false, ownerAffiliations: OWNER, orderBy: {field: PUSHED_AT, direction: DESC}) {
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
        rootTree: object(expression: "HEAD:") {
          ... on Tree {
            entries {
              name
            }
          }
        }
        githubDir: object(expression: "HEAD:.github/workflows") {
          id
        }
      }
    }
  }
}
"""

def execute_graphql(query, variables, step_name="Query", max_retries=4):
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
                    print(f"[{step_name}] GraphQL Error: {payload['errors']}")
                    sys.exit(1)
                return payload["data"]
            
            if res.status_code in (502, 503, 504):
                wait = attempt * 4
                print(f"[{step_name} | Percobaan {attempt}/{max_retries}] HTTP {res.status_code}. Menunggu {wait} detik...")
                time.sleep(wait)
                continue
            
            print(f"[{step_name}] HTTP Error {res.status_code}: {res.text}")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"[{step_name} | Percobaan {attempt}/{max_retries}] Koneksi gagal: {e}")
            if attempt < max_retries:
                time.sleep(attempt * 4)
            else:
                sys.exit(1)
    print(f"ERROR: [{step_name}] gagal setelah {max_retries} percobaan.")
    sys.exit(1)

def run_audit():
    print("Memulai Tahap 1: Mengambil metrik profil & PR eksternal...")
    pr_query_str = f"is:pr author:{USERNAME} is:merged"
    profile_res = execute_graphql(
        PROFILE_QUERY,
        {"login": USERNAME, "prSearchQuery": pr_query_str},
        step_name="Tahap 1 - Profil"
    )
    
    contrib = profile_res["user"]["contributionsCollection"]
    pr_nodes = profile_res["mergedPrs"]["nodes"]
    
    ext_merged_prs = 0
    for pr in pr_nodes:
        if pr and pr.get("repository"):
            owner = pr["repository"]["owner"]["login"]
            if owner.lower() != USERNAME.lower():
                ext_merged_prs += 1

    print(f"Tahap 1 selesai. Ditemukan {ext_merged_prs} External Merged PRs.")

    all_repos = []
    cursor = None
    max_pages = 10  # 10 halaman x 5 repo = tetap 50 repositori orisinal

    for page in range(1, max_pages + 1):
        print(f"Memulai Tahap 2 (Halaman {page}/{max_pages})...")
        repo_res = execute_graphql(
            REPOS_QUERY,
            {"login": USERNAME, "cursor": cursor},
            step_name=f"Tahap 2 - Halaman {page}"
        )
        repo_data = repo_res["user"]["repositories"]
        all_repos.extend(repo_data["nodes"])
        
        if not repo_data["pageInfo"]["hasNextPage"]:
            break
        cursor = repo_data["pageInfo"]["endCursor"]
        time.sleep(0.5)

    total_additions = 0
    total_deletions = 0
    ci_cd_repos = 0
    tested_repos = 0
    meaningful_commits = 0
    total_sampled_commits = 0

    test_folder_names = {"test", "tests", "__tests__", "spec", "specs"}

    for repo in all_repos:
        if repo.get("githubDir") is not None:
            ci_cd_repos += 1
        
        # Cek folder test dari entries root directory
        root_tree = repo.get("rootTree")
        if root_tree and root_tree.get("entries"):
            entry_names = {e["name"].lower() for e in root_tree["entries"]}
            if entry_names.intersection(test_folder_names):
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
| **External Merged PRs** | `{ext_merged_prs} PRs` | Kode lolos *review* di repositori luar (sepanjang masa) |
| **Code Reviews Performed** | `{contrib['totalPullRequestReviewContributions']} Reviews` | Audit & tinjauan kode terhadap kontributor lain |
| **Refactoring Ratio** | `{refactor_ratio}%` (`-{total_deletions}` / `+{total_additions}` baris) | Rasio pembersihan kode usang dari `{total_sampled_commits}` *commit* |
| **Commit Message Hygiene** | `{commit_hygiene}%` | Log perubahan deskriptif (`>15` karakter, non-generik) |
| **Repo dengan CI/CD Aktif** | `{ci_cd_repos} dari {len(all_repos)} repo` | Otomasi *pipeline* (`.github/workflows`) |
| **Repo dengan Struktur Test** | `{tested_repos} dari {len(all_repos)} repo` | Keberadaan direktori `test/`, `tests/`, `__tests__/`, atau `spec/` |

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
