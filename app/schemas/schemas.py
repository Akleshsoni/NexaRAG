import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    stream: bool = True


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[RetrievedChunk]
    latency_ms: int
