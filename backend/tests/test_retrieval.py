import pytest

from app.db.models import ChunkType
from app.llm import LLMUnavailableError
from app.services.embedding import embed_pending
from app.services.importer import import_experience
from app.services.retrieval import RRF_K, SearchFilters, SearchMode, search
from tests.fakes import FakeLLM
from tests.test_importer import SAMPLE_PATH


class DownLLM(FakeLLM):
    def embed(self, texts, *, kind):
        raise LLMUnavailableError("Ollama is not reachable")


@pytest.fixture
def indexed(db_session, fake_llm):
    import_experience(db_session, SAMPLE_PATH.read_bytes())
    embed_pending(db_session, fake_llm)
    return db_session


def ids(result) -> list[str]:
    return [h.chunk.id for h in result.hits]


# ---------- Keyword ----------


def test_keyword_search_finds_exact_terms(indexed, fake_llm):
    result = search(indexed, fake_llm, "jitter backoff", mode=SearchMode.keyword)
    assert result.hits[0].chunk.project_id == "proj-webhook-delivery"
    assert all(h.keyword_rank for h in result.hits)
    assert all(h.vector_rank is None for h in result.hits)


def test_keyword_search_matches_any_word(indexed, fake_llm):
    # Not every word appears in one chunk, but OR-matching still finds results.
    result = search(indexed, fake_llm, "Have I implemented retry mechanisms?", mode="keyword")
    assert result.hits


def test_keyword_search_stop_words_only(indexed, fake_llm):
    assert search(indexed, fake_llm, "have I", mode=SearchMode.keyword).hits == []


def test_keyword_search_no_match(indexed, fake_llm):
    assert search(indexed, fake_llm, "quantum blockchain", mode=SearchMode.keyword).hits == []


# ---------- Vector ----------


def test_vector_search_ranks_by_similarity(indexed, fake_llm):
    result = search(indexed, fake_llm, "exponential backoff jitter dead-letter", mode="vector")
    assert result.hits[0].chunk.project_id == "proj-webhook-delivery"
    scores = [h.vector_score for h in result.hits]
    assert scores == sorted(scores, reverse=True)


def test_vector_search_ignores_other_models(indexed):
    class OtherModel(FakeLLM):
        embed_model = "other-embed"

    assert search(indexed, OtherModel(), "backoff", mode=SearchMode.vector).hits == []


# ---------- Hybrid ----------


def test_hybrid_uses_reciprocal_rank_fusion(indexed, fake_llm):
    result = search(indexed, fake_llm, "Kafka webhook queue", mode=SearchMode.hybrid, limit=20)
    for h in result.hits:
        expected = sum(1 / (RRF_K + r) for r in (h.vector_rank, h.keyword_rank) if r)
        assert h.score == pytest.approx(expected)
    scores = [h.score for h in result.hits]
    assert scores == sorted(scores, reverse=True)
    # A chunk found by both methods beats one found by a single method at the same rank.
    both = [h for h in result.hits if h.vector_rank and h.keyword_rank]
    assert both and result.hits[0] in both


def test_hybrid_falls_back_to_keyword_when_model_down(indexed):
    result = search(indexed, DownLLM(), "backoff jitter", mode=SearchMode.hybrid)
    assert result.mode == SearchMode.keyword
    assert "keyword search only" in result.warning
    assert result.hits


def test_vector_mode_raises_when_model_down(indexed):
    with pytest.raises(LLMUnavailableError):
        search(indexed, DownLLM(), "backoff", mode=SearchMode.vector)


# ---------- Filters and limits ----------


def test_filter_by_project(indexed, fake_llm):
    filters = SearchFilters(project_ids=["proj-carrier-rates-service"])
    result = search(indexed, fake_llm, "timeout carrier", filters=filters, limit=20)
    assert result.hits
    assert {h.chunk.project_id for h in result.hits} == {"proj-carrier-rates-service"}


def test_filter_by_chunk_type_and_category(indexed, fake_llm):
    filters = SearchFilters(chunk_types=[ChunkType.decision], categories=["AI & GenAI"])
    result = search(indexed, fake_llm, "vector database", filters=filters, limit=20)
    assert ids(result) == ["proj-support-docs-assistant:decision-0"]


def test_filter_by_skill_alias(indexed, fake_llm):
    filters = SearchFilters(skills=["Postgres"])
    result = search(indexed, fake_llm, "index", filters=filters, limit=50)
    assert result.hits
    assert all("PostgreSQL" in h.chunk.skills for h in result.hits)


def test_limit_and_project_names(indexed, fake_llm):
    result = search(indexed, fake_llm, "PostgreSQL", limit=3)
    assert len(result.hits) == 3
    assert all(h.project_name for h in result.hits if h.chunk.project_id)


# ---------- API ----------


def test_search_api(make_api_client, indexed):
    response = make_api_client().post("/search", json={"query": "backoff jitter", "limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "hybrid"
    assert len(body["hits"]) <= 5
    assert body["hits"][0]["project_name"] == "Reliable webhook delivery with retries"
    assert "backoff" in body["hits"][0]["content"].lower()


@pytest.mark.parametrize(
    "payload",
    [{"query": ""}, {"query": "   "}, {"query": "x", "mode": "fuzzy"}, {"query": "x", "limit": 0}],
)
def test_search_api_validation(make_api_client, indexed, payload):
    assert make_api_client().post("/search", json=payload).status_code == 422


def test_search_api_vector_mode_model_down(make_api_client, indexed):
    response = make_api_client(DownLLM()).post("/search", json={"query": "x", "mode": "vector"})
    assert response.status_code == 503
