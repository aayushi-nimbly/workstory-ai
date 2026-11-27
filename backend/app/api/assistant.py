"""Experience Assistant: ask questions about your work, get evidence-backed answers."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm import LLMProvider, LLMUnavailableError, get_llm
from app.services.assistant import Support, ask
from app.services.retrieval import SearchFilters

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    project_ids: list[str] = []
    categories: list[str] = []
    skills: list[str] = []


class CitationOut(BaseModel):
    number: int
    chunk_id: str
    chunk_type: str
    title: str
    snippet: str
    project_id: str | None
    project_name: str | None
    pr_ids: list[str]


class AskResponse(BaseModel):
    question: str
    answer: str
    support: Support
    limitations: str | None
    citations: list[CitationOut]
    retrieved_chunk_ids: list[str]
    took_ms: float
    warning: str | None


def _snippet(content: str, length: int = 280) -> str:
    # Skip the "Project: ... / Section: ..." header lines added for retrieval.
    body = "\n".join(
        line for line in content.splitlines() if not line.startswith(("Project: ", "Section: "))
    ).strip()
    return body if len(body) <= length else body[: length - 1].rsplit(" ", 1)[0] + "…"


@router.post("/ask", response_model=AskResponse)
def ask_question(
    body: AskRequest,
    session: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMProvider, Depends(get_llm)],
) -> AskResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Question must not be blank")
    filters = SearchFilters(
        project_ids=body.project_ids, categories=body.categories, skills=body.skills
    )
    try:
        result = ask(session, llm, question, filters=filters)
    except LLMUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The local model is unavailable. Is Ollama running? ({exc})",
        ) from exc

    return AskResponse(
        question=question,
        answer=result.answer,
        support=result.support,
        limitations=result.limitations,
        citations=[
            CitationOut(
                number=c.number,
                chunk_id=c.hit.chunk.id,
                chunk_type=c.hit.chunk.chunk_type,
                title=c.hit.chunk.title,
                snippet=_snippet(c.hit.chunk.content),
                project_id=c.hit.chunk.project_id,
                project_name=c.hit.project_name,
                pr_ids=c.hit.chunk.pr_ids,
            )
            for c in result.citations
        ],
        retrieved_chunk_ids=[h.chunk.id for h in result.retrieved],
        took_ms=result.took_ms,
        warning=result.search_warning,
    )
