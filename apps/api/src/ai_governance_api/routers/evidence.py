"""FastAPI adapter for secure evidence upload and metadata queries."""

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from ai_governance_api.dependencies import (
    CurrentPrincipal,
    ListEvidenceDependency,
    UploadEvidenceDependency,
)
from ai_governance_api.domain.evidence import EvidenceActor, EvidenceKind
from ai_governance_api.evidence_schemas import EvidenceRead

router = APIRouter(prefix="/api/v1", tags=["evidence"])


class FastAPIUploadSource:
    """Adapt Starlette's upload stream to the application-owned source port."""

    def __init__(self, upload: UploadFile) -> None:
        """Capture normalized transport metadata without reading content."""
        self._upload = upload
        self.filename = upload.filename or ""
        self.content_type = upload.content_type or ""

    async def read(self, size: int) -> bytes:
        """Delegate bounded asynchronous reads to the multipart upload."""
        return await self._upload.read(size)


@router.get(
    "/initiatives/{initiative_id}/evidence",
    response_model=list[EvidenceRead],
)
async def list_evidence(
    initiative_id: str,
    use_case: ListEvidenceDependency,
    _: CurrentPrincipal,
) -> list[EvidenceRead]:
    """List trusted uploaded evidence metadata for an initiative."""
    records = await use_case.execute(
        initiative_id,
        EvidenceActor(user_id=_.user_id, is_admin=_.is_admin),
    )
    return [EvidenceRead.from_domain(record) for record in records]


@router.post(
    "/initiatives/{initiative_id}/evidence",
    response_model=EvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_evidence(
    initiative_id: str,
    kind: Annotated[EvidenceKind, Form()],
    file: Annotated[UploadFile, File()],
    use_case: UploadEvidenceDependency,
    principal: CurrentPrincipal,
) -> EvidenceRead:
    """Upload evidence through bounded validation, scanning, and storage."""
    try:
        record = await use_case.execute(
            initiative_id=initiative_id,
            kind=kind,
            source=FastAPIUploadSource(file),
            actor=EvidenceActor(user_id=principal.user_id, is_admin=principal.is_admin),
        )
    finally:
        await file.close()
    return EvidenceRead.from_domain(record)
