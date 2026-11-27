import json

import pytest

from app.llm import LLMUnavailableError
from app.services.assistant import INSUFFICIENT, Support, ask
from app.services.embedding import embed_pending
from app.services.importer import import_experience
from tests.fakes import FakeLLM
from tests.test_importer import SAMPLE_PATH


def reply(answer, support="direct", cited=None, limitations=None) -> str:
    return json.dumps(
        {"answer": answer, "support": support, "cited": cited or [], "limitations": limitations}
    )


@pytest.fixture
def indexed(db_session, fake_llm):
    import_experience(db_session, SAMPLE_PATH.read_bytes())
    embed_pending(db_session, fake_llm)
    return db_session


def test_answer_with_valid_citations_is_renumbered(indexed):
    llm = FakeLLM(
        reply=reply("You added backoff [E3] and a dead-letter table [E1][E3].", cited=["E3", "E1"])
    )
    result = ask(indexed, llm, "Have I implemented retries?")

    assert result.support == Support.direct
    assert result.answer == "You added backoff [1] and a dead-letter table [2][1]."
    assert [c.number for c in result.citations] == [1, 2]
    assert result.citations[0].hit is result.retrieved[2]
    assert result.citations[1].hit is result.retrieved[0]


def test_prompt_contains_labelled_evidence_and_rules(indexed):
    llm = FakeLLM(reply=reply("x [E1]", cited=["E1"]))
    ask(indexed, llm, "Have I used Kafka?")

    call = llm.chat_calls[0]
    system, user = call["messages"]
    assert "Use ONLY the evidence" in system.content
    assert "NOT hands-on" in system.content
    assert "[E1] " in user.content and "Question: Have I used Kafka?" in user.content
    assert call["json_schema"]["required"] == ["answer", "support", "cited", "limitations"]


def test_citations_to_unknown_evidence_are_dropped(indexed):
    llm = FakeLLM(reply=reply("Real [E1]. Invented [E99].", cited=["E1", "E99"]))
    result = ask(indexed, llm, "retries")
    assert result.answer == "Real [1]. Invented."
    assert len(result.citations) == 1


def test_claimed_support_without_citations_is_rejected(indexed):
    llm = FakeLLM(reply=reply("You built a Kubernetes operator.", support="direct"))
    result = ask(indexed, llm, "Have I used Kubernetes?")
    assert result.answer == INSUFFICIENT
    assert result.support == Support.none
    assert result.citations == []


def test_none_support_has_no_citations(indexed):
    llm = FakeLLM(reply=reply("Not enough evidence.", support="none", cited=["E1"]))
    result = ask(indexed, llm, "Have I built iOS apps?")
    assert result.support == Support.none
    assert result.citations == []


def test_partial_support_and_limitations(indexed):
    llm = FakeLLM(
        reply=reply(
            "Kafka was only discussed [E1].", support="partial", cited=["E1"], limitations="null"
        )
    )
    result = ask(indexed, llm, "Kafka")
    assert result.support == Support.partial
    assert result.limitations is None  # the string "null" is treated as no limitations


def test_reply_wrapped_in_code_fence_is_parsed(indexed):
    llm = FakeLLM(reply="```json\n" + reply("Answer [E1]", cited=["E1"]) + "\n```")
    assert ask(indexed, llm, "retries").answer == "Answer [1]"


def test_invalid_json_is_retried_then_gives_up(indexed):
    replies = iter(["not json", reply("Second try [E1]", cited=["E1"])])
    llm = FakeLLM(reply=lambda messages: next(replies))
    assert ask(indexed, llm, "retries").answer == "Second try [1]"

    always_bad = FakeLLM(reply="not json")
    result = ask(indexed, always_bad, "retries")
    assert result.answer == INSUFFICIENT
    assert "valid answer" in result.limitations
    assert len(always_bad.chat_calls) == 2


def test_no_retrieved_evidence_skips_the_model(db_session):
    llm = FakeLLM(reply=reply("should not be used"))
    result = ask(db_session, llm, "anything")  # nothing imported
    assert result.answer == INSUFFICIENT
    assert llm.chat_calls == []


def test_filters_limit_evidence(indexed):
    llm = FakeLLM(reply=reply("x [E1]", cited=["E1"]))
    from app.services.retrieval import SearchFilters

    result = ask(
        indexed, llm, "timeout", filters=SearchFilters(project_ids=["proj-carrier-rates-service"])
    )
    assert {h.chunk.project_id for h in result.retrieved} == {"proj-carrier-rates-service"}


# ---------- API ----------


def test_ask_api(make_api_client, indexed):
    llm = FakeLLM(reply=reply("You implemented retries [E1].", cited=["E1"]))
    response = make_api_client(llm).post(
        "/assistant/ask", json={"question": "Have I done retries?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "You implemented retries [1]."
    assert body["support"] == "direct"
    citation = body["citations"][0]
    assert citation["number"] == 1
    assert not citation["snippet"].startswith("Project: ")
    assert len(body["retrieved_chunk_ids"]) == 8


def test_ask_api_model_down(make_api_client, indexed):
    class Down(FakeLLM):
        def chat(self, *args, **kwargs):
            raise LLMUnavailableError("connection refused")

    response = make_api_client(Down()).post("/assistant/ask", json={"question": "retries"})
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]


@pytest.mark.parametrize("question", ["", "   "])
def test_ask_api_rejects_blank(make_api_client, indexed, question):
    assert make_api_client().post("/assistant/ask", json={"question": question}).status_code == 422
