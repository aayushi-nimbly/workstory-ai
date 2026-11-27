"""Database tables for the experience library.

Projects and pull requests keep the stable IDs from the experience JSON as their
primary keys, which makes re-imports simple upserts. Nested project details
(challenges, decisions, metrics, ...) are stored as JSONB: they are always read
together with their project and never queried on their own.

Allowed values for enum-like columns are enforced with CHECK constraints
(easier to evolve than native PostgreSQL enums).
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.base import Base
from app.experience.models import Complexity, Confidence, Involvement, PRStatus


def _check_in(column: str, enum: type[StrEnum], name: str) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=name)


class TimestampMixin:
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Profile(TimestampMixin, Base):
    """The engineer the data belongs to. Always exactly one row (id = 1)."""

    __tablename__ = "profile"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    owner_name: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    experience_level: Mapped[str] = mapped_column(Text)
    primary_roles: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    primary_technologies: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (Index("uq_categories_name_lower", text("lower(name)"), unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (Index("uq_skills_name_lower", text("lower(name)"), unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        _check_in("complexity", Complexity, "complexity_valid"),
        _check_in("confidence", Confidence, "confidence_valid"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    problem: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    objectives: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    my_contributions: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    implementation: Mapped[str] = mapped_column(Text)
    architecture: Mapped[str | None] = mapped_column(Text)
    challenges: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    uncertainties: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    complexity: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(20))

    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="project")
    skill_links: Mapped[list["ProjectSkill"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    category_links: Mapped[list["ProjectCategory"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class PullRequest(TimestampMixin, Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        _check_in("status", PRStatus, "status_valid"),
        _check_in("confidence", Confidence, "confidence_valid"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    contribution: Mapped[str] = mapped_column(Text)
    problem: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    repo: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[date] = mapped_column(Date)
    merged_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(20))

    project: Mapped[Project | None] = relationship(back_populates="pull_requests")


class ProjectSkill(Base):
    """Which skills a project demonstrates, and how directly."""

    __tablename__ = "project_skills"
    __table_args__ = (_check_in("involvement", Involvement, "involvement_valid"),)

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    involvement: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[str] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="skill_links")
    skill: Mapped[Skill] = relationship()


class ProjectCategory(Base):
    __tablename__ = "project_categories"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    project: Mapped[Project] = relationship(back_populates="category_links")
    category: Mapped[Category] = relationship()


class ImportStatus(StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"


class Import(Base):
    """History of experience file imports."""

    __tablename__ = "imports"
    __table_args__ = (_check_in("status", ImportStatus, "status_valid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChunkType(StrEnum):
    overview = "overview"
    problem = "problem"
    contributions = "contributions"
    implementation = "implementation"
    decision = "decision"
    challenge = "challenge"
    outcomes = "outcomes"
    skills = "skills"
    pull_request = "pull_request"


EMBED_DIMENSIONS = get_settings().embed_dimensions


class Chunk(Base):
    """A self-contained piece of experience text, used for search and RAG.

    Chunks are rebuilt from projects and PRs on every import. `content_hash`
    lets unchanged chunks keep their embedding; `embedding` is NULL until the
    embedding step has run.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        _check_in("chunk_type", ChunkType, "chunk_type_valid"),
        Index("ix_chunks_search", "search", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    pr_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    chunk_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIMENSIONS))
    embed_model: Mapped[str | None] = mapped_column(Text)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Full-text search vector, maintained by PostgreSQL.
    search: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', title || ' ' || content)", persisted=True)
    )
