import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import models as db
from app.services import importer
from app.services.importer import ImportValidationError, import_experience

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "sample-experience.json"


@pytest.fixture
def sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def encode(data: dict) -> bytes:
    return json.dumps(data).encode()


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def table_counts(session) -> dict[str, int]:
    return {
        "projects": count(session, db.Project),
        "pull_requests": count(session, db.PullRequest),
        "skills": count(session, db.Skill),
        "categories": count(session, db.Category),
        "project_skills": count(session, db.ProjectSkill),
        "project_categories": count(session, db.ProjectCategory),
    }


def expected_counts(data: dict) -> dict[str, int]:
    return {
        "projects": len(data["projects"]),
        "pull_requests": len(data["pull_requests"]),
        "skills": len(data["skills"]),
        "categories": len(data["categories"]),
        "project_skills": sum(len(p["skills"]) for p in data["projects"]),
        "project_categories": sum(len(p["categories"]) for p in data["projects"]),
    }


# ---------- Successful imports ----------


def test_import_sample(db_session, sample):
    result = import_experience(db_session, encode(sample))

    assert not result.unchanged
    assert result.counts == {
        "projects": 6,
        "pull_requests": 26,
        "skills": 22,
        "categories": 11,
        "chunks": 77,
    }
    assert table_counts(db_session) == expected_counts(sample)

    profile = db_session.get(db.Profile, 1)
    assert profile.owner_name == "Alex Rivera"

    project = db_session.get(db.Project, "proj-webhook-delivery")
    assert len(project.pull_requests) == 4
    assert project.decisions[0]["alternatives"] == ["Redis with Celery", "Kafka"]
    kafka = next(link for link in project.skill_links if link.skill.name == "Kafka")
    assert kafka.involvement == "discussed"

    standalone = db_session.get(db.PullRequest, "pr-shipments-api-380")
    assert standalone.project_id is None and standalone.status == "open"

    record = db_session.get(db.Import, result.import_id)
    assert record.status == "completed" and record.finished_at is not None


def test_same_file_twice_is_skipped(db_session, sample):
    first = import_experience(db_session, encode(sample))
    second = import_experience(db_session, encode(sample))

    assert second.unchanged
    assert second.import_id == first.import_id
    assert count(db_session, db.Import) == 1
    assert table_counts(db_session) == expected_counts(sample)


def test_forced_reimport_creates_no_duplicates_and_keeps_ids(db_session, sample):
    import_experience(db_session, encode(sample))
    skill_ids = dict(db_session.execute(select(db.Skill.name, db.Skill.id)).all())

    result = import_experience(db_session, encode(sample), force=True)

    assert not result.unchanged
    assert table_counts(db_session) == expected_counts(sample)
    assert dict(db_session.execute(select(db.Skill.name, db.Skill.id)).all()) == skill_ids


def test_reimport_applies_updates_and_deletions(db_session, sample):
    import_experience(db_session, encode(sample))

    # Remove one project and its PRs, edit another project, drop an unused skill.
    removed = "proj-support-docs-assistant"
    sample["projects"] = [p for p in sample["projects"] if p["id"] != removed]
    sample["pull_requests"] = [
        pr for pr in sample["pull_requests"] if pr.get("project_id") != removed
    ]
    sample["projects"][0]["name"] = "Renamed migration project"
    sample["projects"][0]["skills"] = [
        s for s in sample["projects"][0]["skills"] if s["name"] != "Alembic"
    ]
    sample["skills"] = [s for s in sample["skills"] if s["name"] != "Alembic"]

    import_experience(db_session, encode(sample))
    db_session.expire_all()

    assert db_session.get(db.Project, removed) is None
    assert db_session.get(db.PullRequest, "pr-support-assistant-poc-7") is None
    assert db_session.get(db.Project, sample["projects"][0]["id"]).name == (
        "Renamed migration project"
    )
    assert db_session.scalar(select(db.Skill).where(db.Skill.name == "Alembic")) is None
    assert table_counts(db_session) == expected_counts(sample)


# ---------- Failed imports ----------


def test_invalid_file_is_rejected_and_recorded(db_session, sample):
    import_experience(db_session, encode(sample))
    before = table_counts(db_session)

    sample["projects"][0]["categories"] = ["Not a category"]
    with pytest.raises(ImportValidationError) as exc_info:
        import_experience(db_session, encode(sample))

    assert "unknown category" in exc_info.value.errors[0].message
    assert table_counts(db_session) == before
    record = db_session.get(db.Import, exc_info.value.import_id)
    assert record.status == "failed"
    assert "unknown category" in record.error


def test_invalid_json_is_rejected(db_session):
    with pytest.raises(ImportValidationError) as exc_info:
        import_experience(db_session, b"{ not json")
    assert "invalid JSON" in exc_info.value.errors[0].message


def test_failure_while_writing_rolls_back_everything(db_session, sample, monkeypatch):
    import_experience(db_session, encode(sample))
    before = table_counts(db_session)

    original_apply = importer._apply

    def broken_apply(session, data):
        original_apply(session, data)  # writes everything...
        raise RuntimeError("disk full")  # ...then fails before commit

    sample["projects"] = sample["projects"][:1]
    sample["pull_requests"] = [
        pr
        for pr in sample["pull_requests"]
        if pr.get("project_id") in (None, sample["projects"][0]["id"])
    ]
    monkeypatch.setattr(importer, "_apply", broken_apply)
    with pytest.raises(RuntimeError):
        import_experience(db_session, encode(sample))

    assert table_counts(db_session) == before
    last = db_session.scalars(select(db.Import).order_by(db.Import.id.desc())).first()
    assert last.status == "failed" and "disk full" in last.error
