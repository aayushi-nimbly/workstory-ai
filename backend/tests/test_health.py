import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.llm import ProviderStatus, get_llm
from app.main import create_app
from tests.fakes import FakeLLM


@pytest.fixture
def make_client():
    def _make(session, llm=None):
        app = create_app()
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_llm] = lambda: llm or FakeLLM()
        return TestClient(app)

    return _make


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _FakeSession:
    """Minimal stand-in for a Session, to simulate database states."""

    def __init__(self, has_vector=True, fail=False):
        self.has_vector = has_vector
        self.fail = fail

    def execute(self, _statement):
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        return _FakeResult(self.has_vector)


def test_health_ok_with_real_database(make_client, db_session):
    response = make_client(db_session).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "pgvector": "ok",
        "llm": "ok",
        "missing_models": [],
    }


def test_health_database_unavailable(make_client):
    response = make_client(_FakeSession(fail=True)).get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
    assert body["pgvector"] == "unknown"


def test_health_pgvector_missing(make_client):
    response = make_client(_FakeSession(has_vector=False)).get("/health")
    assert response.status_code == 503
    assert response.json()["pgvector"] == "missing"


def test_health_llm_unavailable_is_degraded_but_200(make_client):
    llm = FakeLLM(status=ProviderStatus(reachable=False))
    response = make_client(_FakeSession(), llm).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["llm"] == "unavailable"


def test_health_reports_missing_models(make_client):
    llm = FakeLLM(status=ProviderStatus(reachable=True, missing_models=["llama3.1:8b"]))
    body = make_client(_FakeSession(), llm).get("/health").json()
    assert body["llm"] == "model_missing"
    assert body["missing_models"] == ["llama3.1:8b"]
