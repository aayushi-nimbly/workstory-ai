import json

import pytest
from fastapi.testclient import TestClient

from app.api import imports as imports_api
from app.db.session import get_db
from app.main import create_app
from tests.test_importer import SAMPLE_PATH


@pytest.fixture
def client(db_session):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def upload(client, content: bytes, **params):
    files = {"file": ("experience.json", content, "application/json")}
    return client.post("/imports", files=files, params=params)


def test_upload_sample_then_unchanged(client):
    content = SAMPLE_PATH.read_bytes()

    first = upload(client, content)
    assert first.status_code == 201
    assert first.json()["counts"]["projects"] == 6
    assert first.json()["unchanged"] is False

    second = upload(client, content)
    assert second.status_code == 200
    assert second.json()["unchanged"] is True

    forced = upload(client, content, force="true")
    assert forced.status_code == 201


def test_invalid_upload_returns_errors(client):
    data = json.loads(SAMPLE_PATH.read_text())
    data["pull_requests"][0]["project_id"] = "proj-missing"

    response = upload(client, json.dumps(data).encode())

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("unknown project 'proj-missing'" in e["message"] for e in detail["errors"])


def test_too_large_upload_rejected(client, monkeypatch):
    monkeypatch.setattr(imports_api, "MAX_UPLOAD_BYTES", 10)
    response = upload(client, b'{"metadata": {}}')
    assert response.status_code == 413


def test_import_history(client):
    upload(client, SAMPLE_PATH.read_bytes())
    upload(client, b"not json")

    history = client.get("/imports").json()

    assert [h["status"] for h in history] == ["failed", "completed"]
    assert history[1]["counts"]["pull_requests"] == 26
    assert "invalid JSON" in history[0]["error"]
