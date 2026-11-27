import json

import pytest

from app.evaluation import (
    evaluate_answers,
    evaluate_retrieval,
    load_questions,
    render_report,
    score_ranking,
)
from app.services.embedding import embed_pending
from app.services.importer import import_experience
from app.services.retrieval import SearchMode
from tests.fakes import FakeLLM
from tests.test_importer import SAMPLE_PATH

QUESTIONS_PATH = SAMPLE_PATH.parent / "eval-questions.json"


# ---------- Metric maths ----------


def test_score_ranking_hit_recall_and_mrr():
    ranked = ["a", None, "b", "a", "c"]
    score = score_ranking(ranked, {"b", "c", "z"}, k=3)
    assert score.hit is True
    assert score.recall == pytest.approx(1 / 3)  # only b is in the top 3
    assert score.first_relevant_rank == 3
    assert score.reciprocal_rank == pytest.approx(1 / 3)
    assert score.top_projects == ["a", "(standalone PR)", "b"]


def test_score_ranking_miss():
    score = score_ranking(["a", "a"], {"b"}, k=5)
    assert (score.hit, score.recall, score.reciprocal_rank, score.first_relevant_rank) == (
        False,
        0.0,
        0.0,
        None,
    )


def test_relevant_beyond_k_counts_for_mrr_only():
    score = score_ranking(["x"] * 6 + ["b"], {"b"}, k=5)
    assert not score.hit
    assert score.reciprocal_rank == pytest.approx(1 / 7)


# ---------- Question file ----------


def test_sample_question_file_is_valid():
    questions = load_questions(QUESTIONS_PATH)
    assert {q.kind for q in questions} == {"positive", "negative"}


@pytest.mark.parametrize(
    "items, message",
    [
        (
            [{"id": "a", "question": "x", "kind": "positive", "expected_projects": []}],
            "need expected",
        ),
        ([{"id": "a", "question": "x", "kind": "maybe", "expected_projects": []}], "kind must"),
        (
            [
                {"id": "a", "question": "x", "kind": "negative", "expected_projects": []},
                {"id": "a", "question": "y", "kind": "negative", "expected_projects": []},
            ],
            "unique",
        ),
    ],
)
def test_invalid_question_files(tmp_path, items, message):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(items))
    with pytest.raises(ValueError, match=message):
        load_questions(path)


# ---------- End to end on the sample data (fake model) ----------


@pytest.fixture
def indexed(db_session, fake_llm):
    import_experience(db_session, SAMPLE_PATH.read_bytes())
    embed_pending(db_session, fake_llm)
    return db_session


def test_evaluate_retrieval_on_sample(indexed, fake_llm):
    questions = load_questions(QUESTIONS_PATH)
    report = evaluate_retrieval(indexed, fake_llm, questions, SearchMode.keyword, k=5)
    assert set(report.scores) == {q.id for q in questions if q.kind == "positive"}
    assert 0 < report.mean("hit") <= 1


def test_evaluate_answers_pass_rules(indexed):
    questions = [q for q in load_questions(QUESTIONS_PATH) if q.id in ("q01", "n01")]
    # The fake model always cites E1 with direct support: positives may pass, negatives fail.
    llm = FakeLLM(
        reply=json.dumps(
            {"answer": "x [E1]", "support": "direct", "cited": ["E1"], "limitations": None}
        )
    )
    results = {r.question_id: r for r in evaluate_answers(indexed, llm, questions)}
    assert results["n01"].passed is False
    assert results["n01"].support == "direct"


def test_render_report_has_tables(indexed, fake_llm):
    questions = load_questions(QUESTIONS_PATH)
    reports = [
        evaluate_retrieval(indexed, fake_llm, questions, mode, k=5)
        for mode in (SearchMode.keyword, SearchMode.hybrid)
    ]
    text = render_report(questions, reports, None, "eval-questions.json")
    assert "| keyword |" in text and "| hybrid |" in text
    assert "Misses in hybrid search" in text
