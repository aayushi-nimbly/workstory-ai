import pytest

from app.services.importer import import_experience
from tests.test_importer import SAMPLE_PATH


@pytest.fixture
def client(make_api_client):
    return make_api_client()


@pytest.fixture
def imported(db_session):
    import_experience(db_session, SAMPLE_PATH.read_bytes())


def project_ids(client, **params) -> list[str]:
    response = client.get("/projects", params=params)
    assert response.status_code == 200, response.text
    return [p["id"] for p in response.json()["items"]]


# ---------- Profile ----------


def test_profile_missing_before_import(client):
    assert client.get("/profile").status_code == 404


def test_profile(client, imported):
    body = client.get("/profile").json()
    assert body["owner_name"] == "Alex Rivera"
    assert "Python" in body["primary_technologies"]


# ---------- Project list ----------


def test_list_projects_default_sort_is_most_recent_first(client, imported):
    body = client.get("/projects").json()
    assert body["total"] == 6
    first = body["items"][0]
    assert first["id"] == "proj-support-docs-assistant"
    assert first["pr_count"] == 3
    assert first["started_on"] == "2026-03-02"
    assert first["categories"] == ["AI & GenAI"]


def test_project_summary_lists_strongest_skills_first(client, imported):
    item = next(
        p for p in client.get("/projects").json()["items"] if p["id"] == "proj-webhook-delivery"
    )
    involvements = [s["involvement"] for s in item["skills"]]
    assert involvements[0] == "implemented"
    assert involvements[-1] == "discussed"


def test_sort_by_complexity_and_name(client, imported):
    by_complexity = project_ids(client, sort="complexity")
    assert set(by_complexity[:2]) == {
        "proj-tracking-postgres-migration",
        "proj-webhook-delivery",
    }
    names = [p["name"] for p in client.get("/projects", params={"sort": "name"}).json()["items"]]
    assert names == sorted(names)


def test_filter_by_skill_alias_case_insensitive(client, imported):
    assert set(project_ids(client, skill="postgres")) == {
        "proj-tracking-postgres-migration",
        "proj-webhook-delivery",
        "proj-shipment-search-performance",
    }


def test_multiple_skills_must_all_match(client, imported):
    assert set(project_ids(client, skill=["PostgreSQL", "FastAPI"])) == {
        "proj-webhook-delivery",
        "proj-shipment-search-performance",
    }


def test_involvement_filter_separates_real_experience(client, imported):
    assert project_ids(client, skill="Kafka") == ["proj-webhook-delivery"]
    assert project_ids(client, skill="Kafka", involvement="implemented") == []
    # Python was only "modified" in the logging project, so it is excluded here.
    assert set(project_ids(client, skill="Python", involvement="implemented")) == {
        "proj-tracking-postgres-migration",
        "proj-webhook-delivery",
        "proj-support-docs-assistant",
    }


def test_involvement_without_skill_matches_any_skill(client, imported):
    # Every sample project has at least one implemented/collaborated skill except logging,
    # where all skills were modified or used.
    ids = project_ids(client, involvement=["implemented", "collaborated"])
    assert len(ids) == 5
    assert "proj-structured-logging-tracing" not in ids


def test_unknown_skill_returns_empty(client, imported):
    body = client.get("/projects", params={"skill": "Haskell"}).json()
    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_filter_by_category_and_complexity(client, imported):
    assert project_ids(client, category="ai & genai") == ["proj-support-docs-assistant"]
    assert set(project_ids(client, complexity="high")) == {
        "proj-tracking-postgres-migration",
        "proj-webhook-delivery",
    }
    assert project_ids(client, confidence="low") == ["proj-support-docs-assistant"]


def test_text_search(client, imported):
    assert project_ids(client, q="backoff") == ["proj-webhook-delivery"]
    assert project_ids(client, q="SKIP LOCKED") == ["proj-webhook-delivery"]
    # "%" is matched literally (only the project mentioning "10% sampling"), not as a wildcard.
    assert project_ids(client, q="%") == ["proj-structured-logging-tracing"]


def test_pagination(client, imported):
    all_ids = project_ids(client, sort="name")
    body = client.get("/projects", params={"sort": "name", "limit": 2, "offset": 2}).json()
    assert body["total"] == 6
    assert [p["id"] for p in body["items"]] == all_ids[2:4]


def test_invalid_filter_value_rejected(client, imported):
    assert client.get("/projects", params={"complexity": "extreme"}).status_code == 422
    assert client.get("/projects", params={"limit": 0}).status_code == 422


# ---------- Project detail ----------


def test_project_detail(client, imported):
    body = client.get("/projects/proj-webhook-delivery").json()
    assert body["name"] == "Reliable webhook delivery with retries"
    assert [pr["id"] for pr in body["pull_requests"]] == [
        "pr-notifications-service-88",
        "pr-notifications-service-93",
        "pr-notifications-service-97",
        "pr-notifications-service-104",
    ]
    assert body["decisions"][0]["alternatives"] == ["Redis with Celery", "Kafka"]
    assert body["metrics"][0]["after"] == 0.3
    assert body["pr_count"] == 4


def test_project_detail_shows_uncertainties(client, imported):
    body = client.get("/projects/proj-support-docs-assistant").json()
    assert body["confidence"] == "low"
    assert len(body["uncertainties"]) == 2


def test_unknown_project_404(client, imported):
    assert client.get("/projects/proj-nope").status_code == 404


# ---------- Pull requests ----------


def test_list_pull_requests_filters(client, imported):
    def ids(**params):
        return [pr["id"] for pr in client.get("/pull-requests", params=params).json()["items"]]

    assert client.get("/pull-requests").json()["total"] == 26
    assert len(ids(standalone="true")) == 4
    assert ids(status="open") == ["pr-shipments-api-380"]
    assert ids(status="closed") == ["pr-support-assistant-poc-15"]
    assert len(ids(project_id="proj-webhook-delivery")) == 4
    assert len(ids(repo="Carrier-Gateway")) == 4
    assert ids(q="pydantic") == ["pr-shipments-api-365"]


def test_pull_request_detail(client, imported):
    body = client.get("/pull-requests/pr-shipments-api-322").json()
    assert body["project_id"] == "proj-tracking-postgres-migration"
    assert client.get("/pull-requests/pr-nope").status_code == 404


# ---------- Skills and categories ----------


def test_skills(client, imported):
    skills = {s["name"]: s for s in client.get("/skills").json()}
    assert len(skills) == 22
    assert skills["Kafka"]["strongest_involvement"] == "discussed"
    assert skills["Python"]["project_count"] == 4
    assert skills["Python"]["projects"][0]["involvement"] == "implemented"
    assert skills["PostgreSQL"]["aliases"] == ["Postgres", "psql"]


def test_skills_by_category(client, imported):
    names = [s["name"] for s in client.get("/skills", params={"category": "ai/genai"}).json()]
    assert names == sorted(
        ["LLMs", "RAG", "Embeddings", "Prompt Engineering", "Cross-encoder Reranking"]
    )


def test_categories(client, imported):
    categories = {c["name"]: c for c in client.get("/categories").json()}
    assert len(categories) == 11
    assert categories["AI & GenAI"]["project_count"] == 1
    assert categories["System Design"]["project_count"] == 2


def test_complexity_reason_is_returned(client, db_session, imported):
    from app.db.models import Project

    db_session.get(Project, "proj-webhook-delivery").complexity_reason = "Failure handling."
    db_session.flush()
    body = client.get("/projects/proj-webhook-delivery").json()
    assert body["complexity_reason"] == "Failure handling."
    listed = client.get("/projects").json()["items"]
    assert all("complexity_reason" in p for p in listed)
