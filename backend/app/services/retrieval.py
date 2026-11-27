"""Find the chunks most relevant to a question.

Three modes:
- vector:  semantic similarity of embeddings (pgvector, cosine distance);
- keyword: PostgreSQL full-text search, matching ANY of the question's words;
- hybrid:  both lists merged with Reciprocal Rank Fusion (RRF).

RRF only looks at positions, not raw scores, so the two very different score
scales never need to be normalised: score = sum(1 / (RRF_K + rank)).
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import Select, Text, cast, func, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.db import models as db
from app.llm import LLMProvider, LLMUnavailableError
from app.services.experience import _skill_lookup as skill_lookup

RRF_K = 60
CANDIDATES = 20  # how many results each method contributes before fusion


class SearchMode(StrEnum):
    vector = "vector"
    keyword = "keyword"
    hybrid = "hybrid"


@dataclass
class SearchFilters:
    project_ids: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    chunk_types: list[db.ChunkType] = field(default_factory=list)


@dataclass
class SearchHit:
    chunk: db.Chunk
    project_name: str | None
    score: float
    vector_score: float | None = None  # cosine similarity, 0..1
    vector_rank: int | None = None
    keyword_score: float | None = None  # ts_rank_cd
    keyword_rank: int | None = None


@dataclass
class SearchResult:
    hits: list[SearchHit]
    mode: SearchMode  # the mode actually used (hybrid falls back to keyword)
    took_ms: float
    warning: str | None = None


def _filtered(session: Session, stmt: Select, filters: SearchFilters) -> Select:
    if filters.project_ids:
        stmt = stmt.where(db.Chunk.project_id.in_(filters.project_ids))
    if filters.chunk_types:
        stmt = stmt.where(db.Chunk.chunk_type.in_([t.value for t in filters.chunk_types]))
    if filters.categories:
        stmt = stmt.where(db.Chunk.categories.overlap(filters.categories))
    if filters.skills:
        # Accept aliases ("Postgres") but filter on canonical names ("PostgreSQL").
        lookup = skill_lookup(session)
        id_to_name = {s.id: s.name for s in session.scalars(select(db.Skill))}
        names = [
            id_to_name[lookup[s.casefold()]] if s.casefold() in lookup else s
            for s in filters.skills
        ]
        stmt = stmt.where(db.Chunk.skills.overlap(names))
    return stmt


def vector_search(
    session: Session,
    llm: LLMProvider,
    query: str,
    filters: SearchFilters,
    limit: int,
) -> list[tuple[db.Chunk, float]]:
    query_vector = llm.embed([query], kind="query")[0]
    distance = db.Chunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(db.Chunk, (1 - distance).label("similarity"))
        # Only embeddings from the current model are comparable with the query.
        .where(db.Chunk.embedding.is_not(None), db.Chunk.embed_model == llm.embed_model)
        .order_by(distance)
        .limit(limit)
    )
    return [(row[0], float(row[1])) for row in session.execute(_filtered(session, stmt, filters))]


def keyword_search(
    session: Session, query: str, filters: SearchFilters, limit: int
) -> list[tuple[db.Chunk, float]]:
    # plainto_tsquery stems words and drops stop words, but ANDs them together.
    # Questions rarely share every word with the answer, so OR the terms instead.
    and_query = func.plainto_tsquery("english", query)
    # A query of only stop words ("have I") has no terms: no keyword hits.
    if not session.scalar(select(func.numnode(and_query))):
        return []
    tsquery = cast(func.replace(cast(and_query, Text), "&", "|"), TSQUERY)
    rank = func.ts_rank_cd(db.Chunk.search, tsquery)
    stmt = (
        select(db.Chunk, rank.label("rank"))
        .where(db.Chunk.search.op("@@")(tsquery))
        .order_by(rank.desc(), db.Chunk.id)
        .limit(limit)
    )
    return [(row[0], float(row[1])) for row in session.execute(_filtered(session, stmt, filters))]


def search(
    session: Session,
    llm: LLMProvider,
    query: str,
    *,
    mode: SearchMode = SearchMode.hybrid,
    filters: SearchFilters | None = None,
    limit: int = 8,
) -> SearchResult:
    started = time.perf_counter()
    filters = filters or SearchFilters()
    warning = None

    vector: list[tuple[db.Chunk, float]] = []
    keyword: list[tuple[db.Chunk, float]] = []

    if mode in (SearchMode.vector, SearchMode.hybrid):
        try:
            vector = vector_search(session, llm, query, filters, CANDIDATES)
        except LLMUnavailableError as exc:
            if mode == SearchMode.vector:
                raise
            mode = SearchMode.keyword
            warning = f"Semantic search unavailable, used keyword search only ({exc})"
    if mode in (SearchMode.keyword, SearchMode.hybrid):
        keyword = keyword_search(session, query, filters, CANDIDATES)

    hits: dict[str, SearchHit] = {}

    def hit(chunk: db.Chunk) -> SearchHit:
        return hits.setdefault(chunk.id, SearchHit(chunk=chunk, project_name=None, score=0.0))

    for rank, (chunk, similarity) in enumerate(vector, start=1):
        h = hit(chunk)
        h.vector_score, h.vector_rank = similarity, rank
    for rank, (chunk, score) in enumerate(keyword, start=1):
        h = hit(chunk)
        h.keyword_score, h.keyword_rank = score, rank

    for h in hits.values():
        if mode == SearchMode.vector:
            h.score = h.vector_score or 0.0
        elif mode == SearchMode.keyword:
            h.score = h.keyword_score or 0.0
        else:
            h.score = sum(1 / (RRF_K + r) for r in (h.vector_rank, h.keyword_rank) if r)

    ranked = sorted(hits.values(), key=lambda h: (-h.score, h.chunk.id))[:limit]

    project_ids = {h.chunk.project_id for h in ranked if h.chunk.project_id}
    if project_ids:
        names = dict(
            session.execute(
                select(db.Project.id, db.Project.name).where(db.Project.id.in_(project_ids))
            ).all()
        )
        for h in ranked:
            h.project_name = names.get(h.chunk.project_id or "")

    return SearchResult(
        hits=ranked,
        mode=mode,
        took_ms=round((time.perf_counter() - started) * 1000, 1),
        warning=warning,
    )
