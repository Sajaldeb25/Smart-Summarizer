"""Groq-powered summarization with structured JSON output and Pydantic validation."""

from __future__ import annotations

import json
import os
import re

from groq import Groq

from .models import ExtractedContent, SummaryOutput

DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Approximate token budget for the user content (1 token ≈ 4 chars)
_MAX_CHARS = 24_000

# Strip control chars that break JSON if echoed unescaped by the model
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_SYSTEM_PROMPT = """\
You are a precise content summarizer. Given a piece of extracted web content, \
return ONLY a single valid JSON object — no markdown fences, no explanation, \
just the raw JSON — with exactly these keys:

  "title"       : string  — the title of the content
  "key_points"  : array   — 3 to 5 concise key points as strings
  "sentiment"   : string  — exactly one of "positive", "neutral", or "negative"
  "summary"     : string  — a concise 3–5 sentence summary (single paragraph, no line breaks)
  "source_type" : string  — exactly one of "youtube", "article", or "webpage"
  "word_count"  : integer — the word count value provided in the user message

Rules:
- Do not include literal newlines or tabs inside JSON string values.
- Do not wrap the JSON in markdown code blocks.
- Do not include any other keys.\
"""


class SummarizationError(Exception):
    """Raised when the Groq API call fails or returns invalid structured output."""


def _sanitize_text(text: str) -> str:
    """Remove control characters from extracted content before sending to Groq."""
    return _CONTROL_CHAR_RE.sub(" ", text)


def _build_user_message(content: ExtractedContent, word_count: int) -> str:
    text = _sanitize_text(content.text)

    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + " [truncated]"

    return (
        f"Source type: {content.source_type}\n"
        f"Title hint: {content.title}\n"
        f"Word count: {word_count}\n\n"
        f"--- Content ---\n{text}"
    )


def _parse_groq_response(raw: str) -> dict:
    """Strip optional markdown fences and parse JSON from the model response."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        raw = "\n".join(inner).strip()
    # strict=False allows literal newlines/tabs inside strings (common LLM mistake)
    return json.loads(raw, strict=False)


def summarize(
    content: ExtractedContent,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> SummaryOutput:
    """
    Send extracted content to the Groq API and return a validated SummaryOutput.

    Retries once if the first response cannot be parsed as valid JSON.
    Raises SummarizationError on API or validation failure.
    """
    resolved_key = api_key or os.getenv("GROQ_API_KEY")
    if not resolved_key:
        raise SummarizationError(
            "GROQ_API_KEY is not set. Add it to your .env file or pass it explicitly."
        )

    client = Groq(api_key=resolved_key)
    word_count = len(content.text.split())
    user_message = _build_user_message(content, word_count)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            chat_response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise SummarizationError(f"Groq API request failed: {exc}") from exc

        raw_content = chat_response.choices[0].message.content or ""

        try:
            data = _parse_groq_response(raw_content)
            data["word_count"] = word_count
            return SummaryOutput.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            user_message = user_message + (
                "\n\nIMPORTANT: Your previous response was not valid JSON. "
                "Return ONLY a raw JSON object — no markdown, no prose, "
                "and no line breaks inside string values."
            )

    raise SummarizationError(
        f"Groq returned invalid structured output after 2 attempts: {last_error}"
    )
