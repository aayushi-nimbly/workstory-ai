"""Import an experience JSON file into the database.

The file is treated as a full snapshot of the engineer's experience:
- records in the file are inserted or updated (matched by ID, or by name for
  skills and categories), so importing the same file twice changes nothing;
- records missing from the file are deleted;
- everything happens in one transaction, so a failed import leaves the
  previous data untouched.

Every attempt is recorded in the `imports` table, including failures.

CLI usage:
    uv run workstory-import path/to/workstory-experience.json [--force]
"""

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import models as db
from app.experience.checks import Issue
from app.experience.models import ExperienceFile
from app.experience.validate import validate_data

logger = logging.getLogger(__name__)

MAX_REPORTED_ERRORS = 20


class ImportValidationError(Exception):
    """The file is not valid JSON or does not pass validation."""

    def __init__(self, import_id: int, errors: list[Issue], warnings: list[Issue]):
        super().__init__(f"{len(errors)} validation error(s)")
        self.import_id = import_id
        self.errors = errors
        self.warnings = warnings


@dataclass
class ImportResult:
    import_id: int | None
    unchanged: bool
    counts: dict[str, int]
    warnings: list[Issue] = field(default_factory=list)


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def import_experience(session: Session, content: bytes, *, force: bool = False) -> ImportResult:
    digest = file_hash(content)

    if not force:
        last = session.scalars(
            select(db.Import)
            .where(db.Import.status == db.ImportStatus.completed)
            .order_by(db.Import.id.desc())
            .limit(1)
        ).first()
        if last is not None and last.file_hash == digest:
            logger.info("Import skipped: file identical to import #%s", last.id)
            return ImportResult(import_id=last.id, unchanged=True, counts=last.counts)

    record = db.Import(file_hash=digest, status=db.ImportStatus.running)
    session.add(record)
    session.commit()

    try:
        raw = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        error = Issue("error", "(file)", f"invalid JSON: {exc}")
        _mark_failed(session, record, [error])
        raise ImportValidationError(record.id, [error], []) from exc

    result = validate_data(raw)
    if not result.is_valid or result.data is None:
        _mark_failed(session, record, result.errors)
        raise ImportValidationError(record.id, result.errors, result.warnings)

    data = result.data
    try:
        counts = _apply(session, data)
        record.status = db.ImportStatus.completed
        record.schema_version = data.metadata.schema_version
        record.counts = counts
        record.finished_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        session.rollback()
        _mark_failed(session, record, [Issue("error", "(import)", f"{type(exc).__name__}: {exc}")])
        logger.exception("Import #%s failed", record.id)
        raise

    logger.info("Import #%s completed: %s", record.id, counts)
    return ImportResult(
        import_id=record.id, unchanged=False, counts=counts, warnings=result.warnings
    )


def _mark_failed(session: Session, record: db.Import, errors: list[Issue]) -> None:
    lines = [str(e) for e in errors[:MAX_REPORTED_ERRORS]]
    if len(errors) > MAX_REPORTED_ERRORS:
        lines.append(f"... and {len(errors) - MAX_REPORTED_ERRORS} more")
    record.status = db.ImportStatus.failed
    record.error = "\n".join(lines)
    record.finished_at = datetime.now(UTC)
    session.add(record)
    session.commit()


def _apply(session: Session, data: ExperienceFile) -> dict[str, int]:
    """Write the snapshot to the database. Caller commits or rolls back."""
    summary = data.professional_summary
    session.merge(
        db.Profile(
            id=1,
            owner_name=data.metadata.owner_name,
            summary=summary.summary,
            experience_level=summary.experience_level,
            primary_roles=summary.primary_roles,
            primary_technologies=summary.primary_technologies,
        )
    )

    categories = _sync_by_name(
        session,
        db.Category,
        {c.name: {"name": c.name, "description": c.description} for c in data.categories},
    )
    skills = _sync_by_name(
        session,
        db.Skill,
        {
            s.name: {
                "name": s.name,
                "category": s.category,
                "description": s.description,
                "aliases": s.aliases,
            }
            for s in data.skills
        },
    )

    # Links are rebuilt from scratch: simpler than diffing, and cheap at this size.
    session.execute(delete(db.ProjectSkill))
    session.execute(delete(db.ProjectCategory))

    project_ids = {p.id for p in data.projects}
    session.execute(delete(db.Project).where(db.Project.id.not_in(project_ids)))
    for project in data.projects:
        fields = project.model_dump(mode="json", exclude={"skills", "categories", "pr_ids"})
        _upsert(session, db.Project, project.id, fields)
    session.flush()

    pr_ids = {pr.id for pr in data.pull_requests}
    session.execute(delete(db.PullRequest).where(db.PullRequest.id.not_in(pr_ids)))
    for pr in data.pull_requests:
        _upsert(session, db.PullRequest, pr.id, pr.model_dump())

    for project in data.projects:
        for link in project.skills:
            session.add(
                db.ProjectSkill(
                    project_id=project.id,
                    skill_id=skills[link.name.casefold()].id,
                    involvement=link.involvement,
                    evidence=link.evidence,
                )
            )
        for name in project.categories:
            session.add(
                db.ProjectCategory(
                    project_id=project.id, category_id=categories[name.casefold()].id
                )
            )
    session.flush()

    return {
        "projects": len(data.projects),
        "pull_requests": len(data.pull_requests),
        "skills": len(data.skills),
        "categories": len(data.categories),
    }


def _upsert(session: Session, model: type, key: str, fields: dict) -> None:
    row = session.get(model, key)
    if row is None:
        session.add(model(**fields))
        return
    for name, value in fields.items():
        if getattr(row, name) != value:
            setattr(row, name, value)


def _sync_by_name[T: (db.Category, db.Skill)](
    session: Session, model: type[T], wanted: dict[str, dict]
) -> dict[str, T]:
    """Make the table match `wanted` (matched by case-insensitive name).

    Existing rows keep their IDs, so references to them stay valid.
    Returns rows keyed by lower-cased name.
    """
    existing = {row.name.casefold(): row for row in session.scalars(select(model))}
    wanted_keys = {name.casefold() for name in wanted}

    for key, row in existing.items():
        if key not in wanted_keys:
            session.delete(row)

    rows: dict[str, T] = {}
    for name, fields in wanted.items():
        key = name.casefold()
        row = existing.get(key)
        if row is None:
            row = model(**fields)
            session.add(row)
        else:
            for attr, value in fields.items():
                if getattr(row, attr) != value:
                    setattr(row, attr, value)
        rows[key] = row
    session.flush()
    return rows


def main(argv: list[str] | None = None) -> int:
    from app.db.session import get_engine

    parser = argparse.ArgumentParser(description="Import a WorkStory experience JSON file.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--force", action="store_true", help="import even if unchanged")
    args = parser.parse_args(argv)

    with Session(get_engine(), expire_on_commit=False) as session:
        try:
            result = import_experience(session, args.file.read_bytes(), force=args.force)
        except ImportValidationError as exc:
            for issue in exc.errors + exc.warnings:
                print(issue)
            print(f"\n✗ Import #{exc.import_id} failed: {len(exc.errors)} error(s).")
            return 1

    for issue in result.warnings:
        print(issue)
    if result.unchanged:
        print(f"= File unchanged since import #{result.import_id}; nothing to do.")
    else:
        print(f"✓ Import #{result.import_id} completed: {result.counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
