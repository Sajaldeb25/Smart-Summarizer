from typing import Literal

from pydantic import BaseModel, Field


class SummaryOutput(BaseModel):
    title: str = Field(description="Extracted or inferred title of the content")
    key_points: list[str] = Field(
        min_length=1,
        description="List of 3–5 key points from the content",
    )
    sentiment: Literal["positive", "neutral", "negative"] = Field(
        description="Overall sentiment of the content"
    )
    summary: str = Field(description="Concise 3–5 sentence summary of the content")
    source_type: Literal["youtube", "article", "webpage"] = Field(
        description="Type of the source URL"
    )
    word_count: int = Field(ge=0, description="Word count of the extracted raw text")


class ExtractedContent(BaseModel):
    title: str
    text: str
    source_type: Literal["youtube", "article", "webpage"]
