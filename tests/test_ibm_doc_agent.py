"""Unit tests for IBM Documentation Assistant Agent, Scraper, Chunker, and Vector Store."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.ibm_doc_agent.agent import IBMDocAgent
from src.agents.ibm_doc_agent.chunker import TextChunker
from src.agents.ibm_doc_agent.models import DocumentChunk, ScrapedDocument
from src.agents.ibm_doc_agent.scraper import IBMDocScraper
from src.agents.ibm_doc_agent.tools import get_ibm_doc_by_url, search_ibm_live_docs
from src.agents.ibm_doc_agent.vector_store import VectorStore
from scripts.deploy_orchestrate_agent import AgentDeployer
from scripts.ingest_docs import run_ingestion


@pytest.fixture
def sample_scraped_doc() -> ScrapedDocument:
    """Fixture providing a sample scraped document."""
    return ScrapedDocument(
        url="https://www.ibm.com/docs/en/watsonx/getting-started",
        title="watsonx Orchestrate Getting Started",
        raw_html="<html><body><h1>Overview</h1><p>IBM watsonx Orchestrate helps automate enterprise workflows with agents and tools.</p><h2>Prerequisites</h2><p>An IBM Cloud account with an active watsonx Orchestrate instance is required.</p></body></html>",
        clean_text="Overview\nIBM watsonx Orchestrate helps automate enterprise workflows with agents and tools.\n\nPrerequisites\nAn IBM Cloud account with an active watsonx Orchestrate instance is required.",
        sections=[
            {
                "header": "Overview",
                "content": "IBM watsonx Orchestrate helps automate enterprise workflows with agents and tools.",
            },
            {
                "header": "Prerequisites",
                "content": "An IBM Cloud account with an active watsonx Orchestrate instance is required.",
            },
        ],
    )


def test_scraper_parse_html(sample_scraped_doc: ScrapedDocument):
    """Test HTML parsing and section extraction."""
    scraper = IBMDocScraper()
    doc = scraper.parse_html(sample_scraped_doc.raw_html, sample_scraped_doc.url)

    assert doc.url == sample_scraped_doc.url
    assert "watsonx" in doc.clean_text.lower()
    assert len(doc.sections) >= 1


def test_chunker_processing(sample_scraped_doc: ScrapedDocument):
    """Test chunking with section preservation and token estimation."""
    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    chunks = chunker.process_document(sample_scraped_doc)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.source_url == sample_scraped_doc.url
        assert chunk.page_title == sample_scraped_doc.title
        assert chunk.token_count > 0
        assert chunk.chunk_id is not None


def test_vector_store_operations(tmp_path: Path, sample_scraped_doc: ScrapedDocument):
    """Test vector storage, embedding generation, saving, and similarity search."""
    store_file = tmp_path / "test_store.json"
    store = VectorStore(storage_path=store_file)

    chunker = TextChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.process_document(sample_scraped_doc)

    added = store.add_chunks(chunks)
    assert added == len(chunks)
    assert store_file.exists()

    # Test similarity search
    results = store.similarity_search("enterprise workflows", top_k=2)
    assert len(results) > 0
    top_chunk, score = results[0]
    assert isinstance(top_chunk, DocumentChunk)
    assert score >= 0.0


def test_agent_query_processing(tmp_path: Path, sample_scraped_doc: ScrapedDocument):
    """Test agent query handling and response compilation with citations."""
    store_file = tmp_path / "test_agent_store.json"
    store = VectorStore(storage_path=store_file)
    chunker = TextChunker()
    chunks = chunker.process_document(sample_scraped_doc)
    store.add_chunks(chunks)

    agent = IBMDocAgent(name="Test_Agent", vector_store=store)
    response = agent.process_query("What are the prerequisites for watsonx?")

    assert response["agent_name"] == "Test_Agent"
    assert "citations" in response
    assert len(response["citations"]) > 0
    assert sample_scraped_doc.url in response["citations"]
    assert "Prerequisites" in response["answer"] or "watsonx" in response["answer"]


def test_deployer_mock_workflow(tmp_path: Path):
    """Test deployment script in mock mode."""
    report_file = tmp_path / "deploy_report.json"
    deployer = AgentDeployer(mock_mode=True)
    exit_code = deployer.run(report_path=str(report_file))

    assert exit_code == 0
    assert report_file.exists()
    with open(report_file, "r") as f:
        data = json.load(f)
        assert data["status"] == "success"
        assert len(data["steps"]) >= 3


def test_ingestion_pipeline_execution(tmp_path: Path, sample_scraped_doc: ScrapedDocument):
    """Test full ingestion pipeline run with mocked scraper."""
    store_file = tmp_path / "ingest_store.json"
    report_file = tmp_path / "ingest_report.json"

    with patch.object(IBMDocScraper, "scrape_url", return_value=sample_scraped_doc):
        exit_code = run_ingestion(
            urls=["https://www.ibm.com/docs/en/test"],
            output_store=str(store_file),
            report_output=str(report_file),
        )

        assert exit_code == 0
        assert store_file.exists()
        assert report_file.exists()
