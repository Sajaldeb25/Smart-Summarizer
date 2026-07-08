# SmartSummarizer

A Python CLI tool that takes any URL — YouTube video, blog post, news article, or generic webpage — extracts the content, and returns a structured JSON summary powered by the [Groq API](https://console.groq.com/).

## How It Works

```
URL → extractor.py (route by URL type) → summarizer.py (Groq API) → Pydantic validation → JSON output
```
