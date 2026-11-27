"""Fill in embeddings for chunks that don't have one yet.

Runs after an import (in the background for API uploads), or on demand with:
    uv run workstory-embed

Work is committed batch by batch, so an interrupted run loses at most one batch
and the next run continues where it stopped.
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import Chunk
from app.llm import LLMProvider, LLMUnavailableError

logger = logging.getLogger(__name__)

BATCH_SIZE = 32


@dataclass
class EmbeddingStatus:
    total: int
    embedded: int

    @property
    def pending(self) -> int:
        return self.total - self.embedded


def _pending_filter(model_name: str):
    return or_(Chunk.embedding.is_(None), Chunk.embed_model != model_name)


def embedding_status(session: Session, model_name: str) -> EmbeddingStatus:
    total = session.scalar(select(func.count()).select_from(Chunk)) or 0
    pending = (
        session.scalar(select(func.count()).select_from(Chunk).where(_pending_filter(model_name)))
        or 0
    )
    return EmbeddingStatus(total=total, embedded=total - pending)


def embed_pending(session: Session, llm: LLMProvider, *, batch_size: int = BATCH_SIZE) -> int:
    """Embed every pending chunk. Returns how many were embedded.

    Raises LLMUnavailableError if the model provider fails; chunks embedded
    before the failure are kept.
    """
    done = 0
    while True:
        batch = session.execute(
            select(Chunk.id, Chunk.title, Chunk.content, Chunk.content_hash)
            .where(_pending_filter(llm.embed_model))
            .order_by(Chunk.id)
            .limit(batch_size)
        ).all()
        if not batch:
            break

        vectors = llm.embed([f"{row.title}\n{row.content}" for row in batch], kind="document")
        now = datetime.now(UTC)
        for row, vector in zip(batch, vectors, strict=True):
            # Only write if the text hasn't changed since we read it.
            session.execute(
                update(Chunk)
                .where(Chunk.id == row.id, Chunk.content_hash == row.content_hash)
                .values(embedding=vector, embed_model=llm.embed_model, embedded_at=now)
            )
        session.commit()
        done += len(batch)
        logger.info("Embedded %s chunks (%s so far)", len(batch), done)
    return done


def run_embedding(session: Session, llm: LLMProvider) -> None:
    """Background-task entry point: never raises, only logs."""
    try:
        count = embed_pending(session, llm)
        logger.info("Embedding finished: %s chunks embedded", count)
    except LLMUnavailableError as exc:
        session.rollback()
        logger.warning("Embedding paused, model provider unavailable: %s", exc)
    except Exception:
        session.rollback()
        logger.exception("Embedding failed")


def main(argv: list[str] | None = None) -> int:
    from app.db.session import get_engine
    from app.llm import get_llm

    argparse.ArgumentParser(description="Embed chunks that have no embedding yet.").parse_args(argv)
    llm = get_llm()
    with Session(get_engine()) as session:
        try:
            count = embed_pending(session, llm)
        except LLMUnavailableError as exc:
            print(f"✗ {exc}")
            return 1
        status = embedding_status(session, llm.embed_model)
    print(f"✓ Embedded {count} chunk(s). {status.embedded}/{status.total} chunks have embeddings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
