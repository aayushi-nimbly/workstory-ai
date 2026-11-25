"""FastAPI application entry point.

Run locally:
    uv run uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI

from app.api import health, imports
from app.config import get_settings


def create_app() -> FastAPI:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(
        title="WorkStory AI",
        version="0.1.0",
        description="Experience library, RAG assistant and interview prep API.",
    )
    app.include_router(health.router)
    app.include_router(imports.router)
    return app


app = create_app()
