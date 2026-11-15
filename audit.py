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

# Tahap 1: Profil & Seluruh External Merged PRs (Paginated)
PROFILE_QUERY = """
query($login: String!, $prSearchQuery: String!, $cursor: String) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
    }
  }
  mergedPrs: search(query: $prSearchQuery, type: ISSUE, first: 100, after: $cursor) {
    pageInfo {
      hasNextPage
      endCursor
    }
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

# Tahap 2: Mengambil SELURUH Repositori Orisinal (Tanpa Batas Jumlah Repo)
ALL_REPOS_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 50, after: $cursor, isFork: false, ownerAffiliations: OWNER, orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        isEmpty
        diskUsage
        defaultBranchRef {
          name
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

# Tahap 3: Mengambil SELURUH Riwayat Commit per Repositori (100 commit per halaman sampai habis)
REPO_COMMITS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              messageHeadline
            }
          }
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
                    return None
                return payload["data"]
            
            if res.status_code in (502, 503, 504):
                wait = attempt * 3
                print(f"[{step_name} | Percobaan {attempt}/{max_retries}] HTTP {res.status_code}. Menunggu {wait} detik...")
                time.sleep(wait)
                continue
            
            print(f"[{step_name}] HTTP Error {res.status_code}: {res.text}")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"[{step_name} | Percobaan {attempt}/{max_retries}] Koneksi gagal: {e}")
            if attempt < max_retries:
                time.sleep(attempt * 3)
            else:
                return None
    return None

def analyze_repo_code_frequency(repo_name):
    """
    Menghitung additions/deletions sepanjang masa DAN mendeteksi anomali commit raksasa.
    Returns: (adds, dels, status, max_weekly_add)
    """
    url = f"https://api.github.com/repos/{USERNAME}/{repo_name}/stats/code_frequency"
    for _ in range(4):
        try:
            res = requests.get(url, headers=HEADERS, timeout=20)
            if res.status_code == 200:
                weeks = res.json()
                if isinstance(weeks, list) and len(weeks) > 0:
                    adds = sum(w[1] for w in weeks if len(w) >= 3)
                    dels = sum(abs(w[2]) for w in weeks if len(w) >= 3)
                    max_weekly_add = max((w[1] for w in weeks if len(w) >= 3), default=0)
                    return adds, dels, "OK", max_weekly_add
                return 0, 0, "EMPTY_STATS", 0
            elif res.status_code == 202:
                time.sleep(2.5)
                continue
            elif res.status_code == 422:
                # 422 biasanya muncul jika repo memiliki > 10.000 commit atau diff terlalu raksasa
                return 0, 0, "TOO_LARGE_422", 0
            else:
                return 0, 0, f"HTTP_{res.status_code}", 0
        except requests.exceptions.RequestException:
            return 0, 0, "TIMEOUT", 0
    return 0, 0, "COMPUTE_TIMEOUT_202", 0

def run_audit():
    print("Tahap 1: Mengambil metrik profil & seluruh External Merged PRs...")
    pr_query_str = f"is:pr author:{USERNAME} is:merged"
    ext_merged_prs = 0
    contrib = None
    cursor = None

    while True:
        profile_res = execute_graphql(
            PROFILE_QUERY,
            {"login": USERNAME, "prSearchQuery": pr_query_str, "cursor": cursor},
            step_name="Tahap 1 - Profil & PR"
        )
        if not profile_res:
            sys.exit(1)
            
        if contrib is None:
            contrib = profile_res["user"]["contributionsCollection"]
            
        pr_search = profile_res["mergedPrs"]
        for pr in pr_search["nodes"]:
            if pr and pr.get("repository"):
                owner = pr["repository"]["owner"]["login"]
                if owner.lower() != USERNAME.lower():
                    ext_merged_prs += 1
                    
        if not pr_search["pageInfo"]["hasNextPage"]:
            break
        cursor = pr_search["pageInfo"]["endCursor"]

    print(f"Tahap 1 selesai ({ext_merged_prs} External Merged PRs sepanjang masa).")

    print("Tahap 2: Mengambil SELURUH daftar repositori orisinal...")
    all_repos = []
    cursor = None
    while True:
        repo_res = execute_graphql(
            ALL_REPOS_QUERY,
            {"login": USERNAME, "cursor": cursor},
            step_name="Tahap 2 - Daftar Repo"
        )
        if not repo_res:
            sys.exit(1)
            
        repo_data = repo_res["user"]["repositories"]
        all_repos.extend(repo_data["nodes"])
        if not repo_data["pageInfo"]["hasNextPage"]:
            break
        cursor = repo_data["pageInfo"]["endCursor"]

    ci_cd_repos = 0
    tested_repos = 0
    meaningful_commits = 0
    total_all_commits = 0
    
    test_folder_names = {"test", "tests", "__tests__", "spec", "specs"}
    ignored_artifact_names = {"node_modules", "vendor", ".venv", "venv", "dist", "build", "__pycache__"}
    
    anomalies = []  # Menyimpan temuan masalah/anomali pada repositori
    active_repos = []

    for repo in all_repos:
        if repo.get("isEmpty") or not repo.get("defaultBranchRef"):
            continue
        
        repo_name = repo["name"]
        active_repos.append(repo_name)
        disk_kb = repo.get("diskUsage") or 0

        if repo.get("githubDir") is not None:
            ci_cd_repos += 1
        
        root_tree = repo.get("rootTree")
        if root_tree and root_tree.get("entries"):
            entry_names = {e["name"].lower() for e in root_tree["entries"]}
            if entry_names.intersection(test_folder_names):
                tested_repos += 1
            
            # Cek apakah ada folder build/dependency yang bocor ke repository
            leaked_dirs = entry_names.intersection(ignored_artifact_names)
            if leaked_dirs:
                anomalies.append(
                    f"- **`{repo_name}`**: Direktori dependensi/build (`{', '.join(sorted(leaked_dirs))}`) ikut ter-commit ke repositori."
                )

        # Cek ukuran repositori tidak wajar (> 50 MB)
        if disk_kb > 50000:
            anomalies.append(
                f"- **`{repo_name}`**: Ukuran repositori besar (`{round(disk_kb / 1024, 1)} MB`) — indikasi file biner/aset besar tanpa Git LFS."
            )

    print(f"Tahap 3: Memindai 100% seluruh riwayat commit dari {len(active_repos)} repositori aktif...")
    for idx, repo_name in enumerate(active_repos, 1):
        commit_cursor = None
        repo_commit_count = 0
        while True:
            c_res = execute_graphql(
                REPO_COMMITS_QUERY,
                {"owner": USERNAME, "name": repo_name, "cursor": commit_cursor},
                step_name=f"Commit {repo_name}"
            )
            if not c_res or not c_res.get("repository") or not c_res["repository"].get("defaultBranchRef"):
                break
                
            history = c_res["repository"]["defaultBranchRef"]["target"]["history"]
            for c in history["nodes"]:
                total_all_commits += 1
                repo_commit_count += 1
                msg = c["messageHeadline"].strip()
                if len(msg) > 15 and not msg.lower().startswith(("update", "fix", "wip", "test")):
                    meaningful_commits += 1
                    
            if not history["pageInfo"]["hasNextPage"]:
                break
            commit_cursor = history["pageInfo"]["endCursor"]
        time.sleep(0.2)

    print("Tahap 4: Menghitung Refactoring Ratio & mendeteksi Giant Commits...")
    total_additions = 0
    total_deletions = 0
    counted_freq_repos = 0

    for repo_name in active_repos:
        adds, dels, status, max_weekly = analyze_repo_code_frequency(repo_name)
        if status == "OK":
            total_additions += adds
            total_deletions += dels
            counted_freq_repos += 1
            # Deteksi lonjakan commit raksasa (> 15.000 baris dalam 1 minggu)
            if max_weekly > 15000:
                anomalies.append(
                    f"- **`{repo_name}`**: Terdeteksi *bulk/giant commit* (`+{max_weekly:,}` baris dalam satu siklus) — indikasi file auto-generated, dataset, atau kode tanpa pemecahan atomik."
                )
        elif status in ("COMPUTE_TIMEOUT_202", "TOO_LARGE_422", "TIMEOUT"):
            anomalies.append(
                f"- **`{repo_name}`**: Komputasi *diff* ditolak/timeout oleh API GitHub (`{status}`) — indikasi riwayat *commit* terlalu masif atau file biner berat."
            )

    refactor_ratio = round((total_deletions / total_additions * 100), 1) if total_additions > 0 else 0
    commit_hygiene = round((meaningful_commits / total_all_commits * 100), 1) if total_all_commits > 0 else 0

    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    # Susun bagian laporan anomali / masalah yang perlu diperhatikan
    if anomalies:
        anomalies_section = "#### ⚠️ Temuan Audit & Anomali Repositori (Perlu Perhatian)\n" + "\n".join(anomalies)
    else:
        anomalies_section = "#### ✅ Temuan Audit & Anomali Repositori\n*Tidak ditemukan anomali commit raksasa, kebocoran dependensi (`node_modules`/`.venv`), maupun pembengkakan ukuran repositori.*"

    markdown_output = f"""
| Metrik Evaluasi Teknis | Nilai Terverifikasi | Cakupan Populasi (100% Full Scan) |
| :--- | :--- | :--- |
| **External Merged PRs** | `{ext_merged_prs} PRs` | Seluruh PR *merged* di repositori luar (sepanjang masa) |
| **Code Reviews Performed** | `{contrib['totalPullRequestReviewContributions']} Reviews` | Audit & tinjauan kode terhadap kontributor lain |
| **Refactoring Ratio** | `{refactor_ratio}%` (`-{total_deletions:,}` / `+{total_additions:,}` baris) | Seluruh riwayat baris kode dari `{counted_freq_repos}` repo terkomputasi |
| **Commit Message Hygiene** | `{commit_hygiene}%` | Dari **100% seluruh `{total_all_commits:,}` commit** di `{len(active_repos)}` repo aktif |
| **Repo dengan CI/CD Aktif** | `{ci_cd_repos} dari {len(active_repos)} repo` | Otomasi *pipeline* (`.github/workflows`) |
| **Repo dengan Struktur Test** | `{tested_repos} dari {len(active_repos)} repo` | Keberadaan direktori `test/`, `tests/`, `__tests__/`, atau `spec/` |

{anomalies_section}

*Audit populasi penuh (**100% dari {len(active_repos)} repositori orisinal** & **{total_all_commits:,} commit**) dijalankan otomatis via GitHub API pada `{now_utc}`*
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
    print("Audit populasi penuh berhasil diperbarui ke README.md")
