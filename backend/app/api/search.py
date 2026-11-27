"""Search experience chunks. Shows exactly what the assistant retrieves for a question."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import ChunkType
from app.db.session import get_db
from app.llm import LLMProvider, LLMUnavailableError, get_llm
from app.services.retrieval import SearchFilters, SearchMode, search

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: SearchMode = SearchMode.hybrid
    limit: int = Field(default=8, ge=1, le=50)
    project_ids: list[str] = []
    categories: list[str] = []
    skills: list[str] = []
    chunk_types: list[ChunkType] = []


class SearchHitOut(BaseModel):
    chunk_id: str
    chunk_type: str
    title: str
    content: str
    project_id: str | None
    project_name: str | None
    pr_ids: list[str]
    score: float
    vector_score: float | None
    vector_rank: int | None
    keyword_score: float | None
    keyword_rank: int | None


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    took_ms: float
    warning: str | None
    hits: list[SearchHitOut]


@router.post("/search", response_model=SearchResponse)
def search_chunks(
    body: SearchRequest,
    session: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMProvider, Depends(get_llm)],
) -> SearchResponse:
    query = body.query.strip()
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Query must not be blank")
    filters = SearchFilters(
        project_ids=body.project_ids,
        categories=body.categories,
        skills=body.skills,
        chunk_types=body.chunk_types,
    )
    try:
        result = search(session, llm, query, mode=body.mode, filters=filters, limit=body.limit)
    except LLMUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return SearchResponse(
        query=query,
        mode=result.mode,
        took_ms=result.took_ms,
        warning=result.warning,
        hits=[
            SearchHitOut(
                chunk_id=h.chunk.id,
                chunk_type=h.chunk.chunk_type,
                title=h.chunk.title,
                content=h.chunk.content,
                project_id=h.chunk.project_id,
                project_name=h.project_name,
                pr_ids=h.chunk.pr_ids,
                score=round(h.score, 5),
                vector_score=None if h.vector_score is None else round(h.vector_score, 4),
                vector_rank=h.vector_rank,
                keyword_score=None if h.keyword_score is None else round(h.keyword_score, 4),
                keyword_rank=h.keyword_rank,
            )
            for h in result.hits
        ],
    )
