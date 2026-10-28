"""Documentation models and data structures for IBM Doc Agent."""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScrapedDocument:
    """Represents a raw scraped document from an IBM documentation source."""

    url: str
    title: str
    raw_html: str
    clean_text: str
    sections: List[Dict[str, str]] = field(default_factory=list)
    scraped_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert scraped document to dictionary."""
        return asdict(self)


@dataclass
class DocumentChunk:
    """Represents a single chunk of text prepared for vector embedding and retrieval."""

    chunk_id: str
    source_url: str
    page_title: str
    section_header: str
    text: str
    token_count: int
    chunk_index: int
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary."""
        return asdict(self)
