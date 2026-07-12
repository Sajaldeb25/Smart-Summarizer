# SmartSummarizer

A Python tool that takes any URL — YouTube video, blog post, news article, or generic webpage — extracts the content, and returns a structured JSON summary powered by the [Groq API](https://console.groq.com/).

Use it from the **CLI** or the **web UI**. Paste a link, get an instant summary. Nothing is stored on the server.

**Live demo:** [https://smart-summarizer-ux12.onrender.com/](https://smart-summarizer-ux12.onrender.com/)

> On Render's free tier, the app **spins down after ~15 minutes of inactivity**. The first visit after that may take **up to ~1 minute** to load while the server wakes up. Later requests are fast until it idles again.

## How It Works

```
URL → extractor.py → summarizer.py (Groq) → Pydantic validation → JSON
```

1. **Extract** — Route the URL to the best strategy:
   - **YouTube** → [Supadata](https://supadata.ai) when `SUPADATA_API_KEY` is set (production), otherwise `youtube-transcript-api` (local)
   - **Articles** → `newspaper3k` (news/blogs)
   - **Fallback** → `requests` + `BeautifulSoup` (`<title>` and `<p>` tags)
2. **Summarize** — Send extracted text to Groq with structured JSON output (`response_format: json_object`)
3. **Validate** — Parse with Pydantic and return the result

CLI: progress on **stderr**, JSON on **stdout** or `--output`.  
Web UI: result shown in the browser (stateless, no database).

## Features

- YouTube transcript extraction (Supadata on cloud, free API locally)
- News and blog extraction via `newspaper3k`
- Generic webpage fallback via BeautifulSoup
- Structured JSON with title, key points, sentiment, and summary
- Pydantic validation and automatic retry on invalid JSON
- Local `word_count` (computed from extracted text, not guessed by the model)
- Web UI + REST API (FastAPI)
- Deploy-ready for [Render](https://render.com) via `render.yaml`

## Output Format

```json
{
  "title": "HSC exams to continue nationwide, except under Chattogram Board",
  "key_points": [
    "Exams continue under eight boards as scheduled",
    "Chattogram Board exams postponed due to floods"
  ],
  "sentiment": "neutral",
  "summary": "The Bangladesh Inter-Education Board Coordination Committee confirmed...",
  "source_type": "article",
  "word_count": 171
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
- [Groq API key](https://console.groq.com/) (required)
- [Supadata API key](https://supadata.ai) (optional — for YouTube on cloud hosts)

## Setup

```bash
cd SmartSummarizer

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env — at minimum set GROQ_API_KEY
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key for summarization |
| `SUPADATA_API_KEY` | For YouTube on Render | [Supadata](https://supadata.ai) key — 100 free requests/month |
| `LOG_LEVEL` | No | Logging level (`INFO`, `DEBUG`) — default `INFO` |
| `YOUTUBE_PROXY_URL` | No | Optional residential proxy (alternative to Supadata) |
| `WEBSHARE_PROXY_USERNAME` | No | Webshare proxy user (with password below) |
| `WEBSHARE_PROXY_PASSWORD` | No | Webshare proxy password |

## CLI Usage

```bash
# Summarize a YouTube video (uses youtube-transcript-api locally)
python -m smartsummarizer https://www.youtube.com/watch?v=RaLlpEQv_LA

# Summarize a news article
python -m smartsummarizer https://www.thedailystar.net/news/bangladesh/education/news/hsc-exams-continue-nationwide-except-under-chattogram-board-4222101

# Save to a file
python -m smartsummarizer https://example.com/article --output result.json

# Use a different Groq model
python -m smartsummarizer https://example.com --model openai/gpt-oss-120b
```

### CLI options

| Option | Description | Default |
|--------|-------------|---------|
| `url` | URL to summarize (required) | — |
| `--model` | Groq model ID | `llama-3.3-70b-versatile` |
| `--output` | Write JSON to file instead of stdout | stdout |

### Supported Groq models

| Model | Best for |
|-------|----------|
| `llama-3.3-70b-versatile` | Default — balanced quality and speed |
| `openai/gpt-oss-20b` | Fast, free-tier friendly |
| `openai/gpt-oss-120b` | Long or complex content |

See [Groq deprecations](https://console.groq.com/docs/deprecations) for current model availability.

## Web UI

```bash
source .venv/bin/activate
python -m smartsummarizer.web
```

Open **http://127.0.0.1:8000** — paste a URL, click **Summarize**, view the result on the right.

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/summarize` | Summarize a URL (`{"url": "...", "model": "..."}`) |
| `GET` | `/health` | Health check |
| `GET` | `/` | Web UI |

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/summarize \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'
```

## Deploy to Render

Stateless — no database required.

### 1. Push to GitHub

Ensure `.env` is **not** committed (it's in `.gitignore`).

### 2. Create a Web Service on Render

Connect your GitHub repo. Render can auto-detect [`render.yaml`](render.yaml).

| Setting | Value |
|---------|--------|
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn smartsummarizer.web.app:app --host 0.0.0.0 --port $PORT` |

> `$PORT` is set automatically by Render — do not hardcode it.

### 3. Environment variables (Render dashboard)

| Variable | Required |
|----------|----------|
| `GROQ_API_KEY` | Yes |
| `SUPADATA_API_KEY` | Yes, for YouTube |
| `ENV` | `production` (optional, set in render.yaml) |
| `LOG_LEVEL` | `INFO` (optional) |

### 4. Redeploy and test

Open your Render URL and try an article URL first, then YouTube (with Supadata key set).

**Cold starts (free tier):** After long inactivity, Render stops the service to save resources. The first request can take **~1 minute** before the site responds; subsequent requests are normal until the next idle period.

> GitHub Pages cannot run this app — it needs a Python server. Keep API keys server-side only.

### YouTube on cloud hosts

YouTube **blocks datacenter IPs** (Render, AWS, etc.). SmartSummarizer handles this automatically:

| Environment | YouTube provider | Setup |
|-------------|------------------|-------|
| **Local** | `youtube-transcript-api` | Free, no extra key |
| **Render / cloud** | [Supadata](https://supadata.ai) | Set `SUPADATA_API_KEY` |

**Supadata free tier:** 100 credits/month, 1 request/sec, no credit card. Each YouTube summary = 1 credit.

1. Sign up at [supadata.ai](https://supadata.ai)
2. Add `SUPADATA_API_KEY` in Render Environment
3. Redeploy

Check Render **Logs** for Supadata status — search for `Supadata:` or `YouTube extract:`.

Docs: [Supadata YouTube transcript API](https://docs.supadata.ai/api-reference/endpoint/youtube/transcript)

**Alternatives:** run the CLI locally for free YouTube, or use a residential proxy (`YOUTUBE_PROXY_URL` / Webshare — see `.env.example`).

| URL type | Works on Render? |
|----------|------------------|
| Articles / blogs / webpages | Yes |
| YouTube | Yes, with `SUPADATA_API_KEY` |

## Project Structure

```
SmartSummarizer/
├── .env.example
├── requirements.txt
├── render.yaml              # Render.com deploy config
├── README.md
├── smartsummarizer/
│   ├── __init__.py
│   ├── __main__.py          # python -m smartsummarizer
│   ├── cli.py               # CLI entry point
│   ├── extractor.py         # URL routing + Supadata / newspaper / BS4
│   ├── summarizer.py        # Groq API + JSON validation
│   ├── models.py            # Pydantic schemas
│   ├── static/              # Web UI (HTML, CSS, JS)
│   └── web/
│       ├── __main__.py      # python -m smartsummarizer.web
│       ├── app.py           # FastAPI routes + logging
│       └── service.py       # Extract + summarize orchestration
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

- **YouTube** — Requires captions; Supadata free tier is 100 requests/month
- **Cloud YouTube** — Blocked without `SUPADATA_API_KEY` or a residential proxy
- **JavaScript pages** — BS4 fallback only reads static HTML
- **Long content** — Text truncated to ~24,000 characters before Groq

## Tech Stack

| Package | Purpose |
|---------|---------|
| `groq` | LLM summarization |
| `youtube-transcript-api` | YouTube captions (local) |
| Supadata API | YouTube captions (cloud production) |
| `newspaper3k` | Article extraction |
| `requests` + `beautifulsoup4` | Webpage fallback |
| `pydantic` | JSON validation |
| `python-dotenv` | Environment variables |
| `fastapi` + `uvicorn` | Web UI and REST API |
