"""Assemble the final experience file from extraction outputs.

Inputs (all under data/extraction/, git-ignored):
    pr-records/*.json   step 1 output: one record per PR
    projects/*.json     step 2 output: Project objects
    profile.json        owner name and professional summary

Output:
    data/workstory-experience.json  (validated with the app's schema)

Usage (from the backend folder, so the schema can be imported):
    uv run python ../extraction/assemble.py
"""

import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.experience.validate import validate_data  # noqa: E402

EXTRACTION = ROOT / "data" / "extraction"
OUTPUT = ROOT / "data" / "workstory-experience.json"

INVOLVEMENT_ORDER = ["implemented", "collaborated", "modified", "used", "discussed", "mentioned"]

# Skill group for the Skills page. Unknown skills fall back to "Other".
SKILL_GROUPS = {
    "Languages": ["TypeScript", "JavaScript", "Python", "Go", "SQL", "HTML", "CSS", "YAML"],
    "Backend": [
        "Node.js",
        "Express",
        "NestJS",
        "REST APIs",
        "Mongoose",
        "Zod",
        "Mastra",
        "JWT",
        "Dead Letter Queues",
        "Report Generation",
        "PDFKit",
        "ExcelJS",
        "Jinja",
        "FastAPI",
        "Django",
        "Django REST Framework",
        "Flask",
        "WebSockets",
        "OAuth",
        "Web Push",
    ],
    "Frontend": [
        "React",
        "Next.js",
        "Redux",
        "Redux-Saga",
        "TanStack Query",
        "Lingui",
        "Jotai",
        "Vite",
        "PWA",
        "HTMX",
    ],
    "Databases": [
        "MongoDB",
        "PostgreSQL",
        "Firebase Realtime Database",
        "Firestore",
        "Redis",
        "Alembic",
    ],
    "Cloud & Infrastructure": [
        "Google Cloud Platform",
        "Google Cloud Run",
        "Google Cloud Functions",
        "Firebase Cloud Functions",
        "Google Cloud Pub/Sub",
        "Google Cloud Tasks",
        "Google Cloud Storage",
        "Google Cloud Scheduler",
        "AWS",
        "AWS Lambda",
        "Amazon EventBridge",
        "Amazon CloudWatch",
        "Amazon S3",
        "Terraform",
        "Docker",
        "Cloudflare Workers",
        "Firebase",
        "Firebase Authentication",
        "Google Cloud Logging",
        "Google Cloud Monitoring",
    ],
    "CI/CD & Tooling": ["GitHub Actions", "npm", "CI/CD", "ESLint", "Markdown", "Obsidian"],
    "Integrations": ["Twilio", "Whapi"],
    "Engineering Practices": [
        "Data Migration",
        "Feature Flags",
        "Incident Response",
        "Internationalisation",
        "Code Review Automation",
        "Technical Writing",
        "Unit Testing",
        "Contract Testing",
        "Data Modeling",
    ],
    "Testing": ["Jest", "Vitest", "Pact", "Playwright", "Maestro"],
    "AI/GenAI": [
        "LLM",
        "LLMs",
        "Prompt Engineering",
        "Prompt Injection Mitigation",
        "OpenAI API",
        "Claude",
        "Gemini",
        "Vertex AI",
        "MCP",
        "RAG",
    ],
}
GROUP_OF = {name.casefold(): group for group, names in SKILL_GROUPS.items() for name in names}


def load_list(directory: Path) -> list[dict]:
    return [item for f in sorted(directory.glob("*.json")) for item in json.loads(f.read_text())]


def canonical_names(projects: list[dict]) -> dict[str, str]:
    """Map lower-cased spellings to one canonical spelling (the most common one)."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in projects:
        for s in p.get("skills", []):
            counts[s["name"].strip().casefold()][s["name"].strip()] += 1
    return {key: max(spellings, key=spellings.get) for key, spellings in counts.items()}


def clean_id(value: str) -> str:
    """IDs allow only lowercase letters, digits and hyphens (repo names may contain '_')."""
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")


def main() -> int:
    records = load_list(EXTRACTION / "pr-records")
    projects = load_list(EXTRACTION / "projects")
    profile = json.loads((EXTRACTION / "profile.json").read_text())

    for r in records:
        r["id"] = clean_id(r["id"])
    for p in projects:
        p["id"] = clean_id(p["id"])
        p["pr_ids"] = [clean_id(i) for i in p["pr_ids"]]
        for d in p.get("decisions", []):
            d["pr_ids"] = [clean_id(i) for i in d.get("pr_ids", [])]
        # Metrics must be measured outcomes; stated targets are not evidence of impact.
        p["metrics"] = [m for m in p.get("metrics", []) if "target" not in m["evidence"].lower()]

    # ---- Skills: one spelling per skill, strongest involvement per project ----
    canon = canonical_names(projects)
    for p in projects:
        merged: dict[str, dict] = {}
        for s in p.get("skills", []):
            name = canon[s["name"].strip().casefold()]
            current = merged.get(name)
            if current is None or INVOLVEMENT_ORDER.index(
                s["involvement"]
            ) < INVOLVEMENT_ORDER.index(current["involvement"]):
                merged[name] = {**s, "name": name}
        p["skills"] = list(merged.values())

    skill_names = sorted({s["name"] for p in projects for s in p["skills"]}, key=str.casefold)
    skills = [{"name": n, "category": GROUP_OF.get(n.casefold(), "Other")} for n in skill_names]
    categories = [{"name": c} for c in sorted({c for p in projects for c in p["categories"]})]

    # ---- Pull requests, linked to their project ----
    project_of = {pr_id: p["id"] for p in projects for pr_id in p["pr_ids"]}
    pull_requests = []
    for r in sorted(records, key=lambda r: (r["created_at"], r["id"])):
        status = r["status"]
        merged_at = r.get("merged_at") if status == "merged" else None
        if status == "merged" and not merged_at:
            merged_at = r["created_at"]
        pull_requests.append(
            {
                "id": r["id"],
                "project_id": project_of.get(r["id"]),
                "title": r["title"],
                "summary": r["summary"],
                "contribution": r["contribution"],
                "problem": r.get("problem") or None,
                "technologies": r.get("technologies", []),
                "repo": r.get("repo"),
                "url": r.get("url"),
                "created_at": r["created_at"][:10],
                "merged_at": merged_at[:10] if merged_at else None,
                "status": status,
                "confidence": r["confidence"],
            }
        )

    data = {
        "metadata": {
            "schema_version": "1.0",
            "owner_name": profile["owner_name"],
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "data_source": "GitHub pull requests (LLM-assisted extraction, reviewed)",
            "sanitised": True,
        },
        "professional_summary": profile["professional_summary"],
        "projects": projects,
        "pull_requests": pull_requests,
        "skills": skills,
        "categories": categories,
    }

    result = validate_data(data)
    for issue in result.issues:
        print(issue)
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(
        f"\n{'✓ Valid' if result.is_valid else '✗ Invalid'}: {len(projects)} projects, "
        f"{len(pull_requests)} PRs, {len(skills)} skills, {len(categories)} categories "
        f"→ {OUTPUT.relative_to(ROOT)}"
    )
    return 0 if result.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
