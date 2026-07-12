# SmartSummarizer

A Python CLI tool that takes any URL — YouTube video, blog post, news article, or generic webpage — extracts the content, and returns a structured JSON summary powered by the [Groq API](https://console.groq.com/).

## How It Works

```
URL → extractor.py → summarizer.py (Groq) → Pydantic validation → JSON
```

1. **Extract** — Route the URL to the best strategy:
   - **YouTube** → `youtube-transcript-api` (captions) + oEmbed (title)
   - **Articles** → `newspaper3k` (news/blogs)
   - **Fallback** → `requests` + `BeautifulSoup` (`<title>` and `<p>` tags)
2. **Summarize** — Send extracted text to Groq with a structured JSON prompt
3. **Validate** — Parse and validate the response with Pydantic before output

Progress messages go to **stderr**; JSON goes to **stdout** or `--output`.

## Features

- YouTube transcript extraction (manual or auto-generated captions)
- News and blog extraction via `newspaper3k`
- Generic webpage fallback via BeautifulSoup
- Structured JSON output with sentiment and key points
- Pydantic validation and one automatic retry on invalid JSON
- Local `word_count` (not guessed by the model)

## Output Format

```json
{
  "title": "Once you get money, upgrade these 10 things immediately",
  "key_points": [
    "Upgrade sleep setup for better mental health",
    "Invest in health access and pension contributions"
  ],
  "sentiment": "positive",
  "summary": "The video discusses 10 upgrades to make once you start earning more...",
  "source_type": "youtube",
  "word_count": 3087
}
```

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Extracted or inferred title |
| `key_points` | string[] | 3–5 key points |
| `sentiment` | `"positive"` \| `"neutral"` \| `"negative"` | Overall tone |
| `summary` | string | 3–5 sentence summary |
| `source_type` | `"youtube"` \| `"article"` \| `"webpage"` | Extraction method used |
| `word_count` | integer | Words in the raw extracted text |

## Requirements

- Python 3.10+
- [Groq API key](https://console.groq.com/)

## Setup

```bash
cd SmartSummarizer

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and set GROQ_API_KEY=<your-key>
```

## Usage

```bash
# Summarize a YouTube video
python -m smartsummarizer https://www.youtube.com/watch?v=RaLlpEQv_LA

# Summarize an article or webpage
python -m smartsummarizer https://techcrunch.com/some-article

# Save to a file
python -m smartsummarizer https://www.youtube.com/watch?v=RaLlpEQv_LA --output result.json

# Use a different Groq model
python -m smartsummarizer https://example.com --model openai/gpt-oss-120b
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `url` | URL to summarize (required) | — |
| `--model` | Groq model ID | `llama-3.3-70b-versatile` |
| `--output` | Write JSON to file instead of stdout | stdout |

### Supported Groq Models

| Model | Best for |
|-------|----------|
| `llama-3.3-70b-versatile` | Default — balanced quality and speed |
| `openai/gpt-oss-20b` | Fast, free-tier friendly |
| `openai/gpt-oss-120b` | Long or complex content |

See [Groq deprecations](https://console.groq.com/docs/deprecations) for current model availability.

## Project Structure

```
SmartSummarizer/
├── .env.example
├── requirements.txt
├── README.md
├── smartsummarizer/
│   ├── __init__.py
│   ├── __main__.py       # python -m smartsummarizer
│   ├── cli.py            # CLI entry point
│   ├── extractor.py      # URL routing + content extraction
│   ├── summarizer.py     # Groq API + JSON validation
│   └── models.py         # Pydantic schemas
└── tests/
    ├── test_extractor.py
    └── test_summarizer.py
```

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Limitations

- **YouTube** — Requires captions; videos with transcripts disabled will fail
- **JavaScript pages** — BS4 fallback only reads static HTML
- **Long content** — Text is truncated to ~24,000 characters before sending to Groq

## Tech Stack

| Package | Purpose |
|---------|---------|
| `groq` | LLM summarization |
| `youtube-transcript-api` | YouTube captions |
| `newspaper3k` | Article extraction |
| `requests` + `beautifulsoup4` | Webpage fallback |
| `pydantic` | JSON validation |
| `python-dotenv` | Load `GROQ_API_KEY` from `.env` |
