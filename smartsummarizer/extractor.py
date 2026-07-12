"""URL content extraction with routing for YouTube, articles, and generic webpages."""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# youtube_transcript_api is used to extract the transcript from a YouTube video
try:
    from youtube_transcript_api import (
        IpBlocked,
        NoTranscriptFound,
        RequestBlocked,
        TranscriptsDisabled,
        YouTubeTranscriptApi,
    )
    from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig
    _YOUTUBE_AVAILABLE = True
except ImportError:
    _YOUTUBE_AVAILABLE = False
    YouTubeTranscriptApi = None  # type: ignore[assignment]
    TranscriptsDisabled = None  # type: ignore[assignment]
    NoTranscriptFound = None  # type: ignore[assignment]
    IpBlocked = None  # type: ignore[assignment]
    RequestBlocked = None  # type: ignore[assignment]
    GenericProxyConfig = None  # type: ignore[assignment]
    WebshareProxyConfig = None  # type: ignore[assignment]

# newspaper3k is used to extract the content from a webpage
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


SUPADATA_TRANSCRIPT_URL = "https://api.supadata.ai/v1/youtube/transcript"


def _parse_supadata_transcript(data: object) -> str:
    """Parse transcript text from Supadata API JSON response."""
    if isinstance(data, str):
        return data.strip()

    if not isinstance(data, dict):
        raise ExtractionError("Unexpected Supadata response format.")

    content = data.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            segment.get("text", "") for segment in content if isinstance(segment, dict)
        ).strip()

    if isinstance(data.get("text"), str):
        return data["text"].strip()

    raise ExtractionError("Supadata returned no transcript content.")


def _fetch_youtube_transcript_supadata(video_id: str, api_key: str) -> str:
    """Fetch transcript via Supadata (works on cloud hosts; free tier: 100 req/month)."""
    logger.info("Supadata: fetching transcript for video_id=%s", video_id)
    try:
        resp = requests.get(
            SUPADATA_TRANSCRIPT_URL,
            params={"videoId": video_id, "text": "true"},
            headers={"x-api-key": api_key},
            timeout=45,
        )
    except requests.RequestException as exc:
        logger.error("Supadata: network error for video_id=%s — %s", video_id, exc)
        raise ExtractionError(f"Supadata request failed: {exc}") from exc

    logger.info(
        "Supadata: response video_id=%s status=%s content_length=%s",
        video_id,
        resp.status_code,
        len(resp.content),
    )

    if resp.status_code == 401:
        logger.error("Supadata: invalid API key (401) for video_id=%s", video_id)
        raise ExtractionError("Invalid SUPADATA_API_KEY.")
    if resp.status_code == 404:
        logger.warning("Supadata: no transcript (404) for video_id=%s", video_id)
        raise ExtractionError(
            f"No transcript found for video '{video_id}'. "
            "The video may not have captions available."
        )
    if resp.status_code == 429:
        logger.error("Supadata: rate limit (429) for video_id=%s", video_id)
        raise ExtractionError(
            "Supadata rate limit reached (free tier: 100 credits/month, 1 req/sec). "
            "Try again later or upgrade your Supadata plan."
        )
    if not resp.ok:
        detail = resp.text[:300] if resp.text else resp.reason
        logger.error(
            "Supadata: API error video_id=%s status=%s detail=%s",
            video_id,
            resp.status_code,
            detail,
        )
        raise ExtractionError(f"Supadata API error ({resp.status_code}): {detail}")

    try:
        data = resp.json()
    except ValueError:
        if resp.text.strip():
            word_count = len(resp.text.split())
            logger.info(
                "Supadata: plain-text transcript OK video_id=%s words=%s",
                video_id,
                word_count,
            )
            return resp.text.strip()
        logger.error("Supadata: non-JSON empty response for video_id=%s", video_id)
        raise ExtractionError("Supadata returned a non-JSON response.") from None

    text = _parse_supadata_transcript(data)
    logger.info(
        "Supadata: transcript OK video_id=%s words=%s chars=%s",
        video_id,
        len(text.split()),
        len(text),
    )
    return text


def _youtube_ip_blocked_message() -> str:
    return (
        "YouTube blocked this request because the server runs on a cloud IP "
        "(common on Render, AWS, etc.). Set SUPADATA_API_KEY on your host for YouTube "
        "in production (100 free requests/month at supadata.ai), or run the CLI locally."
    )


def _create_youtube_api() -> YouTubeTranscriptApi:
    """Build YouTubeTranscriptApi, optionally routing through a proxy."""
    proxy_url = os.getenv("YOUTUBE_PROXY_URL", "").strip()
    webshare_user = os.getenv("WEBSHARE_PROXY_USERNAME", "").strip()
    webshare_pass = os.getenv("WEBSHARE_PROXY_PASSWORD", "").strip()

    if webshare_user and webshare_pass:
        proxy_config = WebshareProxyConfig(
            proxy_username=webshare_user,
            proxy_password=webshare_pass,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_config)

    if proxy_url:
        proxy_config = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)
        return YouTubeTranscriptApi(proxy_config=proxy_config)

    return YouTubeTranscriptApi()


def _fetch_youtube_transcript_local(video_id: str) -> str:
    """Fetch transcript via youtube-transcript-api (free; blocked on many cloud IPs)."""
    if not _YOUTUBE_AVAILABLE:
        raise ExtractionError("youtube-transcript-api is not installed.")

    api = _create_youtube_api()
    transcript_list = api.list(video_id)
    available_langs = [t.language_code for t in transcript_list]
    try:
        transcript = transcript_list.find_manually_created_transcript(available_langs)
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(available_langs)
    fetched = transcript.fetch()
    return " ".join(snippet.text for snippet in fetched)


def _extract_youtube(url: str, video_id: str) -> ExtractedContent:
    """Extract transcript and title from a YouTube video.

    Uses Supadata when SUPADATA_API_KEY is set (recommended for Render/production).
    Otherwise uses youtube-transcript-api (works locally).
    """
    supadata_key = os.getenv("SUPADATA_API_KEY", "").strip()
    text = ""

    if supadata_key:
        logger.info(
            "YouTube extract: using Supadata (video_id=%s, api_key_set=True)",
            video_id,
        )
        try:
            text = _fetch_youtube_transcript_supadata(video_id, supadata_key)
            logger.info("YouTube extract: Supadata succeeded for video_id=%s", video_id)
        except ExtractionError as exc:
            logger.error(
                "YouTube extract: Supadata failed for video_id=%s — %s",
                video_id,
                exc,
            )
            raise
        except Exception as exc:
            logger.exception(
                "YouTube extract: unexpected Supadata error for video_id=%s",
                video_id,
            )
            raise ExtractionError(f"Supadata transcript fetch failed: {exc}") from exc
    else:
        logger.info(
            "YouTube extract: SUPADATA_API_KEY not set, using youtube-transcript-api "
            "(video_id=%s)",
            video_id,
        )
        try:
            text = _fetch_youtube_transcript_local(video_id)
            logger.info(
                "YouTube extract: local transcript API succeeded for video_id=%s words=%s",
                video_id,
                len(text.split()),
            )
        except TranscriptsDisabled:
            logger.warning("YouTube extract: transcripts disabled for video_id=%s", video_id)
            raise ExtractionError(
                f"Transcripts are disabled for video '{video_id}'. "
                "Try a different video or provide an article URL instead."
            )
        except NoTranscriptFound:
            raise ExtractionError(
                f"No transcript found for video '{video_id}'. "
                "The video may not have captions available."
            )
        except (IpBlocked, RequestBlocked):
            raise ExtractionError(_youtube_ip_blocked_message())
        except Exception as exc:
            if "blocking requests from your IP" in str(exc):
                raise ExtractionError(_youtube_ip_blocked_message()) from exc
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
        # create an instance of the Article class
        article = Article(url)
        article.download()
        article.parse()
    except ArticleException as exc:
        raise ExtractionError(f"newspaper3k failed to parse '{url}': {exc}") from exc
    except Exception as exc:
        raise ExtractionError(f"newspaper3k encountered an unexpected error: {exc}") from exc

    # get the text of the article
    text = article.text.strip()

    # check if the text is empty
    if not text:
        raise ExtractionError(f"newspaper3k extracted empty text from '{url}'.")

    # get the title of the article
    title = article.title.strip() or _infer_title_from_url(url)

    # return the extracted content with verification by ExtractedContent class
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

    #four method for four types of urls 

    video_id = _extract_youtube_video_id(url)
    if video_id:
        return _extract_youtube(url, video_id)

    try:
        return _extract_article(url)
    except ExtractionError:
        # newspaper3k could not handle it; fall through to generic scraper
        pass

    return _extract_webpage(url)
