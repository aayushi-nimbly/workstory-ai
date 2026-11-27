"""Fetch evidence for personal repositories that have no pull requests.

Read-only. For each repo: description, languages, README, file paths and commit
messages (no file contents other than the README).

Usage:
    python extraction/fetch_repos.py owner/repo [owner/repo ...]

Output (git-ignored): data/raw/repos/<owner>__<repo>.json
"""

import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "repos"
MAX_FILES = 300
MAX_README_CHARS = 20_000


def gh_api(path: str) -> object | None:
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    return json.loads(result.stdout) if result.returncode == 0 else None


def fetch(repo: str) -> dict:
    info = gh_api(f"repos/{repo}") or {}
    readme = gh_api(f"repos/{repo}/readme")
    readme_text = (
        base64.b64decode(readme["content"]).decode("utf-8", "replace")[:MAX_README_CHARS]
        if isinstance(readme, dict) and readme.get("content")
        else ""
    )
    branch = info.get("default_branch", "main")
    tree = gh_api(f"repos/{repo}/git/trees/{branch}?recursive=1") or {}
    files = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"][:MAX_FILES]
    commits = gh_api(f"repos/{repo}/commits?per_page=100") or []
    return {
        "repo": repo,
        "description": info.get("description"),
        "visibility": info.get("visibility"),
        "created_at": info.get("created_at"),
        "pushed_at": info.get("pushed_at"),
        "homepage": info.get("homepage"),
        "languages": gh_api(f"repos/{repo}/languages") or {},
        "readme": readme_text,
        "files": files,
        "commits": [
            {"date": c["commit"]["author"]["date"][:10], "message": c["commit"]["message"]}
            for c in commits
            if isinstance(c, dict)
        ],
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for repo in argv:
        data = fetch(repo)
        (OUT / f"{repo.replace('/', '__')}.json").write_text(json.dumps(data, indent=2))
        print(
            f"{repo}: {len(data['files'])} files, {len(data['commits'])} commits, "
            f"README {len(data['readme'])} chars"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
