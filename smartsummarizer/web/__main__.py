"""Run the SmartSummarizer web server."""

import os

import uvicorn


def main() -> None:
    reload = os.getenv("ENV", "development") != "production"
    uvicorn.run(
        "smartsummarizer.web.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=reload,
    )


if __name__ == "__main__":
    main()
