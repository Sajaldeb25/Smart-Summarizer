"""Groq-powered summarization with structured JSON output and Pydantic validation."""

from __future__ import annotations

import json
import os

from groq import Groq

from .models import ExtractedContent, SummaryOutput

DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Approximate token budget for the user content (1 token ≈ 4 chars)
_MAX_CHARS = 24_000

_SYSTEM_PROMPT = """\
You are a precise content summarizer. Given a piece of extracted web content, \
return ONLY a single valid JSON object — no markdown fences, no explanation, \
just the raw JSON — with exactly these keys:

  "title"       : string  — the title of the content
  "key_points"  : array   — 3 to 5 concise key points as strings
  "sentiment"   : string  — exactly one of "positive", "neutral", or "negative"
  "summary"     : string  — key points as bullet points in 15–20 sentences
  "source_type" : string  — exactly one of "youtube", "article", or "webpage"
  "word_count"  : integer — the word count value provided in the user message

Do not include any other keys. Do not wrap the JSON in markdown code blocks.\
"""


class SummarizationError(Exception):
    """Raised when the Groq API call fails or returns invalid structured output."""


def _build_user_message(content: ExtractedContent, word_count: int) -> str:
    text = content.text

    # check if the text is longer than the maximum character count
    if len(text) > _MAX_CHARS:
        # truncate the text if it is longer than the maximum character count
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
    # Remove ```json ... ``` or ``` ... ``` fences if the model included them
    if raw.startswith("```"):
        lines = raw.splitlines()
        # Drop first line (```json or ```) and last line (```)
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        raw = "\n".join(inner).strip()
    return json.loads(raw)


def summarize(content: ExtractedContent, api_key: str | None = None, model: str = DEFAULT_MODEL,) -> SummaryOutput:
    
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

    # Current Groq model recommendations (July 2026):
    #   balanced default:  llama-3.3-70b-versatile  (default, available until Aug 16 2026)


    client = Groq(api_key=resolved_key)
    word_count = len(content.text.split())
    user_message = _build_user_message(content, word_count)

    # API call to the Groq model
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
            )
        except Exception as exc:
            raise SummarizationError(f"Groq API request failed: {exc}") from exc

        raw_content = chat_response.choices[0].message.content or ""

        try:
            data = _parse_groq_response(raw_content)
            # Enforce the locally computed word_count so the model can't hallucinate it
            data["word_count"] = word_count
            return SummaryOutput.model_validate(data)


        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            # Retry once with a stricter reminder in the user message
            user_message = user_message + (
                "\n\nIMPORTANT: Your previous response was not valid JSON. "
                "Return ONLY a raw JSON object — no markdown, no prose."
            )

    raise SummarizationError(
        f"Groq returned invalid structured output after 2 attempts: {last_error}"
    )
