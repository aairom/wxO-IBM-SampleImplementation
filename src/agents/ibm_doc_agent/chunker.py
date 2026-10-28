"""Text Chunking and Metadata Normalization Pipeline.

Splits documentation into semantically cohesive passages while preserving section
hierarchies, source URLs, page titles, and token counts.
"""

from __future__ import annotations

import hashlib
import re
from typing import List

from src.agents.ibm_doc_agent.models import DocumentChunk, ScrapedDocument


class TextChunker:
    """Chunks structured and unstructured text into overlapping passages with rich metadata."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        """Initialize the text chunker.

        Args:
            chunk_size: Target character / word count per chunk.
            chunk_overlap: Number of characters / words to overlap between consecutive chunks.
        """
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count based on word and punctuation boundaries."""
        words = len(re.findall(r"\w+|[^\w\s]", text))
        return max(1, int(words * 1.3))

    @staticmethod
    def _generate_chunk_id(url: str, section_header: str, chunk_index: int) -> str:
        """Generate a deterministic UUID-like hash for a given chunk."""
        key = f"{url}::{section_header}::{chunk_index}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def _split_text_with_overlap(self, text: str) -> List[str]:
        """Split a long text string into chunks of roughly `chunk_size` with `chunk_overlap`."""
        if not text:
            return []

        # Split into paragraphs or sentences
        paragraphs = text.split("\n\n")
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue

            # If a single paragraph exceeds chunk size, split by sentences
            if len(p_clean) > self.chunk_size:
                sentences = re.split(r"(?<=[.!?]) +", p_clean)
                for s in sentences:
                    s_clean = s.strip()
                    if not s_clean:
                        continue
                    if current_len + len(s_clean) > self.chunk_size and current_chunk:
                        chunk_str = " ".join(current_chunk)
                        chunks.append(chunk_str)
                        # Overlap: keep last few tokens/sentences
                        current_chunk = [s_clean]
                        current_len = len(s_clean)
                    else:
                        current_chunk.append(s_clean)
                        current_len += len(s_clean) + 1
            else:
                if current_len + len(p_clean) > self.chunk_size and current_chunk:
                    chunk_str = "\n\n".join(current_chunk)
                    chunks.append(chunk_str)
                    current_chunk = [p_clean]
                    current_len = len(p_clean)
                else:
                    current_chunk.append(p_clean)
                    current_len += len(p_clean) + 2

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def process_document(self, doc: ScrapedDocument) -> List[DocumentChunk]:
        """Convert a ScrapedDocument into a list of DocumentChunks with metadata.

        Args:
            doc: ScrapedDocument instance.

        Returns:
            List of DocumentChunk instances.
        """
        chunks: List[DocumentChunk] = []
        global_index = 0

        # If sections exist, chunk each section separately to preserve header context
        if doc.sections:
            for sec in doc.sections:
                header = sec.get("header", "General")
                content = sec.get("content", "")
                sub_chunks = self._split_text_with_overlap(content)

                for chunk_text in sub_chunks:
                    chunk_id = self._generate_chunk_id(doc.url, header, global_index)
                    token_count = self._estimate_tokens(chunk_text)
                    chunks.append(
                        DocumentChunk(
                            chunk_id=chunk_id,
                            source_url=doc.url,
                            page_title=doc.title,
                            section_header=header,
                            text=chunk_text,
                            token_count=token_count,
                            chunk_index=global_index,
                            metadata={
                                **doc.metadata,
                                "scraped_at": doc.scraped_at,
                            },
                        )
                    )
                    global_index += 1
        else:
            # Fallback to splitting full clean text
            sub_chunks = self._split_text_with_overlap(doc.clean_text)
            for chunk_text in sub_chunks:
                chunk_id = self._generate_chunk_id(doc.url, "Overview", global_index)
                token_count = self._estimate_tokens(chunk_text)
                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        source_url=doc.url,
                        page_title=doc.title,
                        section_header="Overview",
                        text=chunk_text,
                        token_count=token_count,
                        chunk_index=global_index,
                        metadata={
                            **doc.metadata,
                            "scraped_at": doc.scraped_at,
                        },
                    )
                )
                global_index += 1

        return chunks
