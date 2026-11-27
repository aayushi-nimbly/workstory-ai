"""Answer questions about the engineer's experience, grounded in retrieved evidence.

Flow: hybrid search -> label evidence E1..En -> LLM answers with JSON output ->
validate citations -> renumber them [1], [2], ... for display.

The model is never trusted blindly: citations to labels that weren't provided
are dropped, and an answer that claims support but cites nothing valid is
replaced with an "insufficient evidence" reply.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy.orm import Session

from app.llm import ChatMessage, LLMProvider
from app.services.retrieval import SearchFilters, SearchHit, SearchMode, search

logger = logging.getLogger(__name__)

TOP_K = 8
INSUFFICIENT = "I couldn't find enough evidence in your experience to answer that."


class Support(StrEnum):
    direct = "direct"  # the evidence directly answers the question
    partial = "partial"  # related evidence, but not exactly what was asked
    none = "none"  # nothing relevant


SYSTEM_PROMPT = """\
You answer questions about one software engineer's work experience. The user is that engineer, \
so address them as "you". Use ONLY the evidence provided.

Rules:
1. Every fact must come from the evidence. Never add projects, technologies, metrics, numbers \
or outcomes that are not written in the evidence.
2. Write a complete answer of 2-5 sentences (or a short bullet list for several projects). \
Name the project(s) and say concretely what was done. Never answer with just "Yes" or "No".
3. Put the evidence label after each claim, e.g. [E2] or [E1][E4].
4. How directly a skill was used matters. "implemented"/"collaborated" = hands-on. \
"modified"/"used" = worked with something that already existed. "discussed"/"mentioned" = \
NOT hands-on: say clearly it was only discussed or mentioned, and set support to "partial".
5. If evidence marks a project as low confidence or unverified, say so in "limitations".
6. If the evidence does not answer the question, set support to "none" and answer: \
"There isn't enough evidence in your experience to answer this." Never use general knowledge.

support: "direct" = the evidence clearly answers the question with hands-on work; \
"partial" = related or not hands-on; "none" = not relevant.

Example format (the project here is fictional; never reuse its details):
{"answer": "Yes. In Project Alpha you implemented a caching layer in front of the orders API \\
and added cache invalidation on writes [E2][E3]. Redis was only mentioned as an option, not \\
used [E1].", \\
"support": "direct", "cited": ["E2", "E3", "E1"], "limitations": null}"""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "2-5 sentence answer with [E#] labels after each claim",
        },
        "support": {"type": "string", "enum": [s.value for s in Support]},
        "cited": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": ["string", "null"]},
    },
    "required": ["answer", "support", "cited", "limitations"],
}

_LABEL = re.compile(r"\[(E\d+)\]")


@dataclass
class Citation:
    number: int
    hit: SearchHit


@dataclass
class Answer:
    question: str
    answer: str
    support: Support
    limitations: str | None
    citations: list[Citation]
    retrieved: list[SearchHit] = field(default_factory=list)
    took_ms: float = 0.0
    search_warning: str | None = None


def format_evidence(hits: list[SearchHit]) -> str:
    blocks = []
    for i, hit in enumerate(hits, start=1):
        blocks.append(f"[E{i}] {hit.chunk.title}\n{hit.chunk.content}")
    return "\n\n".join(blocks)


def _parse(reply: str) -> dict:
    """Parse the model's JSON, tolerating code fences or text around it."""
    cleaned = reply.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    data = json.loads(cleaned)
    if not isinstance(data, dict) or not isinstance(data.get("answer"), str):
        raise ValueError("reply is missing 'answer'")
    return data


def _ask_model(llm: LLMProvider, question: str, hits: list[SearchHit]) -> dict | None:
    messages = [
        ChatMessage("system", SYSTEM_PROMPT),
        ChatMessage("user", f"Evidence:\n\n{format_evidence(hits)}\n\nQuestion: {question}"),
    ]
    for attempt in (1, 2):
        reply = llm.chat(messages, json_schema=ANSWER_SCHEMA)
        try:
            return _parse(reply)
        except (ValueError, json.JSONDecodeError):
            logger.warning("Unparseable model reply (attempt %s): %.200s", attempt, reply)
    return None


def _ground(data: dict, hits: list[SearchHit]) -> tuple[str, Support, list[Citation], str | None]:
    """Validate citations against the provided evidence and renumber them."""
    valid = {f"E{i}" for i in range(1, len(hits) + 1)}
    answer_text = data["answer"].strip()

    # Order of first appearance in the text, then any extra labels listed in "cited".
    labels: list[str] = []
    for label in _LABEL.findall(answer_text) + [str(c) for c in data.get("cited") or []]:
        label = label.strip("[] ")
        if label in valid and label not in labels:
            labels.append(label)

    numbers = {label: n for n, label in enumerate(labels, start=1)}

    def renumber(match: re.Match) -> str:
        n = numbers.get(match.group(1))
        return f"[{n}]" if n else ""  # drop citations to evidence that doesn't exist

    answer_text = re.sub(r"\s+([.,;:])", r"\1", _LABEL.sub(renumber, answer_text)).strip()

    try:
        support = Support(data.get("support"))
    except ValueError:
        support = Support.partial if labels else Support.none

    limitations = data.get("limitations") or None
    if isinstance(limitations, str) and limitations.strip().lower() in {"null", "none", "n/a", ""}:
        limitations = None
    if support != Support.none and not labels:
        # A claim of support with nothing to back it up is not shown to the user.
        logger.warning("Model claimed %s support without valid citations", support)
        return INSUFFICIENT, Support.none, [], limitations

    citations = [Citation(number=numbers[label], hit=hits[int(label[1:]) - 1]) for label in labels]
    if support == Support.none:
        citations = []
    return answer_text, support, citations, limitations


def ask(
    session: Session,
    llm: LLMProvider,
    question: str,
    *,
    filters: SearchFilters | None = None,
    top_k: int = TOP_K,
) -> Answer:
    started = time.perf_counter()
    result = search(session, llm, question, mode=SearchMode.hybrid, filters=filters, limit=top_k)
    hits = result.hits

    def done(text: str, support: Support, citations: list[Citation], limits: str | None) -> Answer:
        return Answer(
            question=question,
            answer=text,
            support=support,
            limitations=limits,
            citations=citations,
            retrieved=hits,
            took_ms=round((time.perf_counter() - started) * 1000, 1),
            search_warning=result.warning,
        )

    if not hits:
        return done(INSUFFICIENT, Support.none, [], None)

    data = _ask_model(llm, question, hits)
    if data is None:
        return done(
            INSUFFICIENT, Support.none, [], "The model did not return a valid answer. Try again."
        )
    return done(*_ground(data, hits))
