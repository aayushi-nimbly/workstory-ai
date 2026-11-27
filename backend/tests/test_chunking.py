import json
from collections import Counter

import pytest

from app.db.models import ChunkType
from app.experience.models import ExperienceFile
from app.services.chunking import build_chunks
from tests.test_importer import SAMPLE_PATH


@pytest.fixture
def sample_data() -> ExperienceFile:
    return ExperienceFile.model_validate(json.loads(SAMPLE_PATH.read_text()))


def test_chunk_counts_follow_structure(sample_data):
    chunks = build_chunks(sample_data)
    counts = Counter(c.chunk_type for c in chunks)
    projects = sample_data.projects

    assert counts[ChunkType.overview] == len(projects)
    assert counts[ChunkType.decision] == sum(len(p.decisions) for p in projects)
    assert counts[ChunkType.challenge] == sum(len(p.challenges) for p in projects)
    assert counts[ChunkType.outcomes] == sum(1 for p in projects if p.metrics)
    assert counts[ChunkType.pull_request] == len(sample_data.pull_requests)
    assert len(chunks) == 77


def test_chunk_ids_are_unique_and_stable(sample_data):
    first = [c.id for c in build_chunks(sample_data)]
    second = [c.id for c in build_chunks(sample_data)]
    assert first == second
    assert len(set(first)) == len(first)
    assert "proj-webhook-delivery:decision-0" in first
    assert "pr:pr-shipments-api-380" in first


def test_chunks_are_self_contained(sample_data):
    by_id = {c.id: c for c in build_chunks(sample_data)}
    decision = by_id["proj-webhook-delivery:decision-0"]
    assert decision.content.startswith("Project: Reliable webhook delivery with retries")
    assert "Alternatives considered: Redis with Celery, Kafka" in decision.content
    assert decision.pr_ids == ["pr-notifications-service-88"]
    assert decision.project_id == "proj-webhook-delivery"
    assert "Reliability & Observability" in decision.categories


def test_skills_chunk_keeps_involvement(sample_data):
    skills = {c.id: c for c in build_chunks(sample_data)}["proj-webhook-delivery:skills"]
    assert "- Kafka (discussed):" in skills.content
    assert skills.skills[0] != "Kafka"  # strongest involvement first


def test_low_confidence_project_flags_uncertainty(sample_data):
    overview = {c.id: c for c in build_chunks(sample_data)}["proj-support-docs-assistant:overview"]
    assert "Confidence: low" in overview.content
    assert "Unverified:" in overview.content


def test_standalone_pr_chunk(sample_data):
    chunk = {c.id: c for c in build_chunks(sample_data)}["pr:pr-shipments-api-380"]
    assert chunk.project_id is None
    assert "Not part of a larger project." in chunk.content
    assert "Status: open" in chunk.content


def test_content_hash_changes_with_text(sample_data):
    before = {c.id: c.content_hash for c in build_chunks(sample_data)}
    sample_data.projects[0].decisions[0].reasoning = "Different reasoning."
    after = {c.id: c.content_hash for c in build_chunks(sample_data)}
    changed = [cid for cid in before if before[cid] != after[cid]]
    assert changed == [f"{sample_data.projects[0].id}:decision-0"]
