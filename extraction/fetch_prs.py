"""Fetch details for the pull requests you authored, using the GitHub CLI (`gh`).

Read-only. Saves PR metadata, descriptions and changed file *names* (never diffs).

Usage:
    python extraction/fetch_prs.py                    # all PRs you authored
    python extraction/fetch_prs.py --limit 50         # quick trial

Output (git-ignored):
    data/raw/pr-index.json        search results
    data/raw/prs/<repo>__<n>.json one file per PR (re-runs skip existing files)
    data/raw/prs.json             everything combined
"""

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DETAIL_FIELDS = (
    "number,title,body,state,createdAt,mergedAt,closedAt,url,isDraft,"
    "additions,deletions,changedFiles,files,labels,baseRefName,headRefName"
)
MAX_FILES = 60  # enough to see what areas a PR touched


def gh_json(*args: str) -> object:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh {' '.join(args)} failed")
    return json.loads(result.stdout)


def search_prs(limit: int) -> list[dict]:
    return gh_json(
        "search",
        "prs",
        "--author",
        "@me",
        "--limit",
        str(limit),
        "--json",
        "number,title,repository,state,createdAt,closedAt,url,isDraft",
    )  # type: ignore[return-value]


def fetch_detail(repo: str, number: int) -> dict:
    data = gh_json("pr", "view", str(number), "--repo", repo, "--json", DETAIL_FIELDS)
    assert isinstance(data, dict)
    data["repo"] = repo
    data["files"] = [f["path"] for f in data.get("files", [])][:MAX_FILES]
    data["labels"] = [label["name"] for label in data.get("labels", [])]
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    out_dir = RAW / "prs"
    out_dir.mkdir(parents=True, exist_ok=True)

    index = search_prs(args.limit)
    (RAW / "pr-index.json").write_text(json.dumps(index, indent=2))
    print(f"Found {len(index)} PRs")

    todo = []
    for pr in index:
        repo = pr["repository"]["nameWithOwner"]
        path = out_dir / f"{repo.replace('/', '__')}__{pr['number']}.json"
        if not path.exists():
            todo.append((repo, pr["number"], path))
    print(f"Fetching {len(todo)} (skipping {len(index) - len(todo)} already saved)")

    failed = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_detail, repo, n): (repo, n, path) for repo, n, path in todo}
        for i, future in enumerate(as_completed(futures), start=1):
            repo, n, path = futures[future]
            try:
                path.write_text(json.dumps(future.result(), indent=2))
            except Exception as exc:  # keep going; re-run to retry failures
                failed.append(f"{repo}#{n}: {exc}")
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}")

    combined = [json.loads(p.read_text()) for p in sorted(out_dir.glob("*.json"))]
    (RAW / "prs.json").write_text(json.dumps(combined, indent=2))
    print(f"Saved {len(combined)} PRs to {RAW / 'prs.json'}")
    if failed:
        print(f"{len(failed)} failed (re-run to retry):", *failed[:10], sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
