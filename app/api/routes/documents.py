import logging
import re
import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, get_current_user, rate_limit, rate_limit_suggestions, rate_limit_upload
from app.core.config import settings
from app.db.session import get_db
from app.models.models import Document, DocumentStatus
from app.schemas.schemas import DocumentResponse, PaginatedDocuments, total_pages
from app.services import cache, llm, vectorstore
from app.workers.tasks import process_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


def storage_dir() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)  # lazy: importing the app must not touch the disk
    return path


def safe_filename(name: str | None) -> str:
    """Strip any directory part and keep only harmless characters."""
    base = PurePosixPath((name or "").replace("\\", "/")).name.strip()
    base = re.sub(r"[^A-Za-z0-9._() \-]", "_", base)
    return base[:200] or "document"


def validate_upload(filename: str, contents: bytes) -> str:
    """Return the (lower-case) extension, or raise a clean 4xx error."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Only PDF and DOCX files are allowed.")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {settings.max_upload_mb} MB.")
    # Extension alone is not trusted: check the file signature too.
    if ext == ".pdf" and not contents.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="The file is not a valid PDF.")
    if ext == ".docx" and not contents.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="The file is not a valid DOCX.")
    return ext


async def get_owned_document(db: AsyncSession, document_id: uuid.UUID, tenant_id: str) -> Document:
    """404 for both 'does not exist' and 'belongs to another tenant' (no information leak)."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.post("", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_upload),
):
    filename = safe_filename(file.filename)
    # Read at most limit+1 bytes so an oversized upload is never fully held in memory.
    contents = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    ext = validate_upload(filename, contents)

    doc_id = uuid.uuid4()
    storage_path = storage_dir() / f"{doc_id}{ext}"  # server-generated name: no path traversal
    storage_path.write_bytes(contents)

    document = Document(
        id=doc_id,
        tenant_id=user.tenant_id,
        filename=filename,
        storage_path=str(storage_path),
    )
    db.add(document)
    await db.commit()

    process_document.delay(str(doc_id), user.tenant_id, str(storage_path), filename)
    return DocumentResponse.model_validate(document)


@router.get("", response_model=PaginatedDocuments)
async def list_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    total = await db.scalar(select(func.count()).select_from(Document).where(Document.tenant_id == user.tenant_id))
    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == user.tenant_id)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return PaginatedDocuments(
        items=[DocumentResponse.model_validate(d) for d in result.scalars().all()],
        total=total or 0,
        page=page,
        limit=limit,
        total_pages=total_pages(total or 0, limit),
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    document = await get_owned_document(db, document_id, user.tenant_id)
    storage_path = document.storage_path

    # The row goes first: a queued/running worker re-checks it and will not
    # recreate vectors for a document that no longer exists.
    await db.delete(document)
    await db.commit()

    vectors_removed = True
    try:
        await run_in_threadpool(vectorstore.delete_document, user.tenant_id, str(document_id))
    except Exception:  # noqa: BLE001
        # Queries drop chunks whose document row is gone, so leftovers are never served.
        vectors_removed = False
        logger.exception("vector cleanup failed after document delete")

    Path(storage_path).unlink(missing_ok=True)
    await cache.bump_cache_version(user.tenant_id)
    await cache.forget_suggestions(str(document_id))

    return {"id": str(document_id), "status": "deleted", "vectors_removed": vectors_removed}


@router.post("/{document_id}/reindex", response_model=DocumentResponse)
async def reindex_document(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_upload),
):
    document = await get_owned_document(db, document_id, user.tenant_id)

    if document.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="Document is already being processed.")
    if not Path(document.storage_path).exists():
        raise HTTPException(status_code=410, detail="The original file is no longer stored. Please upload it again.")

    try:
        await run_in_threadpool(vectorstore.delete_document, user.tenant_id, str(document_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("vector cleanup failed before re-index")
        raise HTTPException(status_code=503, detail="Vector store is unavailable. Try again shortly.") from exc

    document.status = DocumentStatus.PENDING
    document.error_message = None
    await db.commit()

    await cache.bump_cache_version(user.tenant_id)
    await cache.forget_suggestions(str(document_id))
    process_document.delay(str(document.id), user.tenant_id, document.storage_path, document.filename)
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/suggestions")
async def document_suggestions(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_suggestions),
):
    """5 questions generated from the document's actual indexed text."""
    document = await get_owned_document(db, document_id, user.tenant_id)
    if document.status != DocumentStatus.READY:
        raise HTTPException(status_code=409, detail="Document is not ready yet.")

    cache_key = f"suggestions:{document_id}"
    try:
        cached = await cache.redis_client.get(cache_key)
    except Exception:  # noqa: BLE001
        cached = None
    if cached:
        return {"document_id": str(document_id), "filename": document.filename, "suggestions": cached.split("\n")}

    try:
        chunks = await run_in_threadpool(vectorstore.get_document_chunks, user.tenant_id, str(document_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not load chunks for suggestions")
        raise HTTPException(status_code=503, detail="Vector store is unavailable. Try again shortly.") from exc
    if not chunks:
        raise HTTPException(status_code=409, detail="No indexed content found for this document.")

    try:
        suggestions = await llm.generate_suggestions(document.filename, [c["text"] for c in chunks])
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not suggestions:
        raise HTTPException(status_code=502, detail="Could not generate suggestions. Try again.")

    try:
        await cache.redis_client.set(cache_key, "\n".join(suggestions), ex=60 * 60 * 24)
    except Exception:  # noqa: BLE001
        pass
    return {"document_id": str(document_id), "filename": document.filename, "suggestions": suggestions}
