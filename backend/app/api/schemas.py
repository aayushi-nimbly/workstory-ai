"""Response models for the experience library API."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ProfileOut(ORMModel):
    owner_name: str
    summary: str
    experience_level: str
    primary_roles: list[str]
    primary_technologies: list[str]


# ---------- Projects ----------


class ProjectSkillOut(BaseModel):
    name: str
    category: str
    involvement: str
    evidence: str


class ProjectPRStats(BaseModel):
    pr_count: int
    started_on: date | None
    last_activity_on: date | None


class ProjectSummaryOut(ProjectPRStats):
    id: str
    name: str
    summary: str
    complexity: str
    complexity_reason: str | None
    confidence: str
    categories: list[str]
    skills: list[ProjectSkillOut]


class PullRequestOut(ORMModel):
    id: str
    project_id: str | None
    title: str
    summary: str
    contribution: str
    problem: str | None
    technologies: list[str]
    repo: str | None
    url: str | None
    created_at: date
    merged_at: date | None
    status: str
    confidence: str


class ProjectDetailOut(ProjectSummaryOut):
    problem: str
    context: str | None
    objectives: list[str]
    my_contributions: list[str]
    implementation: str
    architecture: str | None
    challenges: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    uncertainties: list[str]
    pull_requests: list[PullRequestOut]


# ---------- Skills and categories ----------


class ProjectRefOut(BaseModel):
    id: str
    name: str


class SkillProjectOut(ProjectRefOut):
    involvement: str


class SkillOut(BaseModel):
    name: str
    category: str
    description: str | None
    aliases: list[str]
    project_count: int
    strongest_involvement: str | None
    projects: list[SkillProjectOut]


class CategoryOut(BaseModel):
    name: str
    description: str | None
    project_count: int
    projects: list[ProjectRefOut]
