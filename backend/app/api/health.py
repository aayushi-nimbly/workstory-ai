"""Health check: API, database, pgvector and local models."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm import LLMProvider, get_llm

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    pgvector: Literal["ok", "missing", "unknown"]
    llm: Literal["ok", "unavailable", "model_missing"]
    missing_models: list[str] = []


@router.get("/health", response_model=HealthResponse)
def health(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMProvider, Depends(get_llm)],
) -> HealthResponse:
    model_status = llm.status()
    llm_state = (
        "ok" if model_status.ok else ("model_missing" if model_status.reachable else "unavailable")
    )

    database, pgvector = "ok", "ok"
    try:
        db.execute(text("SELECT 1"))
        has_vector = db.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar_one()
        if not has_vector:
            pgvector = "missing"
    except SQLAlchemyError:
        logger.exception("Health check: database unavailable")
        database, pgvector = "unavailable", "unknown"

    # Without the database nothing works (503). Without models only the assistant is affected.
    if database != "ok" or pgvector != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    all_ok = database == "ok" and pgvector == "ok" and llm_state == "ok"
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        database=database,
        pgvector=pgvector,
        llm=llm_state,
        missing_models=model_status.missing_models,
    )
