import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    tenant_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    created_at: datetime
    error_message: str | None = None


class PaginatedDocuments(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)
    stream: bool = True


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    filename: str = ""


class QueryResponse(BaseModel):
    answer: str
    sources: list[RetrievedChunk]
    latency_ms: int
    # "rag": answered from the user's documents. "general": nothing relevant was
    # retrieved above the similarity threshold, so the model answered without documents.
    mode: str = "rag"


class QueryHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    answer: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    created_at: datetime


class PaginatedQueries(BaseModel):
    items: list[QueryHistoryItem]
    total: int
    page: int
    limit: int
    total_pages: int


def total_pages(total: int, limit: int) -> int:
    return max(1, -(-total // limit))
