"""Experience library API: profile, projects, pull requests, skills and categories."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    CategoryOut,
    Page,
    ProfileOut,
    ProjectDetailOut,
    ProjectRefOut,
    ProjectSkillOut,
    ProjectSummaryOut,
    PullRequestOut,
    SkillOut,
    SkillProjectOut,
)
from app.db import models as db
from app.db.session import get_db
from app.experience.models import Complexity, Confidence, Involvement, PRStatus
from app.services import experience as queries
from app.services.experience import INVOLVEMENT_RANK, ProjectFilters, ProjectSort, PRStats

router = APIRouter(tags=["experience"])

SessionDep = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def _project_skills(project: db.Project) -> list[ProjectSkillOut]:
    links = sorted(
        project.skill_links,
        key=lambda link: (INVOLVEMENT_RANK[link.involvement], link.skill.name),
    )
    return [
        ProjectSkillOut(
            name=link.skill.name,
            category=link.skill.category,
            involvement=link.involvement,
            evidence=link.evidence,
        )
        for link in links
    ]


def _summary_fields(project: db.Project, stats: PRStats) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "summary": project.summary,
        "complexity": project.complexity,
        "complexity_reason": project.complexity_reason,
        "confidence": project.confidence,
        "categories": sorted(link.category.name for link in project.category_links),
        "skills": _project_skills(project),
        "pr_count": stats.pr_count,
        "started_on": stats.started_on,
        "last_activity_on": stats.last_activity_on,
    }


# ---------- Profile ----------


@router.get("/profile", response_model=ProfileOut)
def get_profile(session: SessionDep) -> db.Profile:
    profile = queries.get_profile(session)
    if profile is None:
        raise _not_found("Profile (import an experience file first)")
    return profile


# ---------- Projects ----------


@router.get("/projects", response_model=Page[ProjectSummaryOut])
def list_projects(
    session: SessionDep,
    q: Annotated[str | None, Query(description="Text search in project content.")] = None,
    skill: Annotated[
        list[str], Query(description="Skill name or alias. Repeat to require several.")
    ] = [],  # noqa: B006  (FastAPI copies defaults per request)
    involvement: Annotated[
        list[Involvement], Query(description="Only count skills used at these levels.")
    ] = [],  # noqa: B006
    category: Annotated[list[str], Query(description="Repeat to require several.")] = [],  # noqa: B006
    complexity: Annotated[list[Complexity], Query()] = [],  # noqa: B006
    confidence: Annotated[list[Confidence], Query()] = [],  # noqa: B006
    sort: ProjectSort = ProjectSort.recent,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[ProjectSummaryOut]:
    filters = ProjectFilters(
        q=q,
        skills=skill,
        involvement=involvement,
        categories=category,
        complexity=complexity,
        confidence=confidence,
    )
    page = queries.list_projects(session, filters, sort=sort, limit=limit, offset=offset)
    items = [ProjectSummaryOut(**_summary_fields(p, page.stats[p.id])) for p in page.projects]
    return Page(items=items, total=page.total, limit=limit, offset=offset)


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: str, session: SessionDep) -> ProjectDetailOut:
    project = queries.get_project(session, project_id)
    if project is None:
        raise _not_found(f"Project '{project_id}'")
    stats = queries.project_stats(session, [project])[project.id]
    pull_requests = sorted(project.pull_requests, key=lambda pr: (pr.created_at, pr.id))
    return ProjectDetailOut(
        **_summary_fields(project, stats),
        problem=project.problem,
        context=project.context,
        objectives=project.objectives,
        my_contributions=project.my_contributions,
        implementation=project.implementation,
        architecture=project.architecture,
        challenges=project.challenges,
        decisions=project.decisions,
        metrics=project.metrics,
        uncertainties=project.uncertainties,
        pull_requests=[PullRequestOut.model_validate(pr) for pr in pull_requests],
    )


# ---------- Pull requests ----------


@router.get("/pull-requests", response_model=Page[PullRequestOut])
def list_pull_requests(
    session: SessionDep,
    project_id: str | None = None,
    standalone: Annotated[
        bool | None, Query(description="true: only PRs without a project.")
    ] = None,
    status_: Annotated[list[PRStatus], Query(alias="status")] = [],  # noqa: B006
    repo: str | None = None,
    q: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[PullRequestOut]:
    items, total = queries.list_pull_requests(
        session,
        project_id=project_id,
        standalone=standalone,
        status=status_,
        repo=repo,
        q=q,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[PullRequestOut.model_validate(pr) for pr in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/pull-requests/{pr_id}", response_model=PullRequestOut)
def get_pull_request(pr_id: str, session: SessionDep) -> db.PullRequest:
    pr = queries.get_pull_request(session, pr_id)
    if pr is None:
        raise _not_found(f"Pull request '{pr_id}'")
    return pr


# ---------- Skills and categories ----------


@router.get("/skills", response_model=list[SkillOut])
def list_skills(
    session: SessionDep,
    category: Annotated[str | None, Query(description="Skill group, e.g. 'Databases'.")] = None,
) -> list[SkillOut]:
    links_by_skill = queries.skill_projects(session)
    result = []
    for skill in queries.list_skills(session, category=category):
        links = links_by_skill.get(skill.id, [])
        result.append(
            SkillOut(
                name=skill.name,
                category=skill.category,
                description=skill.description,
                aliases=skill.aliases,
                project_count=len(links),
                strongest_involvement=links[0][1] if links else None,
                projects=[
                    SkillProjectOut(id=p.id, name=p.name, involvement=inv) for p, inv in links
                ],
            )
        )
    return result


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: SessionDep) -> list[CategoryOut]:
    return [
        CategoryOut(
            name=category.name,
            description=category.description,
            project_count=len(projects),
            projects=[ProjectRefOut(id=p.id, name=p.name) for p in projects],
        )
        for category, projects in queries.list_categories(session)
    ]
