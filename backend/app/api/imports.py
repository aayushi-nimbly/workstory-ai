"""Import experience files and view import history."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as db
from app.db.session import get_db
from app.experience.checks import Issue
from app.services.importer import ImportValidationError, import_experience

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class IssueOut(BaseModel):
    path: str
    message: str

    @classmethod
    def from_issue(cls, issue: Issue) -> "IssueOut":
        return cls(path=issue.path, message=issue.message)


class ImportResponse(BaseModel):
    import_id: int | None
    unchanged: bool
    counts: dict[str, int]
    warnings: list[IssueOut]


class ImportRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    file_hash: str
    schema_version: str | None
    counts: dict[str, int]
    error: str | None
    started_at: datetime
    finished_at: datetime | None


@router.post(
    "",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "File unchanged since the last import; nothing was written"},
        413: {"description": "File too large"},
        422: {"description": "File is not valid JSON or fails validation"},
    },
)
async def create_import(
    file: UploadFile,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    force: Annotated[bool, Query(description="Import even if the file is unchanged.")] = False,
) -> ImportResponse:
    """Upload a `workstory-experience.json` file and load it into the database."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    try:
        result = import_experience(session, content, force=force)
    except ImportValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "message": f"Import #{exc.import_id} failed validation",
                "import_id": exc.import_id,
                "errors": [IssueOut.from_issue(i).model_dump() for i in exc.errors],
                "warnings": [IssueOut.from_issue(i).model_dump() for i in exc.warnings],
            },
        ) from exc

    if result.unchanged:
        response.status_code = status.HTTP_200_OK
    return ImportResponse(
        import_id=result.import_id,
        unchanged=result.unchanged,
        counts=result.counts,
        warnings=[IssueOut.from_issue(i) for i in result.warnings],
    )


@router.get("", response_model=list[ImportRecordOut])
def list_imports(
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[db.Import]:
    """Most recent imports first."""
    return list(session.scalars(select(db.Import).order_by(db.Import.id.desc()).limit(limit)))
