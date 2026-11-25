from datetime import date

import pytest
from alembic import command
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Category,
    Profile,
    Project,
    ProjectCategory,
    ProjectSkill,
    PullRequest,
    Skill,
)


def make_project(**overrides) -> Project:
    fields = dict(
        id="proj-a",
        name="Project A",
        summary="Summary",
        problem="Problem",
        implementation="Implementation",
        my_contributions=["Did the work"],
        decisions=[{"decision": "Use PostgreSQL", "pr_ids": ["pr-1"]}],
        complexity="high",
        confidence="medium",
    )
    return Project(**(fields | overrides))


def make_pr(**overrides) -> PullRequest:
    fields = dict(
        id="pr-1",
        title="Title",
        summary="Summary",
        contribution="Contribution",
        created_at=date(2026, 1, 1),
        merged_at=date(2026, 1, 2),
        status="merged",
        confidence="high",
    )
    return PullRequest(**(fields | overrides))


# ---------- Migrations ----------


def test_migrations_match_models(alembic_config):
    """Fails if a model changed without a matching migration."""
    command.check(alembic_config)


def test_migrations_downgrade_and_upgrade(alembic_config, test_engine):
    command.downgrade(alembic_config, "0001")
    assert "projects" not in inspect(test_engine).get_table_names()
    command.upgrade(alembic_config, "head")
    assert {"projects", "pull_requests", "skills", "categories", "imports"} <= set(
        inspect(test_engine).get_table_names()
    )


# ---------- Relationships ----------


def test_project_with_prs_skills_and_categories(db_session):
    project = make_project()
    skill = Skill(name="PostgreSQL", category="Databases", aliases=["Postgres"])
    category = Category(name="Database Design & Migration")
    project.pull_requests.append(make_pr())
    project.skill_links.append(
        ProjectSkill(skill=skill, involvement="implemented", evidence="Designed schema")
    )
    project.category_links.append(ProjectCategory(category=category))
    db_session.add(project)
    db_session.flush()
    db_session.expire_all()

    loaded = db_session.get(Project, "proj-a")
    assert [pr.id for pr in loaded.pull_requests] == ["pr-1"]
    assert loaded.skill_links[0].skill.aliases == ["Postgres"]
    assert loaded.category_links[0].category.name == "Database Design & Migration"
    assert loaded.decisions[0]["decision"] == "Use PostgreSQL"
    assert loaded.inserted_at is not None


def test_deleting_project_keeps_prs_but_removes_links(db_session):
    project = make_project()
    skill = Skill(name="Redis", category="Databases")
    project.pull_requests.append(make_pr())
    project.skill_links.append(ProjectSkill(skill=skill, involvement="used", evidence="Cache"))
    db_session.add(project)
    db_session.flush()

    db_session.delete(project)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(PullRequest, "pr-1").project_id is None
    assert db_session.scalars(select(ProjectSkill)).all() == []
    assert db_session.scalars(select(Skill)).one().name == "Redis"


# ---------- Constraints ----------


@pytest.mark.parametrize(
    "obj",
    [
        make_project(complexity="extreme"),
        make_project(confidence="certain"),
        make_pr(status="draft"),
    ],
    ids=["complexity", "confidence", "pr-status"],
)
def test_invalid_enum_values_rejected(db_session, obj):
    db_session.add(obj)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_invalid_involvement_rejected(db_session):
    project = make_project()
    project.skill_links.append(
        ProjectSkill(
            skill=Skill(name="Go", category="Languages"), involvement="expert", evidence="x"
        )
    )
    db_session.add(project)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_skill_names_unique_ignoring_case(db_session):
    db_session.add_all(
        [Skill(name="PostgreSQL", category="Databases"), Skill(name="postgresql", category="X")]
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_category_names_unique_ignoring_case(db_session):
    db_session.add_all([Category(name="Backend"), Category(name="BACKEND")])
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_profile_allows_only_one_row(db_session):
    db_session.add(Profile(id=2, owner_name="A", summary="S", experience_level="3 years"))
    with pytest.raises(IntegrityError):
        db_session.flush()
