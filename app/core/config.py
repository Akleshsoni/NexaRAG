from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-secret"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://documind:documind@localhost:5432/documind"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "documind_chunks"

    gemini_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    default_tenant_token_budget: int = 200_000

    access_token_expire_minutes: int = 60 * 24
    jwt_algorithm: str = "HS256"

    # --- Uploads ---
    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 10

    # --- Retrieval ---
    # Minimum cosine similarity (vector score) for a chunk to count as relevant.
    # Below this, no chunks are used and the query falls back to general AI.
    # This is a heuristic for the bge-small model; tune it with eval/evaluate_rag.py.
    retrieval_min_score: float = 0.55
    retrieval_dedup_overlap: float = 0.70

    # --- Rate limits (requests per minute, per user) ---
    rate_limit_default_rpm: int = 60
    rate_limit_query_rpm: int = 30
    rate_limit_upload_rpm: int = 10
    rate_limit_suggestions_rpm: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
