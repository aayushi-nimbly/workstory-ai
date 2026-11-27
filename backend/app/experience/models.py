"""Pydantic models describing the `workstory-experience.json` file.

These models are the single source of truth for the experience data format.
The exported JSON Schema (`extraction/schema.json`) is generated from them.

Field-level rules live here. Rules that span multiple records (IDs that must
exist, PR <-> project consistency, ...) live in `checks.py`.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SCHEMA_VERSION = "1.0"

# ---------- Reusable field types ----------

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Required, non-blank text."""

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=100),
]
"""Stable ID: lowercase letters, digits and hyphens, e.g. `proj-order-sync`."""


class Confidence(StrEnum):
    """How sure the extraction is that this information is accurate."""

    high = "high"
    medium = "medium"
    low = "low"


class Complexity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class Involvement(StrEnum):
    """How directly the engineer worked with a skill in a project.

    Ordered from strongest to weakest evidence of practical experience.
    """

    implemented = "implemented"  # built it themselves
    collaborated = "collaborated"  # built it together with others
    modified = "modified"  # changed an existing implementation
    used = "used"  # used or integrated something that already existed
    discussed = "discussed"  # discussed or proposed, not implemented
    mentioned = "mentioned"  # referenced only, no demonstrated usage


class PRStatus(StrEnum):
    merged = "merged"
    open = "open"
    closed = "closed"


class StrictModel(BaseModel):
    """Base model: unknown fields are rejected so typos are caught early."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------- File-level sections ----------


class Metadata(StrictModel):
    schema_version: Literal["1.0"] = Field(description="Version of this file format.")
    owner_name: Text = Field(description="Name of the engineer this experience belongs to.")
    generated_at: datetime = Field(description="When the file was generated (ISO 8601).")
    data_source: Text = Field(description="Where the data came from, e.g. 'GitHub PRs'.")
    sanitised: bool = Field(
        description="True if secrets, customer data and confidential details were removed."
    )


class ProfessionalSummary(StrictModel):
    summary: Text
    experience_level: Text = Field(description="e.g. '3-4 years', 'Mid-level'.")
    primary_roles: list[Text] = Field(default_factory=list)
    primary_technologies: list[Text] = Field(default_factory=list)


# ---------- Project building blocks ----------


class Challenge(StrictModel):
    challenge: Text
    solution: Text


class Decision(StrictModel):
    """A technical decision made during a project."""

    context: Text = Field(description="The problem or situation that required a decision.")
    decision: Text = Field(description="What was decided.")
    reasoning: Text = Field(description="Why it was decided.")
    alternatives: list[Text] = Field(default_factory=list)
    tradeoffs: Text | None = None
    pr_ids: list[Identifier] = Field(
        default_factory=list, description="PRs that support this decision."
    )


class Metric(StrictModel):
    """A measurable outcome. Only record metrics that are backed by evidence."""

    name: Text = Field(description="e.g. 'p95 API latency'.")
    before: float | None = None
    after: float | None = None
    unit: Text | None = Field(default=None, description="e.g. 'ms', '%', 'requests/s'.")
    period: Text | None = Field(default=None, description="Measurement period, if known.")
    evidence: Text = Field(description="Where this number comes from. Required.")

    @model_validator(mode="after")
    def _unit_required_with_values(self) -> "Metric":
        if (self.before is not None or self.after is not None) and self.unit is None:
            raise ValueError("'unit' is required when 'before' or 'after' is set")
        return self


class ProjectSkill(StrictModel):
    """Link between a project and a skill, with how deeply the skill was used."""

    name: Text = Field(description="Canonical skill name; must exist in the top-level 'skills'.")
    involvement: Involvement
    evidence: Text = Field(description="Short explanation of how the skill was used.")


# ---------- Main entities ----------


class Project(StrictModel):
    """A larger piece of engineering work, usually made of several related PRs."""

    id: Identifier
    name: Text
    summary: Text
    problem: Text
    context: Text | None = Field(default=None, description="Business/technical context.")
    objectives: list[Text] = Field(default_factory=list)
    my_contributions: list[Text] = Field(
        min_length=1, description="What this engineer personally did."
    )
    implementation: Text
    architecture: Text | None = None
    challenges: list[Challenge] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    categories: list[Text] = Field(min_length=1)
    skills: list[ProjectSkill] = Field(default_factory=list)
    pr_ids: list[Identifier] = Field(default_factory=list)
    complexity: Complexity
    complexity_reason: Text | None = Field(
        default=None,
        description="One sentence: the specific challenge that makes it complex (or not).",
    )
    confidence: Confidence
    uncertainties: list[Text] = Field(
        default_factory=list,
        description="Ambiguous or unverified points flagged during extraction.",
    )


class PullRequest(StrictModel):
    id: Identifier
    project_id: Identifier | None = Field(
        default=None, description="Project this PR belongs to, if any."
    )
    title: Text
    summary: Text = Field(description="Sanitised description of the PR.")
    contribution: Text = Field(description="What this engineer did in the PR.")
    problem: Text | None = None
    technologies: list[Text] = Field(default_factory=list)
    repo: Text | None = None
    url: Text | None = None
    created_at: date
    merged_at: date | None = None
    status: PRStatus
    confidence: Confidence

    @model_validator(mode="after")
    def _dates_consistent(self) -> "PullRequest":
        if self.status == PRStatus.merged and self.merged_at is None:
            raise ValueError("'merged_at' is required when status is 'merged'")
        if self.status != PRStatus.merged and self.merged_at is not None:
            raise ValueError("'merged_at' must be empty unless status is 'merged'")
        if self.merged_at is not None and self.merged_at < self.created_at:
            raise ValueError("'merged_at' cannot be earlier than 'created_at'")
        return self


class Skill(StrictModel):
    name: Text = Field(description="Canonical name, e.g. 'PostgreSQL'.")
    category: Text = Field(description="Skill group, e.g. 'Databases', 'Languages'.")
    description: Text | None = None
    aliases: list[Text] = Field(
        default_factory=list, description="Other spellings, e.g. ['Postgres', 'psql']."
    )


class Category(StrictModel):
    name: Text = Field(description="Engineering category, e.g. 'Backend Engineering'.")
    description: Text | None = None


# ---------- Root ----------


class ExperienceFile(StrictModel):
    """The root of `workstory-experience.json`."""

    model_config = ConfigDict(title="WorkStory Experience File")

    metadata: Metadata
    professional_summary: ProfessionalSummary
    projects: list[Project] = Field(default_factory=list)
    pull_requests: list[PullRequest] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    categories: list[Category] = Field(default_factory=list)
