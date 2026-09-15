import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.models import Document
from app.schemas.schemas import DocumentResponse
from app.workers.tasks import process_document

router = APIRouter(prefix="/documents", tags=["documents"])

STORAGE_DIR = Path("/data/uploads")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


@router.post("", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Write to disk first so the request returns fast -- heavy lifting
    # (extraction, chunking, embedding) happens in the Celery worker.
    doc_id = uuid.uuid4()
    storage_path = STORAGE_DIR / f"{doc_id}_{file.filename}"
    contents = await file.read()
    storage_path.write_bytes(contents)

    document = Document(
        id=doc_id,
        tenant_id=user.tenant_id,
        filename=file.filename,
        storage_path=str(storage_path),
    )
    db.add(document)
    await db.commit()

    process_document.delay(str(doc_id), user.tenant_id, str(storage_path), file.filename)

    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.tenant_id == user.tenant_id))
    return result.scalars().all()
