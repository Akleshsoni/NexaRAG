import asyncio
import logging

from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.models.models import Document, DocumentStatus
from app.services.cache import bump_cache_version_sync
from app.services.chunking import chunk_text, extract_text
from app.services.embeddings import embed_texts
from app.services.vectorstore import delete_document, upsert_chunks
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    return asyncio.run(coro)


def _document_exists(document_id: str) -> bool:
    async def _check() -> bool:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Document.id).where(Document.id == document_id))
            return result.first() is not None

    return _run(_check())


def _set_status(document_id: str, status: DocumentStatus, error: str | None = None) -> None:
    async def _update():
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=status, error_message=error)
            )
            await session.commit()

    _run(_update())


@celery_app.task(name="app.workers.tasks.process_document", bind=True, max_retries=3)
def process_document(self, document_id: str, tenant_id: str, storage_path: str, filename: str):
    """Extract -> chunk -> embed -> store.

    Used for both first-time indexing and re-indexing (existing vectors are removed
    before the new ones are written, so no duplicates). The document row is
    re-checked before and after writing vectors: if the user deleted the document
    while it was queued/processing, the worker never leaves vectors behind.
    """
    if not _document_exists(document_id):
        logger.info("document deleted before processing; skipping")
        return

    try:
        _set_status(document_id, DocumentStatus.PROCESSING)

        text = extract_text(storage_path, filename)
        chunks = chunk_text(text)
        if not chunks:
            _set_status(document_id, DocumentStatus.FAILED, "No extractable text found")
            return

        embeddings = embed_texts(chunks)

        if not _document_exists(document_id):
            return

        delete_document(tenant_id, document_id)  # idempotent: re-index never duplicates
        upsert_chunks(tenant_id, document_id, chunks, embeddings)

        if not _document_exists(document_id):  # deleted while we were writing
            delete_document(tenant_id, document_id)
            return

        _set_status(document_id, DocumentStatus.READY)
        bump_cache_version_sync(tenant_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("document processing failed")
        try:
            self.retry(exc=exc, countdown=2**self.request.retries)
        except self.MaxRetriesExceededError:
            # Keep the stored message generic: internal errors stay in the logs.
            _set_status(document_id, DocumentStatus.FAILED, f"Processing failed ({type(exc).__name__})")
