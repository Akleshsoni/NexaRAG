import logging

from fastapi import FastAPI


from app.api.routes import auth, chat_ui, documents, query, history, stats
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

app = FastAPI(
    title="DocuMind",
    description="Multi-tenant RAG-as-a-service API",
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(history.router)
app.include_router(stats.router)
app.include_router(chat_ui.router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}
