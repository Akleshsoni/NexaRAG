"""Gemini wrapper: grounded RAG answers, general answers, comparison, suggestions.

Prompt construction lives here so retrieval changes never touch generation code.
"""
import json
import logging
import re
from collections.abc import AsyncGenerator

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


class LLMError(Exception):
    """Raised for any LLM provider failure; the message is safe to show to users."""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise LLMError("The AI service is not configured.")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _friendly(exc: Exception) -> LLMError:
    code = getattr(exc, "code", None)
    if code == 429:
        return LLMError("The AI provider quota or rate limit was reached. Please try again shortly.")
    if code in (500, 503):
        return LLMError("The AI provider is temporarily unavailable. Please try again.")
    return LLMError("The AI service failed to generate a response.")


LANGUAGE_RULE = (
    "Reply in the same language the user wrote in (English, Hindi, or Hinglish). "
    "Keep technical terms, names and numbers exactly as written in the sources."
)

RAG_SYSTEM_PROMPT = (
    "You are a precise assistant that answers questions using ONLY the provided context. "
    "If the context does not contain the answer, say you could not find it in the documents -- "
    "never invent facts. Cite the source number for each claim, like [1] or [2]. "
    + LANGUAGE_RULE
)

GENERAL_SYSTEM_PROMPT = (
    "You are a helpful assistant. No relevant passages were found in the user's uploaded "
    "documents for this question, so answer from general knowledge and do not cite any sources. "
    "If the question clearly refers to the user's own documents (for example 'in my document' "
    "or 'in the uploaded file'), say you could not find relevant content in their documents. "
    "Be concise and accurate; if unsure, say so. " + LANGUAGE_RULE
)

COMPARE_SYSTEM_PROMPT = (
    "You compare documents using ONLY the numbered excerpts provided, grouped by document. "
    "State clearly which document each point comes from and cite excerpt numbers like [1]. "
    "Cover common points and differences. If a document has no relevant excerpts, say so "
    "explicitly instead of guessing. Never use outside knowledge. " + LANGUAGE_RULE
)

NO_ANSWER = "I could not generate an answer for this question."


def _label(c: dict) -> str:
    return c.get("filename") or f"doc {c['document_id']}"


def build_prompt(question: str, chunks: list[dict]) -> str:
    context_blocks = "\n\n".join(f"[{i + 1}] (source: {_label(c)}): {c['text']}" for i, c in enumerate(chunks))
    return f"Context:\n{context_blocks}\n\nQuestion: {question}\n\nAnswer using only the context above."


def build_comparison_prompt(
    question: str, per_doc_chunks: dict[str, list[dict]], doc_names: dict[str, str]
) -> str:
    blocks: list[str] = []
    n = 0
    for doc_id, chunks in per_doc_chunks.items():
        name = doc_names.get(doc_id, doc_id)
        if not chunks:
            blocks.append(f"=== Document: {name} ===\n(no relevant excerpts found in this document)")
            continue
        lines = []
        for c in chunks:
            n += 1  # numbering matches the order of the `sources` list returned by the API
            lines.append(f"[{n}] {c['text']}")
        blocks.append(f"=== Document: {name} ===\n" + "\n\n".join(lines))
    return "\n\n".join(blocks) + f"\n\nTask: {question}"


def _config(system: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(system_instruction=system, max_output_tokens=1024)


def _usage(response) -> tuple[int, int]:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return 0, 0
    return (usage.prompt_token_count or 0), (usage.candidates_token_count or 0)


async def _generate(prompt: str, system: str) -> tuple[str, int, int]:
    try:
        response = await _get_client().aio.models.generate_content(
            model=settings.llm_model, contents=prompt, config=_config(system)
        )
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM call failed")
        raise _friendly(exc) from exc
    in_t, out_t = _usage(response)
    return (response.text or NO_ANSWER), in_t, out_t


async def generate_answer(question: str, chunks: list[dict]) -> tuple[str, int, int]:
    """RAG answer when chunks exist, general answer otherwise."""
    if chunks:
        return await _generate(build_prompt(question, chunks), RAG_SYSTEM_PROMPT)
    return await _generate(question, GENERAL_SYSTEM_PROMPT)


async def stream_answer(
    question: str, chunks: list[dict], usage_holder: dict | None = None
) -> AsyncGenerator[str, None]:
    prompt, system = (
        (build_prompt(question, chunks), RAG_SYSTEM_PROMPT) if chunks else (question, GENERAL_SYSTEM_PROMPT)
    )
    try:
        response = _get_client().aio.models.generate_content_stream(
            model=settings.llm_model, contents=prompt, config=_config(system)
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text
            if usage_holder is not None and chunk.usage_metadata:
                usage_holder["input_tokens"] = chunk.usage_metadata.prompt_token_count or 0
                usage_holder["output_tokens"] = chunk.usage_metadata.candidates_token_count or 0
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM stream failed")
        raise _friendly(exc) from exc


async def generate_comparison(
    question: str, per_doc_chunks: dict[str, list[dict]], doc_names: dict[str, str]
) -> tuple[str, int, int]:
    prompt = build_comparison_prompt(question, per_doc_chunks, doc_names)
    return await _generate(prompt, COMPARE_SYSTEM_PROMPT)


SUGGESTION_PROMPT = (
    "Below are excerpts from a document called '{name}'. Write exactly 5 useful, specific questions "
    "a reader could ask about THIS document, each answerable from the excerpts. "
    "Do not write generic questions. Return ONLY a JSON array of 5 strings.\n\n{excerpts}"
)


def parse_suggestions(raw: str) -> list[str]:
    """Parse the model's reply into a clean list of at most 5 questions."""
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    items: list = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            items = parsed
    except json.JSONDecodeError:
        items = [re.sub(r"^[\s\-*\d.)]+", "", line) for line in text.splitlines()]
    cleaned = [s.strip() for s in items if isinstance(s, str) and len(s.strip()) > 5]
    return cleaned[:5]


async def generate_suggestions(filename: str, texts: list[str]) -> list[str]:
    excerpts = "\n\n".join(f"- {t[:1200]}" for t in texts)
    prompt = SUGGESTION_PROMPT.format(name=filename, excerpts=excerpts)
    answer, _, _ = await _generate(prompt, "You write helpful questions about documents. " + LANGUAGE_RULE)
    return parse_suggestions(answer)
