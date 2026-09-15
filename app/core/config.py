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
    voyage_api_key: str = ""
    embedding_model: str = "voyage-3-lite"

    default_tenant_token_budget: int = 200_000

    access_token_expire_minutes: int = 60 * 24
    jwt_algorithm: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
