"""Cross-record checks for an experience file.

Pydantic validates each record on its own. These checks look across records:
IDs that must be unique, references that must exist, and links that must agree
in both directions.

Errors make the file invalid. Warnings point at likely mistakes but still allow
the import.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from app.experience.models import ExperienceFile, PRStatus


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.path}: {self.message}"


def check_references(data: ExperienceFile) -> list[Issue]:
    issues: list[Issue] = []

    def error(path: str, message: str) -> None:
        issues.append(Issue("error", path, message))

    def warning(path: str, message: str) -> None:
        issues.append(Issue("warning", path, message))

    # ---- Uniqueness ----
    for path, label, values in (
        ("projects", "project id", [p.id for p in data.projects]),
        ("pull_requests", "pull request id", [pr.id for pr in data.pull_requests]),
        ("skills", "skill name", [s.name.casefold() for s in data.skills]),
        ("categories", "category name", [c.name.casefold() for c in data.categories]),
    ):
        for value, count in Counter(values).items():
            if count > 1:
                error(path, f"duplicate {label} '{value}' ({count} times)")

    # Skill names and aliases must not clash, otherwise a mention is ambiguous.
    skill_names = {s.name.casefold(): s.name for s in data.skills}
    alias_to_skill: dict[str, str] = {}
    for i, skill in enumerate(data.skills):
        for alias in skill.aliases:
            key = alias.casefold()
            if key in skill_names and skill_names[key] != skill.name:
                error(f"skills[{i}].aliases", f"alias '{alias}' is also a skill name")
            elif key in alias_to_skill and alias_to_skill[key] != skill.name:
                error(
                    f"skills[{i}].aliases",
                    f"alias '{alias}' is used by both '{alias_to_skill[key]}' and '{skill.name}'",
                )
            alias_to_skill[key] = skill.name

    project_ids = {p.id for p in data.projects}
    prs_by_id = {pr.id: pr for pr in data.pull_requests}
    category_names = {c.name for c in data.categories}
    category_names_folded = {c.name.casefold(): c.name for c in data.categories}

    # ---- Projects ----
    for i, project in enumerate(data.projects):
        base = f"projects[{i}] ({project.id})"

        for name in project.categories:
            if name not in category_names:
                hint = category_names_folded.get(name.casefold())
                msg = f"unknown category '{name}'"
                error(f"{base}.categories", f"{msg}; did you mean '{hint}'?" if hint else msg)

        seen_skills: set[str] = set()
        for j, link in enumerate(project.skills):
            path = f"{base}.skills[{j}]"
            if link.name in seen_skills:
                error(path, f"skill '{link.name}' is listed more than once")
            seen_skills.add(link.name)
            if link.name not in skill_names.values():
                canonical = skill_names.get(link.name.casefold()) or alias_to_skill.get(
                    link.name.casefold()
                )
                if canonical:
                    error(path, f"use the canonical skill name '{canonical}', not '{link.name}'")
                else:
                    error(path, f"unknown skill '{link.name}'; add it to the top-level 'skills'")

        for pr_id in project.pr_ids:
            pr = prs_by_id.get(pr_id)
            if pr is None:
                error(f"{base}.pr_ids", f"unknown pull request '{pr_id}'")
            elif pr.project_id != project.id:
                error(
                    f"{base}.pr_ids",
                    f"'{pr_id}' is listed here but its project_id is '{pr.project_id}'",
                )
        for pr_id, count in Counter(project.pr_ids).items():
            if count > 1:
                error(f"{base}.pr_ids", f"'{pr_id}' is listed {count} times")

        for j, decision in enumerate(project.decisions):
            for pr_id in decision.pr_ids:
                if pr_id not in project.pr_ids:
                    error(
                        f"{base}.decisions[{j}].pr_ids",
                        f"'{pr_id}' is not one of this project's PRs",
                    )

        if not project.pr_ids:
            warning(base, "project has no pull requests as evidence")
        elif all(prs_by_id[p].status != PRStatus.merged for p in project.pr_ids if p in prs_by_id):
            warning(base, "none of this project's PRs are merged")

        for j, metric in enumerate(project.metrics):
            if metric.before is None and metric.after is None:
                warning(f"{base}.metrics[{j}]", f"metric '{metric.name}' has no values")

    # ---- Pull requests ----
    for i, pr in enumerate(data.pull_requests):
        if pr.project_id is None:
            continue
        path = f"pull_requests[{i}] ({pr.id}).project_id"
        if pr.project_id not in project_ids:
            error(path, f"unknown project '{pr.project_id}'")
        else:
            project = next(p for p in data.projects if p.id == pr.project_id)
            if pr.id not in project.pr_ids:
                error(path, f"project '{pr.project_id}' does not list this PR in its pr_ids")

    # ---- Unused definitions ----
    used_skills = {link.name for p in data.projects for link in p.skills}
    for i, skill in enumerate(data.skills):
        if skill.name not in used_skills:
            warning(f"skills[{i}]", f"skill '{skill.name}' is not used by any project")

    used_categories = {name for p in data.projects for name in p.categories}
    for i, category in enumerate(data.categories):
        if category.name not in used_categories:
            warning(f"categories[{i}]", f"category '{category.name}' is not used by any project")

    return issues
