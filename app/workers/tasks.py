import asyncio

from sqlalchemy import update

from app.db.session import AsyncSessionLocal
from app.models.models import Document, DocumentStatus
from app.services.chunking import chunk_text, extract_text
from app.services.embeddings import embed_texts
from app.services.vectorstore import upsert_chunks
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.process_document", bind=True, max_retries=3)
def process_document(self, document_id: str, tenant_id: str, storage_path: str, filename: str):
    """Extract -> chunk -> embed -> store. Retries up to 3x on transient failures
    (e.g. embedding API rate limits) before marking the document FAILED."""
    try:
        text = extract_text(storage_path, filename)
        chunks = chunk_text(text)

        if not chunks:
            _set_status(document_id, DocumentStatus.FAILED, "No extractable text found")
            return

        embeddings = embed_texts(chunks)
        upsert_chunks(tenant_id, document_id, chunks, embeddings)
        _set_status(document_id, DocumentStatus.READY)

    except Exception as exc:  # noqa: BLE001
        try:
            self.retry(exc=exc, countdown=2**self.request.retries)
        except self.MaxRetriesExceededError:
            _set_status(document_id, DocumentStatus.FAILED, str(exc))


def _set_status(document_id: str, status: DocumentStatus, error: str | None = None) -> None:
    async def _update():
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=status, error_message=error)
            )
            await session.commit()

    asyncio.run(_update())
