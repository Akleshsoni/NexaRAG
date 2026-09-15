from collections.abc import AsyncGenerator
from google import genai
from google.genai import types
from app.core.config import settings

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None: 
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


RAG_SYSTEM_PROMPT = """You are DocuMind, a precise document assistant.
Answer using ONLY the provided document context.
If the context does not contain the answer, say you don't have enough information.
Never invent facts.
Cite sources using [1], [2], etc."""

GENERAL_SYSTEM_PROMPT = """You are DocuMind, a helpful general-purpose AI assistant.
Answer the user's question using your general knowledge.
Be accurate, clear, and helpful.
Do not mention document context or citations when no documents are provided."""


def build_prompt(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return f"Question: {question}\n\nAnswer helpfully and directly."

    context_blocks = "\n\n".join(
        f"[{i + 1}] (doc {c['document_id']}): {c['text']}"
        for i, c in enumerate(chunks)
    )

    return f"Context:\n{context_blocks}\n\nQuestion: {question}\n\nAnswer using only the context above."

async def generate_answer(question: str, chunks: list[dict]) -> tuple[str, int, int]:
    prompt = build_prompt(question, chunks)
    response = await _get_client().aio.models.generate_content(
        model=settings.llm_model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=RAG_SYSTEM_PROMPT if chunks else GENERAL_SYSTEM_PROMPT, max_output_tokens=1024),
    )
    usage = response.usage_metadata
    return response.text, usage.prompt_token_count, usage.candidates_token_count


async def stream_answer(
    question: str, chunks: list[dict], usage_holder: dict | None = None
) -> AsyncGenerator[str, None]:
    prompt = build_prompt(question, chunks)
    response = _get_client().aio.models.generate_content_stream(
        model=settings.llm_model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=RAG_SYSTEM_PROMPT if chunks else GENERAL_SYSTEM_PROMPT, max_output_tokens=1024),
    )
    async for chunk in response:
        if chunk.text:
            yield chunk.text
        if usage_holder is not None and chunk.usage_metadata:
            usage_holder["input_tokens"] = chunk.usage_metadata.prompt_token_count or 0
            usage_holder["output_tokens"] = chunk.usage_metadata.candidates_token_count or 0