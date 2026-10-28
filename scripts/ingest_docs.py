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
from src.agents.ibm_doc_agent.models import ScrapedDocument
from src.agents.ibm_doc_agent.scraper import IBMDocScraper
from src.agents.ibm_doc_agent.vector_store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingest_docs")

# Official IBM Bob Documentation URLs (https://bob.ibm.com/docs)
DEFAULT_URLS = [
    "https://bob.ibm.com/docs/overview",
    "https://bob.ibm.com/docs/bob_shell",
    "https://bob.ibm.com/docs/enterprise",
    "https://bob.ibm.com/docs/premium_packages",
    "https://bob.ibm.com/docs/skills",
    "https://bob.ibm.com/docs/mcp",
    "https://bob.ibm.com/docs/security",
    "https://bob.ibm.com/docs/telemetry",
    "https://bob.ibm.com/docs/modes",
    "https://bob.ibm.com/docs/bobcoins",
    "https://bob.ibm.com/docs/bobalytics",
]


def run_ingestion(
    urls: Optional[List[str]] = None,
    local_docs_dir: Optional[str] = "knowledge-bases/docs",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    delay: float = 0.5,
    output_store: str = "knowledge-bases/ibm_doc_store.json",
    report_output: str = "output/ingestion_report.json",
) -> int:
    """Execute scraping, local text ingestion, chunking, and vector indexing pipeline.

    Args:
        urls: Optional target URLs to scrape.
        local_docs_dir: Local documentation directory (e.g. knowledge-bases/docs).
        chunk_size: Character size for chunking.
        chunk_overlap: Overlap characters between chunks.
        delay: Delay between requests in seconds.
        output_store: Path to output JSON vector store.
        report_output: Path to write the timestamped execution report.

    Returns:
        0 on success, non-zero on failure.
    """
    start_time = datetime.datetime.now(datetime.timezone.utc)
    logger.info("Starting documentation ingestion pipeline...")

    scraper = IBMDocScraper(timeout=15, max_retries=3)
    chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    store = VectorStore(storage_path=Path(output_store))

    total_chunks = 0
    scraped_docs = []
    errors = []

    # 1. Ingest local documentation files if present
    local_dir = Path(local_docs_dir) if local_docs_dir else None
    if local_dir and local_dir.exists():
        logger.info("Ingesting local documentation from %s...", local_dir)
        for doc_file in sorted(local_dir.glob("*.txt")):
            try:
                content = doc_file.read_text(encoding="utf-8")
                doc_title = doc_file.stem.replace("_", " ").title()
                source_url = f"https://bob.ibm.com/docs/{doc_file.stem}"
                
                # Extract first heading if present
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                if lines and lines[0].startswith("# "):
                    doc_title = lines[0].replace("# ", "")

                doc = ScrapedDocument(
                    url=source_url,
                    title=f"IBM Bob — {doc_title}",
                    raw_html="",
                    clean_text=content,
                    sections=[{"header": doc_title, "content": content}],
                    metadata={"source": "local_doc", "filename": doc_file.name},
                )
                scraped_docs.append(doc)
                chunks = chunker.process_document(doc)
                added = store.add_chunks(chunks)
                total_chunks += added
                logger.info("Indexed %d chunks from %s", added, doc_file.name)
            except Exception as exc:
                err = f"Failed processing {doc_file}: {exc}"
                logger.error(err)
                errors.append({"file": str(doc_file), "error": str(exc)})

    # 2. Ingest remote URLs if provided
    if urls:
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
        default=None,
        help="List of external IBM documentation URLs to scrape and index.",
    )
    parser.add_argument(
        "--local-dir",
        default="knowledge-bases/docs",
        help="Path to local documentation files (default: knowledge-bases/docs).",
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
        local_docs_dir=args.local_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        delay=args.delay,
        output_store=args.store_path,
        report_output=args.report,
    )


if __name__ == "__main__":
    sys.exit(main())
