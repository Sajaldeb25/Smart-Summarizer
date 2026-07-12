"""Orchestrates extraction and summarization for the web API."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..extractor import ExtractionError, extract
from ..models import SummaryOutput
from ..summarizer import DEFAULT_MODEL, SummarizationError, summarize


class WebServiceError(Exception):
    """Base error for web service operations."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SummaryResult:
    url: str
    model: str
    title: str
    source_type: str
    sentiment: str
    summary: str
    key_points: list[str]
    word_count: int

    @classmethod
    def from_output(cls, url: str, model: str, output: SummaryOutput) -> SummaryResult:
        return cls(
            url=url,
            model=model,
            title=output.title,
            source_type=output.source_type,
            sentiment=output.sentiment,
            summary=output.summary,
            key_points=output.key_points,
            word_count=output.word_count,
        )


def ensure_api_key() -> None:
    if not os.getenv("GROQ_API_KEY"):
        raise WebServiceError(
            "GROQ_API_KEY is not set. Add it to your environment variables.",
            status_code=503,
        )


def summarize_url(url: str, model: str = DEFAULT_MODEL) -> SummaryResult:
    """Extract and summarize a URL. Results are not persisted."""
    ensure_api_key()
    url = url.strip()
    if not url:
        raise WebServiceError("URL is required.")

    try:
        content = extract(url)
    except ExtractionError as exc:
        raise WebServiceError(str(exc), status_code=422) from exc

    try:
        result = summarize(content, model=model)
    except SummarizationError as exc:
        raise WebServiceError(str(exc), status_code=502) from exc

    return SummaryResult.from_output(url, model, result)
