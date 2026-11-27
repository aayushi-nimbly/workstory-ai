"""Evaluate retrieval (and optionally answers) against a labelled question set.

Question file format (JSON list):
    [{"id": "q1", "question": "...", "kind": "positive",
      "expected_projects": ["proj-a", "proj-b"], "notes": "optional"},
     {"id": "q2", "question": "Have I used Kubernetes?", "kind": "negative",
      "expected_projects": []}]

Relevance is judged at project level: a retrieved chunk is relevant when it
belongs to one of the expected projects.

Metrics per search mode (positive questions only):
    Hit@k     share of questions with at least one relevant chunk in the top k
    Recall@k  share of expected projects that appear in the top k chunks
    MRR       mean of 1 / rank of the first relevant chunk (0 if none in top 20)

With --answers, the full assistant also runs once per question:
    positive  passes if support is not "none" and a citation is from an expected project
    negative  passes if support is "none"

Usage:
    uv run workstory-eval ../examples/eval-questions.json --out ../eval/results-sample.md
    uv run workstory-eval ../data/eval/questions.json --answers --out ../data/eval/results.md
"""

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.llm import LLMProvider
from app.services.assistant import Support, ask
from app.services.retrieval import SearchMode, search

DEPTH = 20  # how deep to look for the first relevant chunk (for MRR)


@dataclass
class Question:
    id: str
    question: str
    kind: str  # "positive" | "negative"
    expected_projects: list[str]
    notes: str = ""


@dataclass
class RetrievalScore:
    hit: bool
    recall: float
    reciprocal_rank: float
    first_relevant_rank: int | None
    top_projects: list[str]


@dataclass
class ModeReport:
    mode: SearchMode
    k: int
    scores: dict[str, RetrievalScore] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)

    def mean(self, attr: str) -> float:
        values = [float(getattr(s, attr)) for s in self.scores.values()]
        return statistics.fmean(values) if values else 0.0


@dataclass
class AnswerResult:
    question_id: str
    passed: bool
    support: str
    cited_projects: list[str]
    seconds: float
    answer: str


def load_questions(path: Path) -> list[Question]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    questions = [Question(**item) for item in raw]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("question ids must be unique")
    for q in questions:
        if q.kind not in ("positive", "negative"):
            raise ValueError(f"{q.id}: kind must be 'positive' or 'negative'")
        if q.kind == "positive" and not q.expected_projects:
            raise ValueError(f"{q.id}: positive questions need expected_projects")
    return questions


def score_ranking(ranked_projects: list[str | None], expected: set[str], k: int) -> RetrievalScore:
    """Score one ranked list of chunk project ids against the expected projects."""
    top_k = ranked_projects[:k]
    found = expected & {p for p in top_k if p}
    first = next((i for i, p in enumerate(ranked_projects, start=1) if p in expected), None)
    return RetrievalScore(
        hit=bool(found),
        recall=len(found) / len(expected),
        reciprocal_rank=1 / first if first else 0.0,
        first_relevant_rank=first,
        top_projects=[p or "(standalone PR)" for p in top_k],
    )


def evaluate_retrieval(
    session: Session, llm: LLMProvider, questions: list[Question], mode: SearchMode, k: int
) -> ModeReport:
    report = ModeReport(mode=mode, k=k)
    for q in questions:
        if q.kind != "positive":
            continue
        result = search(session, llm, q.question, mode=mode, limit=DEPTH)
        report.latencies_ms.append(result.took_ms)
        ranked = [h.chunk.project_id for h in result.hits]
        report.scores[q.id] = score_ranking(ranked, set(q.expected_projects), k)
    return report


def evaluate_answers(
    session: Session, llm: LLMProvider, questions: list[Question]
) -> list[AnswerResult]:
    results = []
    for q in questions:
        started = time.perf_counter()
        answer = ask(session, llm, q.question)
        cited = sorted({c.hit.chunk.project_id or "" for c in answer.citations} - {""})
        if q.kind == "negative":
            passed = answer.support == Support.none
        else:
            passed = answer.support != Support.none and bool(set(cited) & set(q.expected_projects))
        results.append(
            AnswerResult(
                question_id=q.id,
                passed=passed,
                support=answer.support.value,
                cited_projects=cited,
                seconds=round(time.perf_counter() - started, 1),
                answer=answer.answer,
            )
        )
    return results


def render_report(
    questions: list[Question],
    reports: list[ModeReport],
    answers: list[AnswerResult] | None,
    source: str,
) -> str:
    k = reports[0].k if reports else 5
    positives = [q for q in questions if q.kind == "positive"]
    lines = [
        "# Retrieval evaluation",
        "",
        f"- Question set: `{source}` ({len(positives)} positive, "
        f"{len(questions) - len(positives)} negative)",
        f"- Run at: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Retrieval (positive questions)",
        "",
        f"| Mode | Hit@{k} | Recall@{k} | MRR | Median latency |",
        "|---|---|---|---|---|",
    ]
    for r in reports:
        latency = statistics.median(r.latencies_ms) if r.latencies_ms else 0
        lines.append(
            f"| {r.mode.value} | {r.mean('hit'):.2f} | {r.mean('recall'):.2f} | "
            f"{r.mean('reciprocal_rank'):.2f} | {latency:.0f} ms |"
        )

    hybrid = next(
        (r for r in reports if r.mode == SearchMode.hybrid), reports[-1] if reports else None
    )
    if hybrid:
        misses = [q for q in positives if not hybrid.scores[q.id].hit]
        lines += [
            "",
            f"## Misses in {hybrid.mode.value} search (no expected project in top {k})",
            "",
        ]
        if not misses:
            lines.append("None.")
        for q in misses:
            s = hybrid.scores[q.id]
            rank = (
                f"first relevant at rank {s.first_relevant_rank}"
                if s.first_relevant_rank
                else "not in top 20"
            )
            lines.append(
                f"- **{q.id}** {q.question} — expected {', '.join(q.expected_projects)}; {rank}; "
                f"got {', '.join(dict.fromkeys(s.top_projects))}"
            )

    if answers is not None:
        by_kind = {
            kind: [
                a
                for a in answers
                if next(q for q in questions if q.id == a.question_id).kind == kind
            ]
            for kind in ("positive", "negative")
        }
        lines += [
            "",
            "## Answers (full assistant)",
            "",
            "| Kind | Passed | Median time |",
            "|---|---|---|",
        ]
        for kind, items in by_kind.items():
            if items:
                passed = sum(a.passed for a in items)
                median = statistics.median(a.seconds for a in items)
                lines.append(f"| {kind} | {passed}/{len(items)} | {median:.1f} s |")
        failed = [a for a in answers if not a.passed]
        lines += ["", "### Failed answers", ""]
        if not failed:
            lines.append("None.")
        for a in failed:
            q = next(q for q in questions if q.id == a.question_id)
            lines.append(
                f"- **{q.id}** ({q.kind}) {q.question} — support `{a.support}`, "
                f"cited {', '.join(a.cited_projects) or 'nothing'}"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from app.db.session import get_engine
    from app.llm import get_llm

    parser = argparse.ArgumentParser(description="Evaluate retrieval against a question set.")
    parser.add_argument("questions", type=Path)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--modes", default="vector,keyword,hybrid")
    parser.add_argument("--answers", action="store_true", help="also evaluate full answers (slow)")
    parser.add_argument("--out", type=Path, help="write the Markdown report here")
    args = parser.parse_args(argv)

    questions = load_questions(args.questions)
    llm = get_llm()
    modes = [SearchMode(m.strip()) for m in args.modes.split(",")]
    with Session(get_engine()) as session:
        reports = [evaluate_retrieval(session, llm, questions, m, args.k) for m in modes]
        answers = evaluate_answers(session, llm, questions) if args.answers else None

    report = render_report(questions, reports, answers, args.questions.name)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"Report written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
