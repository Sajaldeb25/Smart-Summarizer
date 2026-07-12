"""Tests for smartsummarizer.summarizer — Groq call and Pydantic validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from smartsummarizer.models import ExtractedContent, SummaryOutput
from smartsummarizer.summarizer import SummarizationError, _parse_groq_response, summarize

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PAYLOAD = {
    "title": "Test Article",
    "key_points": ["Point one", "Point two", "Point three"],
    "sentiment": "positive",
    "summary": "This is a summary. It has multiple sentences. Here is a third.",
    "source_type": "article",
    "word_count": 42,
}

SAMPLE_CONTENT = ExtractedContent(
    title="Test Article",
    text="word " * 42,
    source_type="article",
)


def _make_groq_response(content: str) -> MagicMock:
    """Build a mock Groq chat completion response."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# JSON parsing edge cases
# ---------------------------------------------------------------------------

class TestParseGroqResponse:
    def test_parses_json_with_literal_newlines_in_strings(self):
        raw = (
            '{"title": "HSC exams", "key_points": ["Point one"], '
            '"sentiment": "neutral", "summary": "Line one\\nLine two", '
            '"source_type": "article", "word_count": 100}'
        )
        # Simulate model returning unescaped newline (invalid strict JSON)
        raw = raw.replace("\\n", "\n")
        data = _parse_groq_response(raw)
        assert "Line one" in data["summary"]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestSummarizeSuccess:
    @patch("smartsummarizer.summarizer.Groq")
    def test_valid_json_returns_summary_output(self, MockGroq):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            json.dumps(VALID_PAYLOAD)
        )
        MockGroq.return_value = mock_client

        result = summarize(SAMPLE_CONTENT, api_key="test-key")

        assert isinstance(result, SummaryOutput)
        assert result.title == "Test Article"
        assert result.sentiment == "positive"
        assert result.source_type == "article"
        assert isinstance(result.key_points, list)
        assert len(result.key_points) >= 1

    @patch("smartsummarizer.summarizer.Groq")
    def test_word_count_is_overridden_with_local_value(self, MockGroq):
        payload = {**VALID_PAYLOAD, "word_count": 9999}
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            json.dumps(payload)
        )
        MockGroq.return_value = mock_client

        result = summarize(SAMPLE_CONTENT, api_key="test-key")
        # word_count must be the locally computed value, not the model's hallucination
        assert result.word_count == len(SAMPLE_CONTENT.text.split())

    @patch("smartsummarizer.summarizer.Groq")
    def test_strips_markdown_fence_from_response(self, MockGroq):
        fenced = f"```json\n{json.dumps(VALID_PAYLOAD)}\n```"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(fenced)
        MockGroq.return_value = mock_client

        result = summarize(SAMPLE_CONTENT, api_key="test-key")
        assert isinstance(result, SummaryOutput)


# ---------------------------------------------------------------------------
# Retry on invalid JSON
# ---------------------------------------------------------------------------

class TestSummarizeRetry:
    @patch("smartsummarizer.summarizer.Groq")
    def test_retries_once_on_invalid_json_then_succeeds(self, MockGroq):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_groq_response("not valid json at all"),
            _make_groq_response(json.dumps(VALID_PAYLOAD)),
        ]
        MockGroq.return_value = mock_client

        result = summarize(SAMPLE_CONTENT, api_key="test-key")
        assert isinstance(result, SummaryOutput)
        assert mock_client.chat.completions.create.call_count == 2

    @patch("smartsummarizer.summarizer.Groq")
    def test_raises_after_two_failed_attempts(self, MockGroq):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_groq_response("bad json #1"),
            _make_groq_response("bad json #2"),
        ]
        MockGroq.return_value = mock_client

        with pytest.raises(SummarizationError, match="2 attempts"):
            summarize(SAMPLE_CONTENT, api_key="test-key")


# ---------------------------------------------------------------------------
# Missing API key
# ---------------------------------------------------------------------------

class TestSummarizeMissingKey:
    def test_raises_when_api_key_absent(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with pytest.raises(SummarizationError, match="GROQ_API_KEY"):
            summarize(SAMPLE_CONTENT, api_key=None)


# ---------------------------------------------------------------------------
# Pydantic validation — invalid field values
# ---------------------------------------------------------------------------

class TestSummaryOutputValidation:
    def test_invalid_sentiment_raises_validation_error(self):
        bad = {**VALID_PAYLOAD, "sentiment": "ecstatic"}
        with pytest.raises(Exception):
            SummaryOutput.model_validate(bad)

    def test_invalid_source_type_raises_validation_error(self):
        bad = {**VALID_PAYLOAD, "source_type": "twitter"}
        with pytest.raises(Exception):
            SummaryOutput.model_validate(bad)

    def test_negative_word_count_raises_validation_error(self):
        bad = {**VALID_PAYLOAD, "word_count": -1}
        with pytest.raises(Exception):
            SummaryOutput.model_validate(bad)

    def test_valid_payload_passes(self):
        result = SummaryOutput.model_validate(VALID_PAYLOAD)
        assert result.title == VALID_PAYLOAD["title"]
