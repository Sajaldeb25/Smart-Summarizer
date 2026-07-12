"""Tests for smartsummarizer.extractor — routing and content extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from smartsummarizer.extractor import (
    ExtractionError,
    _extract_youtube_video_id,
    extract,
)
from smartsummarizer.models import ExtractedContent


# ---------------------------------------------------------------------------
# YouTube video ID parsing
# ---------------------------------------------------------------------------

class TestExtractYoutubeVideoId:
    def test_standard_watch_url(self):
        assert _extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert _extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert _extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_mobile_url(self):
        assert _extract_youtube_video_id("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_non_youtube_returns_none(self):
        assert _extract_youtube_video_id("https://techcrunch.com/article") is None

    def test_empty_string_returns_none(self):
        assert _extract_youtube_video_id("") is None


# ---------------------------------------------------------------------------
# YouTube extraction routing
# ---------------------------------------------------------------------------

class TestExtractYoutube:
    """Tests for youtube-transcript-api v1.x instance-based API."""

    def _make_snippet(self, text: str):
        """Create a mock FetchedTranscriptSnippet with a .text attribute."""
        s = MagicMock()
        s.text = text
        return s

    def _mock_api_instance(self, snippets):
        """
        Build a mock YouTubeTranscriptApi() instance whose .list() returns a
        TranscriptList with a .find_manually_created_transcript() that returns
        a transcript whose .fetch() yields the given snippets.
        """
        fetched = MagicMock()
        fetched.__iter__ = MagicMock(return_value=iter(snippets))

        transcript = MagicMock()
        transcript.language_code = "en"
        transcript.fetch.return_value = fetched

        transcript_list = MagicMock()
        transcript_list.__iter__ = MagicMock(return_value=iter([transcript]))
        transcript_list.find_manually_created_transcript.return_value = transcript

        api_instance = MagicMock()
        api_instance.list.return_value = transcript_list
        return api_instance

    @patch("smartsummarizer.extractor._fetch_youtube_title", return_value="Test Video")
    @patch("smartsummarizer.extractor.YouTubeTranscriptApi")
    @patch("smartsummarizer.extractor._YOUTUBE_AVAILABLE", True)
    def test_youtube_extract_returns_correct_source_type(self, MockApiCls, mock_title):
        snippets = [self._make_snippet("Hello world"), self._make_snippet("This is a test")]
        MockApiCls.return_value = self._mock_api_instance(snippets)
        result = extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result.source_type == "youtube"
        assert result.title == "Test Video"
        assert "Hello world" in result.text

    @patch("smartsummarizer.extractor.YouTubeTranscriptApi")
    @patch("smartsummarizer.extractor._YOUTUBE_AVAILABLE", True)
    def test_youtube_disabled_transcripts_raises(self, MockApiCls):
        from youtube_transcript_api import TranscriptsDisabled
        api_instance = MagicMock()
        api_instance.list.side_effect = TranscriptsDisabled("dQw4w9WgXcQ")
        MockApiCls.return_value = api_instance
        with pytest.raises(ExtractionError, match="disabled"):
            extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    @patch("smartsummarizer.extractor.YouTubeTranscriptApi")
    @patch("smartsummarizer.extractor._YOUTUBE_AVAILABLE", True)
    def test_youtube_no_transcript_raises(self, MockApiCls):
        from youtube_transcript_api import NoTranscriptFound
        api_instance = MagicMock()
        api_instance.list.side_effect = NoTranscriptFound("dQw4w9WgXcQ", ["en"], {})
        MockApiCls.return_value = api_instance
        with pytest.raises(ExtractionError, match="No transcript found"):
            extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


# ---------------------------------------------------------------------------
# Article extraction (newspaper3k)
# ---------------------------------------------------------------------------

class TestExtractArticle:
    @patch("smartsummarizer.extractor.Article")
    @patch("smartsummarizer.extractor._NEWSPAPER_AVAILABLE", True)
    def test_article_extract_success(self, MockArticle):
        mock_article = MagicMock()
        mock_article.title = "Test Article"
        mock_article.text = "This is the article body. " * 20
        MockArticle.return_value = mock_article

        result = extract("https://techcrunch.com/2026/07/test-article")
        assert result.source_type == "article"
        assert result.title == "Test Article"
        assert "article body" in result.text

    @patch("smartsummarizer.extractor._extract_webpage")
    @patch("smartsummarizer.extractor.Article")
    @patch("smartsummarizer.extractor._NEWSPAPER_AVAILABLE", True)
    def test_falls_back_to_webpage_on_article_failure(self, MockArticle, mock_webpage):
        from newspaper import ArticleException

        mock_article = MagicMock()
        mock_article.download.side_effect = ArticleException("download failed")
        MockArticle.return_value = mock_article

        mock_webpage.return_value = ExtractedContent(
            title="Fallback Title",
            text="Fallback text content here.",
            source_type="webpage",
        )
        result = extract("https://example.com/page")
        assert result.source_type == "webpage"
        mock_webpage.assert_called_once()


# ---------------------------------------------------------------------------
# Webpage fallback (BeautifulSoup)
# ---------------------------------------------------------------------------

class TestExtractWebpage:
    @patch("smartsummarizer.extractor.requests.get")
    @patch("smartsummarizer.extractor.Article")
    @patch("smartsummarizer.extractor._NEWSPAPER_AVAILABLE", True)
    def test_webpage_fallback_parses_paragraphs(self, MockArticle, mock_get):
        from newspaper import ArticleException

        mock_article = MagicMock()
        mock_article.download.side_effect = ArticleException("failed")
        MockArticle.return_value = mock_article

        html = (
            "<html><head><title>My Page</title></head><body>"
            "<p>First paragraph.</p><p>Second paragraph.</p>"
            "</body></html>"
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = extract("https://example.com/page")
        assert result.source_type == "webpage"
        assert result.title == "My Page"
        assert "First paragraph" in result.text

    @patch("smartsummarizer.extractor.requests.get")
    @patch("smartsummarizer.extractor.Article")
    @patch("smartsummarizer.extractor._NEWSPAPER_AVAILABLE", True)
    def test_webpage_http_error_raises(self, MockArticle, mock_get):
        from newspaper import ArticleException

        mock_article = MagicMock()
        mock_article.download.side_effect = ArticleException("failed")
        MockArticle.return_value = mock_article

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        http_error = requests.HTTPError(response=mock_resp)
        mock_get.return_value.__enter__ = MagicMock()
        mock_get.side_effect = http_error

        with pytest.raises(ExtractionError, match="404"):
            extract("https://example.com/missing-page")
