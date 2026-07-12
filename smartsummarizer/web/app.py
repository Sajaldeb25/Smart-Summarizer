"""FastAPI application for the SmartSummarizer web UI."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from ..summarizer import DEFAULT_MODEL
from .service import WebServiceError, summarize_url

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="SmartSummarizer",
    description="Summarize URLs from YouTube, articles, and web pages",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SummarizeRequest(BaseModel):
    url: HttpUrl
    model: str = Field(default=DEFAULT_MODEL)


class SummaryResponse(BaseModel):
    url: str
    model: str
    title: str
    source_type: str
    sentiment: str
    summary: str
    key_points: list[str]
    word_count: int


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/summarize", response_model=SummaryResponse)
def api_summarize(body: SummarizeRequest) -> SummaryResponse:
    try:
        result = summarize_url(str(body.url), model=body.model)
    except WebServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SummaryResponse(**result.__dict__)
