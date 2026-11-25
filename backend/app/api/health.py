"""Health check: is the API up, can it reach the database, is pgvector installed?"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    pgvector: Literal["ok", "missing", "unknown"]


@router.get("/health", response_model=HealthResponse)
def health(response: Response, db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        has_vector = db.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar_one()
    except SQLAlchemyError:
        logger.exception("Health check: database unavailable")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", database="unavailable", pgvector="unknown")

    if not has_vector:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", database="ok", pgvector="missing")

    return HealthResponse(status="ok", database="ok", pgvector="ok")
