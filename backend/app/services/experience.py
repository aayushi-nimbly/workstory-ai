"""Read queries for the experience library (projects, PRs, skills, categories)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from sqlalchemy import Select, String, and_, case, cast, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import models as db
from app.experience.models import Complexity, Confidence, Involvement, PRStatus

# Strongest evidence first; used to sort and to pick a skill's strongest involvement.
INVOLVEMENT_RANK = {member.value: rank for rank, member in enumerate(Involvement)}
COMPLEXITY_RANK = {"high": 0, "medium": 1, "low": 2}


class ProjectSort(StrEnum):
    recent = "recent"  # latest PR activity first
    complexity = "complexity"  # high complexity first
    name = "name"


@dataclass
class ProjectFilters:
    q: str | None = None
    skills: Sequence[str] = ()
    involvement: Sequence[Involvement] = ()
    categories: Sequence[str] = ()
    complexity: Sequence[Complexity] = ()
    confidence: Sequence[Confidence] = ()


@dataclass
class PRStats:
    pr_count: int = 0
    started_on: date | None = None
    last_activity_on: date | None = None


@dataclass
class ProjectPage:
    projects: list[db.Project]
    stats: dict[str, PRStats]
    total: int
    unknown_filters: list[str] = field(default_factory=list)


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _skill_lookup(session: Session) -> dict[str, int]:
    """Lower-cased skill name or alias -> skill id."""
    lookup: dict[str, int] = {}
    for skill in session.scalars(select(db.Skill)):
        lookup[skill.name.casefold()] = skill.id
        for alias in skill.aliases:
            lookup.setdefault(alias.casefold(), skill.id)
    return lookup


def _pr_stats_subquery():
    activity = func.coalesce(db.PullRequest.merged_at, db.PullRequest.created_at)
    return (
        select(
            db.PullRequest.project_id.label("project_id"),
            func.count().label("pr_count"),
            func.min(db.PullRequest.created_at).label("started_on"),
            func.max(activity).label("last_activity_on"),
        )
        .where(db.PullRequest.project_id.is_not(None))
        .group_by(db.PullRequest.project_id)
        .subquery()
    )


def _apply_filters(
    session: Session, stmt: Select, filters: ProjectFilters
) -> tuple[Select, list[str]]:
    unknown: list[str] = []

    if filters.q:
        pattern = _like(filters.q.strip())
        stmt = stmt.where(
            or_(
                db.Project.name.ilike(pattern, escape="\\"),
                db.Project.summary.ilike(pattern, escape="\\"),
                db.Project.problem.ilike(pattern, escape="\\"),
                db.Project.implementation.ilike(pattern, escape="\\"),
                cast(db.Project.my_contributions, String).ilike(pattern, escape="\\"),
                cast(db.Project.decisions, String).ilike(pattern, escape="\\"),
            )
        )

    if filters.skills:
        lookup = _skill_lookup(session)
        for name in filters.skills:
            skill_id = lookup.get(name.casefold())
            if skill_id is None:
                unknown.append(f"skill '{name}'")
                continue
            conditions = [
                db.ProjectSkill.project_id == db.Project.id,
                db.ProjectSkill.skill_id == skill_id,
            ]
            if filters.involvement:
                conditions.append(
                    db.ProjectSkill.involvement.in_([i.value for i in filters.involvement])
                )
            stmt = stmt.where(exists().where(and_(*conditions)))

    if filters.categories:
        rows = session.execute(select(db.Category.id, db.Category.name)).all()
        by_name = {name.casefold(): cid for cid, name in rows}
        for name in filters.categories:
            category_id = by_name.get(name.casefold())
            if category_id is None:
                unknown.append(f"category '{name}'")
                continue
            stmt = stmt.where(
                exists().where(
                    db.ProjectCategory.project_id == db.Project.id,
                    db.ProjectCategory.category_id == category_id,
                )
            )

    if filters.complexity:
        stmt = stmt.where(db.Project.complexity.in_([c.value for c in filters.complexity]))
    if filters.confidence:
        stmt = stmt.where(db.Project.confidence.in_([c.value for c in filters.confidence]))

    return stmt, unknown


def list_projects(
    session: Session,
    filters: ProjectFilters,
    *,
    sort: ProjectSort = ProjectSort.recent,
    limit: int = 20,
    offset: int = 0,
) -> ProjectPage:
    stmt, unknown = _apply_filters(session, select(db.Project), filters)
    if unknown:
        # A filter value that doesn't exist can't match anything.
        return ProjectPage(projects=[], stats={}, total=0, unknown_filters=unknown)

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stats = _pr_stats_subquery()
    stmt = stmt.outerjoin(stats, stats.c.project_id == db.Project.id)
    match sort:
        case ProjectSort.recent:
            stmt = stmt.order_by(stats.c.last_activity_on.desc().nulls_last(), db.Project.name)
        case ProjectSort.complexity:
            rank = case(COMPLEXITY_RANK, value=db.Project.complexity, else_=len(COMPLEXITY_RANK))
            stmt = stmt.order_by(rank, db.Project.name)
        case ProjectSort.name:
            stmt = stmt.order_by(db.Project.name)

    stmt = (
        stmt.options(
            selectinload(db.Project.skill_links).selectinload(db.ProjectSkill.skill),
            selectinload(db.Project.category_links).selectinload(db.ProjectCategory.category),
        )
        .limit(limit)
        .offset(offset)
    )
    projects = list(session.scalars(stmt))
    return ProjectPage(projects=projects, stats=project_stats(session, projects), total=total)


def project_stats(session: Session, projects: Sequence[db.Project]) -> dict[str, PRStats]:
    if not projects:
        return {}
    stats = _pr_stats_subquery()
    rows = session.execute(
        select(stats).where(stats.c.project_id.in_([p.id for p in projects]))
    ).all()
    result = {p.id: PRStats() for p in projects}
    for row in rows:
        result[row.project_id] = PRStats(row.pr_count, row.started_on, row.last_activity_on)
    return result


def get_project(session: Session, project_id: str) -> db.Project | None:
    return session.scalar(
        select(db.Project)
        .where(db.Project.id == project_id)
        .options(
            selectinload(db.Project.skill_links).selectinload(db.ProjectSkill.skill),
            selectinload(db.Project.category_links).selectinload(db.ProjectCategory.category),
            selectinload(db.Project.pull_requests),
        )
    )


def list_pull_requests(
    session: Session,
    *,
    project_id: str | None = None,
    standalone: bool | None = None,
    status: Sequence[PRStatus] = (),
    repo: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[db.PullRequest], int]:
    stmt = select(db.PullRequest)
    if project_id is not None:
        stmt = stmt.where(db.PullRequest.project_id == project_id)
    if standalone is True:
        stmt = stmt.where(db.PullRequest.project_id.is_(None))
    elif standalone is False:
        stmt = stmt.where(db.PullRequest.project_id.is_not(None))
    if status:
        stmt = stmt.where(db.PullRequest.status.in_([s.value for s in status]))
    if repo:
        stmt = stmt.where(func.lower(db.PullRequest.repo) == repo.casefold())
    if q:
        pattern = _like(q.strip())
        stmt = stmt.where(
            or_(
                db.PullRequest.title.ilike(pattern, escape="\\"),
                db.PullRequest.summary.ilike(pattern, escape="\\"),
                db.PullRequest.contribution.ilike(pattern, escape="\\"),
            )
        )

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(db.PullRequest.created_at.desc(), db.PullRequest.id)
    return list(session.scalars(stmt.limit(limit).offset(offset))), total


def get_pull_request(session: Session, pr_id: str) -> db.PullRequest | None:
    return session.get(db.PullRequest, pr_id)


def list_skills(session: Session, *, category: str | None = None) -> list[db.Skill]:
    stmt = select(db.Skill).order_by(db.Skill.category, db.Skill.name)
    if category:
        stmt = stmt.where(func.lower(db.Skill.category) == category.casefold())
    return list(session.scalars(stmt))


def skill_projects(session: Session) -> dict[int, list[tuple[db.Project, str]]]:
    """Skill id -> [(project, involvement)], strongest involvement first."""
    rows = session.execute(
        select(db.ProjectSkill.skill_id, db.Project, db.ProjectSkill.involvement).join(
            db.Project, db.Project.id == db.ProjectSkill.project_id
        )
    ).all()
    result: dict[int, list[tuple[db.Project, str]]] = {}
    for skill_id, project, involvement in rows:
        result.setdefault(skill_id, []).append((project, involvement))
    for links in result.values():
        links.sort(key=lambda link: (INVOLVEMENT_RANK[link[1]], link[0].name))
    return result


def list_categories(session: Session) -> list[tuple[db.Category, list[db.Project]]]:
    categories = list(session.scalars(select(db.Category).order_by(db.Category.name)))
    rows = session.execute(
        select(db.ProjectCategory.category_id, db.Project)
        .join(db.Project, db.Project.id == db.ProjectCategory.project_id)
        .order_by(db.Project.name)
    ).all()
    by_category: dict[int, list[db.Project]] = {}
    for category_id, project in rows:
        by_category.setdefault(category_id, []).append(project)
    return [(c, by_category.get(c.id, [])) for c in categories]


def get_profile(session: Session) -> db.Profile | None:
    return session.get(db.Profile, 1)
