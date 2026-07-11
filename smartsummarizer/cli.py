"""CLI entry point for SmartSummarizer."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from .extractor import ExtractionError, extract
from .summarizer import DEFAULT_MODEL, SummarizationError, summarize


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smartsummarizer",
        description=(
            "Extract and summarize content from a URL (YouTube, article, or webpage) "
            "using the Groq API."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m smartsummarizer https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
            "  python -m smartsummarizer https://techcrunch.com/article --output result.json\n"
            "  python -m smartsummarizer https://example.com --model llama-3.3-70b-versatile\n"
        ),
    )
    parser.add_argument(
        "url",
        help="URL to summarize (YouTube video, news article, blog post, or any webpage)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        metavar="MODEL",
        help=f"Groq model to use for summarization (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON output to FILE instead of stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """
    CLI entry point for SmartSummarizer.
    Receives a list of strings or None and returns an integer
    if the list is not None, it will be used to parse the arguments
    if the list is None, it will use sys.argv
    load the environment variables from the .env file
    """

    load_dotenv()

    # check if the GROQ_API_KEY is set
    if not os.getenv("GROQ_API_KEY"):
        print(
            "Error: GROQ_API_KEY is not set.\n"
            "Copy .env.example to .env and add your key:\n"
            "  cp .env.example .env\n"
            "  # then edit .env and set GROQ_API_KEY=<your-key>",
            file=sys.stderr,
        )
        return 1

    parser = _build_parser()
    args = parser.parse_args(argv)

    print(f"\n\n\nExtracting content from: {args.url}\n\n\n", file=sys.stderr)
    try:
        content = extract(args.url)
    except ExtractionError as exc:
        print(f"Extraction error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Extracted {len(content.text.split())} words from "
        f"'{content.title}' [{content.source_type}]",
        file=sys.stderr,
    )
    print(f"\n\n\nSummarizing with model '{args.model}'...", file=sys.stderr)

    try:
        result = summarize(content, model=args.model)
    except SummarizationError as exc:
        print(f"Summarization error: {exc}", file=sys.stderr)
        return 1

    output_json = result.model_dump_json(indent=2)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(output_json + "\n")
            print(f"\n\n\nOutput written to: {args.output}\n\n\n", file=sys.stderr)
        except OSError as exc:
            print(f"Failed to write output file '{args.output}': {exc}", file=sys.stderr)
            return 1
    else:
        print(f"\n\n\n{output_json}\n\n\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
