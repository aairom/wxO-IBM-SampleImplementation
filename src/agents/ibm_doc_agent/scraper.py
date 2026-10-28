"""Robust Web Scraper for IBM Documentation.

Fetches and cleans live IBM documentation pages using HTTP client with retry logic,
user-agent headers, and HTML parsing via BeautifulSoup.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import urllib.request
import urllib.error

try:
    from bs4 import BeautifulSoup
    HAS_BEAUTIFUL_SOUP = True
except ImportError:
    HAS_BEAUTIFUL_SOUP = False

from src.agents.ibm_doc_agent.models import ScrapedDocument

logger = logging.getLogger("ibm_doc_scraper")


class IBMDocScraper:
    """Scrapes, extracts, and normalizes documentation from IBM documentation portals."""

    DEFAULT_USER_AGENT: str = (
        "Mozilla/5.0 (compatible; IBMWatsonxDocIngestion/1.0; +https://www.ibm.com)"
    )

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: int = 15,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> None:
        """Initialize the scraper.

        Args:
            user_agent: Custom User-Agent header string.
            timeout: Request timeout in seconds.
            max_retries: Number of retry attempts on network failures.
            backoff_factor: Multiplier for exponential backoff between retries.
        """
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def _fetch_url(self, url: str) -> str:
        """Fetch raw HTML content from a URL with retries.

        Args:
            url: Target URL to fetch.

        Returns:
            The raw HTML string content.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        req = urllib.request.Request(url, headers=headers)
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info("Fetching URL (attempt %d/%d): %s", attempt, self.max_retries, url)
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return response.read().decode(charset, errors="replace")
            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "Attempt %d failed for %s: %s", attempt, url, str(exc)
                )
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)

        raise RuntimeError(
            f"Failed to fetch {url} after {self.max_retries} attempts: {last_exception}"
        )

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace and strip unnecessary characters.

        Args:
            text: Raw extracted text.

        Returns:
            Cleaned and normalized text.
        """
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def scrape_url(self, url: str) -> ScrapedDocument:
        """Scrape and parse a single IBM documentation URL.

        Args:
            url: URL of the documentation page.

        Returns:
            ScrapedDocument containing cleaned text, structure, and metadata.
        """
        raw_html = self._fetch_url(url)
        return self.parse_html(raw_html, url)

    def parse_html(self, raw_html: str, url: str) -> ScrapedDocument:
        """Parse raw HTML string and extract clean text and hierarchical sections.

        Args:
            raw_html: The HTML source content.
            url: The origin URL for metadata attribution.

        Returns:
            ScrapedDocument model instance.
        """
        title = "IBM Documentation"
        clean_text = ""
        sections: List[Dict[str, str]] = []
        metadata: Dict[str, Any] = {
            "domain": urlparse(url).netloc,
            "path": urlparse(url).path,
        }

        if HAS_BEAUTIFUL_SOUP:
            soup = BeautifulSoup(raw_html, "html.parser")

            # Extract page title
            title_tag = soup.find("title") or soup.find("h1")
            if title_tag and title_tag.get_text():
                title = title_tag.get_text().strip()

            # Remove scripts, styles, navigations, footers
            for unwanted in soup(
                ["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]
            ):
                unwanted.decompose()

            # Target main article or body
            main_content = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", {"role": "main"})
                or soup.find("body")
                or soup
            )

            # Extract sections by headers (h1, h2, h3)
            current_header = "Overview"
            current_paragraphs: List[str] = []

            for elem in main_content.find_all(["h1", "h2", "h3", "p", "ul", "ol", "pre", "code"]):
                tag_name = elem.name.lower()
                text = elem.get_text(separator=" ").strip()
                if not text:
                    continue

                if tag_name in ["h1", "h2", "h3"]:
                    if current_paragraphs:
                        section_body = self._clean_text("\n".join(current_paragraphs))
                        if section_body:
                            sections.append({
                                "header": current_header,
                                "content": section_body,
                            })
                        current_paragraphs = []
                    current_header = text
                else:
                    current_paragraphs.append(text)

            if current_paragraphs:
                section_body = self._clean_text("\n".join(current_paragraphs))
                if section_body:
                    sections.append({
                        "header": current_header,
                        "content": section_body,
                    })

            clean_text = self._clean_text(main_content.get_text(separator="\n"))
        else:
            # Fallback regex-based HTML cleaning
            title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

            # Strip scripts, styles, and html tags
            no_scripts = re.sub(r"<(script|style|nav|footer)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", no_scripts)
            clean_text = self._clean_text(text)
            sections = [{"header": "Overview", "content": clean_text}]

        return ScrapedDocument(
            url=url,
            title=title,
            raw_html=raw_html,
            clean_text=clean_text,
            sections=sections,
            metadata=metadata,
        )

    def scrape_batch(self, urls: List[str], delay: float = 0.5) -> List[ScrapedDocument]:
        """Scrape a batch of URLs with rate limiting.

        Args:
            urls: List of documentation URLs to scrape.
            delay: Pause in seconds between requests to respect rate limits.

        Returns:
            List of successfully scraped ScrapedDocument instances.
        """
        documents: List[ScrapedDocument] = []
        for i, url in enumerate(urls):
            try:
                doc = self.scrape_url(url)
                documents.append(doc)
            except Exception as exc:
                logger.error("Failed to scrape URL %s: %s", url, str(exc))

            if i < len(urls) - 1 and delay > 0:
                time.sleep(delay)

        return documents
