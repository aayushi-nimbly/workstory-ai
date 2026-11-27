import json

import pytest
from sqlalchemy import func, select

from app.db.models import Chunk
from app.llm import LLMUnavailableError
from app.services.embedding import embed_pending, embedding_status
from app.services.importer import import_experience
from tests.fakes import FakeLLM
from tests.test_importer import SAMPLE_PATH


@pytest.fixture
def sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text())


def encode(data: dict) -> bytes:
    return json.dumps(data).encode()


class FailingLLM(FakeLLM):
    def __init__(self, fail_after_calls: int):
        super().__init__()
        self.calls = 0
        self.fail_after_calls = fail_after_calls

    def embed(self, texts, *, kind):
        self.calls += 1
        if self.calls > self.fail_after_calls:
            raise LLMUnavailableError("Ollama is not reachable")
        return super().embed(texts, kind=kind)


def test_import_creates_chunks_without_embeddings(db_session, sample):
    import_experience(db_session, encode(sample))
    status = embedding_status(db_session, FakeLLM.embed_model)
    assert status.total == 77
    assert status.pending == 77


def test_embed_pending_fills_all_chunks(db_session, sample):
    import_experience(db_session, encode(sample))
    llm = FakeLLM()

    assert embed_pending(db_session, llm) == 77
    assert embedding_status(db_session, llm.embed_model).pending == 0
    assert all(kind == "document" for kind, _ in llm.embedded)
    chunk = db_session.get(Chunk, "proj-webhook-delivery:overview")
    assert len(chunk.embedding) == 768
    assert chunk.embed_model == "fake-embed"


def test_reimport_only_reembeds_changed_chunks(db_session, sample):
    import_experience(db_session, encode(sample))
    embed_pending(db_session, FakeLLM())

    sample["projects"][1]["decisions"][0]["reasoning"] = "Updated reasoning."
    import_experience(db_session, encode(sample))
    llm = FakeLLM()

    assert embed_pending(db_session, llm) == 1
    assert "Updated reasoning." in llm.embedded[0][1]


def test_removed_project_removes_its_chunks(db_session, sample):
    import_experience(db_session, encode(sample))
    removed = "proj-support-docs-assistant"
    sample["projects"] = [p for p in sample["projects"] if p["id"] != removed]
    sample["pull_requests"] = [
        pr for pr in sample["pull_requests"] if pr.get("project_id") != removed
    ]

    import_experience(db_session, encode(sample))

    left = db_session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.project_id == removed)
    )
    assert left == 0
    assert db_session.get(Chunk, "pr:pr-support-assistant-poc-7") is None


def test_model_change_marks_chunks_pending(db_session, sample):
    import_experience(db_session, encode(sample))
    embed_pending(db_session, FakeLLM())

    class OtherModel(FakeLLM):
        embed_model = "other-embed"

    assert embedding_status(db_session, "other-embed").pending == 77
    assert embed_pending(db_session, OtherModel()) == 77


def test_provider_failure_keeps_finished_batches(db_session, sample):
    import_experience(db_session, encode(sample))

    with pytest.raises(LLMUnavailableError):
        embed_pending(db_session, FailingLLM(fail_after_calls=1), batch_size=32)

    status = embedding_status(db_session, FakeLLM.embed_model)
    assert status.embedded == 32  # first batch was committed
    assert embed_pending(db_session, FakeLLM()) == 45  # resumes where it stopped


def test_upload_schedules_background_embedding(make_api_client):
    client = make_api_client()
    response = client.post(
        "/imports",
        files={"file": ("e.json", SAMPLE_PATH.read_bytes(), "application/json")},
    )
    assert response.status_code == 201
    assert response.json()["embedding_scheduled"] is True

    # TestClient runs background tasks before returning, so embedding is done.
    status = client.get("/imports/embedding").json()
    assert status == {"model": "fake-embed", "total": 77, "embedded": 77, "pending": 0}


def test_embedding_paused_when_model_unavailable_then_retried(make_api_client):
    down = FailingLLM(fail_after_calls=0)
    client = make_api_client(down)
    response = client.post(
        "/imports",
        files={"file": ("e.json", SAMPLE_PATH.read_bytes(), "application/json")},
    )
    assert response.status_code == 201  # import itself succeeds
    assert client.get("/imports/embedding").json()["pending"] == 77

    retry = make_api_client().post("/imports/embedding")
    assert retry.status_code == 202
    assert make_api_client().get("/imports/embedding").json()["pending"] == 0
