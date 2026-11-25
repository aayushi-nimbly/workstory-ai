import copy
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import get_settings

_VALID = {
    "metadata": {
        "schema_version": "1.0",
        "owner_name": "Test Engineer",
        "generated_at": "2026-11-01T10:00:00Z",
        "data_source": "GitHub PRs",
        "sanitised": True,
    },
    "professional_summary": {
        "summary": "Backend engineer.",
        "experience_level": "3 years",
        "primary_roles": ["Backend Engineer"],
        "primary_technologies": ["Python"],
    },
    "projects": [
        {
            "id": "proj-cache",
            "name": "Response caching",
            "summary": "Added caching to a slow endpoint.",
            "problem": "Endpoint was slow under load.",
            "my_contributions": ["Designed and implemented the cache layer."],
            "implementation": "Read-through cache with TTL invalidation.",
            "decisions": [
                {
                    "context": "Needed a cache store.",
                    "decision": "Use Redis.",
                    "reasoning": "Already in the stack.",
                    "pr_ids": ["pr-1"],
                }
            ],
            "metrics": [
                {
                    "name": "p95 latency",
                    "before": 800,
                    "after": 120,
                    "unit": "ms",
                    "evidence": "Load test results in PR description.",
                }
            ],
            "categories": ["Performance Optimisation"],
            "skills": [
                {"name": "Redis", "involvement": "implemented", "evidence": "Built cache layer."}
            ],
            "pr_ids": ["pr-1", "pr-2"],
            "complexity": "medium",
            "confidence": "high",
        }
    ],
    "pull_requests": [
        {
            "id": "pr-1",
            "project_id": "proj-cache",
            "title": "Add Redis cache",
            "summary": "Adds read-through cache.",
            "contribution": "Wrote the cache module.",
            "created_at": "2026-01-01",
            "merged_at": "2026-01-03",
            "status": "merged",
            "confidence": "high",
        },
        {
            "id": "pr-2",
            "project_id": "proj-cache",
            "title": "Cache invalidation",
            "summary": "Invalidates cache on writes.",
            "contribution": "Added invalidation hooks.",
            "created_at": "2026-01-05",
            "merged_at": "2026-01-06",
            "status": "merged",
            "confidence": "medium",
        },
    ],
    "skills": [{"name": "Redis", "category": "Databases", "aliases": ["redis-py"]}],
    "categories": [{"name": "Performance Optimisation"}],
}


@pytest.fixture
def valid_data() -> dict:
    """A small, fully valid experience file. Tests mutate their own copy."""
    return copy.deepcopy(_VALID)


# ---------- Database fixtures ----------

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def test_engine():
    """Engine for the separate test database, migrated to the latest version.

    Tests using it are skipped when the database is not running
    (start it with `docker compose up -d` from the repo root).
    """
    url = get_settings().test_database_url
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("test database not reachable; run `docker compose up -d`")

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """A session whose changes are rolled back after each test."""
    with test_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()


@pytest.fixture(scope="session")
def alembic_config(test_engine):
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", test_engine.url.render_as_string(hide_password=False))
    return cfg
