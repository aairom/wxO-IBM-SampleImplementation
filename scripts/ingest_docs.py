#!/usr/bin/env python3
"""ingest_docs.py — Standalone CLI script for scraping and vectorizing live IBM documentation.

Crawls specified IBM documentation URLs, extracts clean structured text, chunks passages,
generates embeddings, and stores them in the watsonx Orchestrate vector store.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import List

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.ibm_doc_agent.chunker import TextChunker
from src.agents.ibm_doc_agent.scraper import IBMDocScraper
from src.agents.ibm_doc_agent.vector_store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingest_docs")

DEFAULT_URLS = [
    "https://www.ibm.com/docs/en/watsonx/watsonx-orchestrate/current?topic=getting-started",
    "https://www.ibm.com/docs/en/watsonx/watsonx-orchestrate/current?topic=building-agents",
    "https://www.ibm.com/docs/en/watsonx/watsonx-ai/current?topic=foundation-models",
]


def run_ingestion(
    urls: List[str],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    delay: float = 0.5,
    output_store: str = "knowledge-bases/ibm_doc_store.json",
    report_output: str = "output/ingestion_report.json",
) -> int:
    """Execute scraping, chunking, and vector ingestion pipeline.

    Args:
        urls: Target URLs to scrape.
        chunk_size: Character size for chunking.
        chunk_overlap: Overlap characters between chunks.
        delay: Delay between requests in seconds.
        output_store: Path to output JSON vector store.
        report_output: Path to write the timestamped execution report.

    Returns:
        0 on success, non-zero on failure.
    """
    start_time = datetime.datetime.now(datetime.timezone.utc)
    logger.info("Starting documentation ingestion pipeline for %d URLs...", len(urls))

    scraper = IBMDocScraper(timeout=15, max_retries=3)
    chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    store = VectorStore(storage_path=Path(output_store))

    total_chunks = 0
    scraped_docs = []
    errors = []

    for url in urls:
        logger.info("Processing documentation URL: %s", url)
        try:
            doc = scraper.scrape_url(url)
            scraped_docs.append(doc)
            chunks = chunker.process_document(doc)
            added = store.add_chunks(chunks)
            total_chunks += added
            logger.info("Generated and indexed %d chunks for %s", added, url)
        except Exception as exc:
            error_msg = f"Failed processing {url}: {exc}"
            logger.error(error_msg)
            errors.append({"url": url, "error": str(exc)})

    end_time = datetime.datetime.now(datetime.timezone.utc)
    duration_secs = (end_time - start_time).total_seconds()

    report = {
        "status": "success" if not errors else "partial_success",
        "started_at": start_time.isoformat(),
        "completed_at": end_time.isoformat(),
        "duration_seconds": round(duration_secs, 2),
        "total_urls_processed": len(scraped_docs),
        "total_chunks_indexed": total_chunks,
        "vector_store_path": output_store,
        "documents": [
            {
                "url": d.url,
                "title": d.title,
                "sections_count": len(d.sections),
                "text_length": len(d.clean_text),
            }
            for d in scraped_docs
        ],
        "errors": errors,
    }

    report_path = Path(report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Ingestion completed in %.2fs. Report written to %s", duration_secs, report_path)
    return 0 if not errors else 1


def main() -> int:
    """CLI entrypoint for doc ingestion."""
    parser = argparse.ArgumentParser(
        description="Scrape and index live IBM documentation into watsonx Orchestrate vector store."
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        default=DEFAULT_URLS,
        help="List of IBM documentation URLs to scrape and index.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Max character size per chunk (default: 500).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Overlap character count between chunks (default: 50).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between scrape requests (default: 0.5).",
    )
    parser.add_argument(
        "--store-path",
        default="knowledge-bases/ibm_doc_store.json",
        help="Output path for the vector store index file.",
    )
    parser.add_argument(
        "--report",
        default="output/ingestion_report.json",
        help="Path for timestamped JSON report.",
    )

    args = parser.parse_args()
    return run_ingestion(
        urls=args.urls,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        delay=args.delay,
        output_store=args.store_path,
        report_output=args.report,
    )


if __name__ == "__main__":
    sys.exit(main())
