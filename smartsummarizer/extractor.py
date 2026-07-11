"""URL content extraction with routing for YouTube, articles, and generic webpages."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from youtube_transcript_api import (
        NoTranscriptFound,
        TranscriptsDisabled,
        YouTubeTranscriptApi,
    )
    _YOUTUBE_AVAILABLE = True
except ImportError:
    _YOUTUBE_AVAILABLE = False
    YouTubeTranscriptApi = None  # type: ignore[assignment]
    TranscriptsDisabled = None  # type: ignore[assignment]
    NoTranscriptFound = None  # type: ignore[assignment]

try:
    from newspaper import Article, ArticleException
    _NEWSPAPER_AVAILABLE = True
except ImportError:
    _NEWSPAPER_AVAILABLE = False
    Article = None  # type: ignore[assignment,misc]
    ArticleException = None  # type: ignore[assignment]

from .models import ExtractedContent


class ExtractionError(Exception):
    """Raised when content cannot be extracted from a URL."""


def _extract_youtube_video_id(url: str) -> str | None:
    """Return the YouTube video ID from a URL, or None if not a YouTube URL."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().lstrip("www.")

    if netloc == "youtube.com" or netloc == "m.youtube.com":
        qs = parse_qs(parsed.query)
        video_ids = qs.get("v")
        if video_ids:
            return video_ids[0]
        # Handle /shorts/<id> and /embed/<id> paths
        match = re.match(r"^/(?:shorts|embed|v)/([A-Za-z0-9_-]{11})", parsed.path)
        if match:
            return match.group(1)

    if netloc == "youtu.be":
        path = parsed.path.lstrip("/")
        if path:
            return path.split("/")[0]

    return None


def _fetch_youtube_title(video_id: str) -> str:
    """Fetch the video title via YouTube's oEmbed endpoint (no API key needed)."""
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=10,
        )
        if resp.ok:
            return resp.json().get("title", f"YouTube Video ({video_id})")
    except requests.RequestException:
        pass
    return f"YouTube Video ({video_id})"


def _extract_youtube(url: str, video_id: str) -> ExtractedContent:
    """Extract transcript and title from a YouTube video.

    Uses the youtube-transcript-api v1.x instance-based API:
      YouTubeTranscriptApi().list(video_id) → TranscriptList
      transcript_list.find_transcript([...]).fetch() → FetchedTranscript
    """
    if not _YOUTUBE_AVAILABLE:
        raise ExtractionError("youtube-transcript-api is not installed.")

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        # Prefer manually-created transcripts, then fall back to auto-generated,
        # across any available language.
        available_langs = [t.language_code for t in transcript_list]
        try:
            transcript = transcript_list.find_manually_created_transcript(available_langs)
        except NoTranscriptFound:
            transcript = transcript_list.find_generated_transcript(available_langs)
        fetched = transcript.fetch()
        text = " ".join(snippet.text for snippet in fetched)
    except TranscriptsDisabled:
        raise ExtractionError(
            f"Transcripts are disabled for video '{video_id}'. "
            "Try a different video or provide an article URL instead."
        )
    except NoTranscriptFound:
        raise ExtractionError(
            f"No transcript found for video '{video_id}'. "
            "The video may not have captions available."
        )
    except Exception as exc:
        raise ExtractionError(f"Failed to fetch YouTube transcript: {exc}") from exc

    if not text.strip():
        raise ExtractionError(f"Transcript for video '{video_id}' is empty.")

    title = _fetch_youtube_title(video_id)
    return ExtractedContent(title=title, text=text, source_type="youtube")


def _extract_article(url: str) -> ExtractedContent:
    """Extract content using newspaper3k."""
    if not _NEWSPAPER_AVAILABLE:
        raise ExtractionError("newspaper3k is not installed.")

    try:
        article = Article(url)
        article.download()
        article.parse()
    except ArticleException as exc:
        raise ExtractionError(f"newspaper3k failed to parse '{url}': {exc}") from exc
    except Exception as exc:
        raise ExtractionError(f"newspaper3k encountered an unexpected error: {exc}") from exc

    text = article.text.strip()
    if not text:
        raise ExtractionError(f"newspaper3k extracted empty text from '{url}'.")

    title = article.title.strip() or _infer_title_from_url(url)
    return ExtractedContent(title=title, text=text, source_type="article")


def _infer_title_from_url(url: str) -> str:
    """Derive a human-readable title from a URL path as a last resort."""
    path = urlparse(url).path.rstrip("/")
    if path:
        slug = path.split("/")[-1]
        return slug.replace("-", " ").replace("_", " ").title()
    return url


def _extract_webpage(url: str) -> ExtractedContent:
    """Fallback extraction using requests + BeautifulSoup."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; SmartSummarizer/1.0; "
                "+https://github.com/smartsummarizer)"
            )
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ExtractionError(
            f"HTTP {exc.response.status_code} when fetching '{url}'."
        ) from exc
    except requests.ConnectionError as exc:
        raise ExtractionError(f"Connection error fetching '{url}': {exc}") from exc
    except requests.Timeout:
        raise ExtractionError(f"Request timed out fetching '{url}'.")
    except requests.RequestException as exc:
        raise ExtractionError(f"Network error fetching '{url}': {exc}") from exc

    soup = BeautifulSoup(response.text, "lxml")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else _infer_title_from_url(url)

    paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
    text = " ".join(p for p in paragraphs if p)

    if not text.strip():
        raise ExtractionError(
            f"Could not extract any text content from '{url}'. "
            "The page may require JavaScript to render."
        )

    return ExtractedContent(title=title, text=text, source_type="webpage")


def extract(url: str) -> ExtractedContent:
    """
    Route the URL to the appropriate extraction strategy and return
    an ExtractedContent with title, text, and source_type.

    Routing order:
    1. YouTube (youtube.com / youtu.be)  →  youtube-transcript-api
    2. Non-YouTube                        →  newspaper3k
    3. newspaper3k failure                →  requests + BeautifulSoup fallback
    """
    url = url.strip()

    video_id = _extract_youtube_video_id(url)
    if video_id:
        return _extract_youtube(url, video_id)

    try:
        return _extract_article(url)
    except ExtractionError:
        # newspaper3k could not handle it; fall through to generic scraper
        pass

    return _extract_webpage(url)
