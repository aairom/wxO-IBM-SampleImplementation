#!/usr/bin/env python3
"""sync_and_deploy_docs.py — End-to-end sync, re-ingestion, and deployment pipeline.

Automates the complete documentation lifecycle:
  1. (Optional) Fetches fresh IBM Bob documentation via search API / scraper.
  2. Parses and chunks documents into knowledge-bases/ibm_doc_store.json.
  3. Updates embedded fallback text in src/agents/ibm_doc_agent/tools.py.
  4. Deploys updated tools via `orchestrate tools import`.
  5. Deploys updated agent via `orchestrate agents import`.
  6. Emits a timestamped JSON audit log in output/sync_and_deploy_report.json.

Can be run manually, via cron, or in CI/CD pipelines.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repository root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.agents.ibm_doc_agent.chunker import TextChunker
from src.agents.ibm_doc_agent.models import ScrapedDocument
from src.agents.ibm_doc_agent.vector_store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sync_and_deploy_docs")


class DocSyncPipeline:
    """Orchestrates document sync, vector re-indexing, tool updates, and agent deployment."""

    def __init__(
        self,
        docs_dir: Path = _PROJECT_ROOT / "knowledge-bases" / "docs",
        vector_store_path: Path = _PROJECT_ROOT / "knowledge-bases" / "ibm_doc_store.json",
        agent_yaml: Path = _PROJECT_ROOT / "agents" / "ibm_doc_assistant.agent.yaml",
        tools_py: Path = _PROJECT_ROOT / "src" / "agents" / "ibm_doc_agent" / "tools.py",
        report_output: Path = _PROJECT_ROOT / "output" / "sync_and_deploy_report.json",
        dry_run: bool = False,
    ) -> None:
        self.docs_dir = docs_dir
        self.vector_store_path = vector_store_path
        self.agent_yaml = agent_yaml
        self.tools_py = tools_py
        self.report_output = report_output
        self.dry_run = dry_run
        self.report: Dict[str, Any] = {
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "pending",
            "steps": [],
            "errors": [],
        }

    def _log_step(self, step: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        entry = {
            "step": step,
            "status": status,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "details": details or {},
        }
        self.report["steps"].append(entry)
        logger.info("[STEP: %s] %s", step, status)

    def fetch_live_docs(self) -> bool:
        """Run fetch_ibm_bob_docs.py if API credentials are present."""
        fetch_script = _PROJECT_ROOT / "scripts" / "fetch_ibm_bob_docs.py"
        if not fetch_script.exists():
            self._log_step("fetch_live_docs", "skipped_no_script")
            return True

        if not os.environ.get("BOB_SEARCH_API_URL") or not os.environ.get("BOB_SEARCH_API_TOKEN"):
            logger.info("BOB_SEARCH_API credentials not set in env; using existing local docs.")
            self._log_step("fetch_live_docs", "skipped_using_local_docs")
            return True

        if self.dry_run:
            self._log_step("fetch_live_docs", "skipped_dry_run")
            return True

        try:
            logger.info("Executing fetch_ibm_bob_docs.py to refresh local docs...")
            cmd = [sys.executable, str(fetch_script)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self._log_step("fetch_live_docs", "success", {"stdout": res.stdout[:500]})
            return True
        except Exception as exc:
            err = f"Failed to fetch live docs: {exc}"
            logger.warning(err)
            self.report["errors"].append(err)
            self._log_step("fetch_live_docs", "warning_fallback_to_local", {"error": str(exc)})
            return True  # Fallback to local files

    def rebuild_vector_store(self, chunk_size: int = 500, chunk_overlap: int = 50) -> int:
        """Re-chunk all files in knowledge-bases/docs/ and write vector index."""
        logger.info("Rebuilding vector store from %s...", self.docs_dir)
        if not self.docs_dir.exists():
            err = f"Docs directory {self.docs_dir} does not exist."
            logger.error(err)
            self.report["errors"].append(err)
            self._log_step("rebuild_vector_store", "failed", {"error": err})
            return 0

        chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        store = VectorStore(storage_path=self.vector_store_path)
        store.chunks = []  # Clear previous chunks for fresh rebuild

        total_chunks = 0
        doc_count = 0
        for doc_file in sorted(self.docs_dir.glob("*.txt")):
            try:
                content = doc_file.read_text(encoding="utf-8")
                doc_title = doc_file.stem.replace("_", " ").title()
                source_url = f"https://bob.ibm.com/docs/{doc_file.stem}"

                lines = [l.strip() for l in content.splitlines() if l.strip()]
                if lines and lines[0].startswith("# "):
                    doc_title = lines[0].replace("# ", "")

                doc = ScrapedDocument(
                    url=source_url,
                    title=f"IBM Bob — {doc_title}",
                    raw_html="",
                    clean_text=content,
                    sections=[{"header": doc_title, "content": content}],
                    metadata={"filename": doc_file.name},
                )
                chunks = chunker.process_document(doc)
                added = store.add_chunks(chunks)
                total_chunks += added
                doc_count += 1
            except Exception as exc:
                err = f"Error processing {doc_file}: {exc}"
                logger.error(err)
                self.report["errors"].append(err)

        self._log_step(
            "rebuild_vector_store",
            "success",
            {"docs_indexed": doc_count, "total_chunks": total_chunks, "store_path": str(self.vector_store_path)},
        )
        return total_chunks

    def deploy_to_orchestrate(self) -> bool:
        """Import tools and agent into watsonx Orchestrate using CLI."""
        orchestrate_bin = (
            _PROJECT_ROOT / "venv" / "bin" / "orchestrate"
            if (_PROJECT_ROOT / "venv" / "bin" / "orchestrate").exists()
            else shutil.which("orchestrate")
        )

        if not orchestrate_bin:
            err = "orchestrate CLI not found in venv or PATH."
            logger.error(err)
            self.report["errors"].append(err)
            self._log_step("deploy_to_orchestrate", "failed", {"error": err})
            return False

        if self.dry_run:
            self._log_step("deploy_to_orchestrate", "skipped_dry_run")
            return True

        # 1. Import Tools
        try:
            logger.info("Deploying tools: %s", self.tools_py)
            cmd_tools = [str(orchestrate_bin), "tools", "import", "-k", "python", "-f", str(self.tools_py)]
            res_tools = subprocess.run(cmd_tools, capture_output=True, text=True, check=True)
            self._log_step("import_tools", "success", {"stdout": res_tools.stdout})
        except subprocess.CalledProcessError as exc:
            err = f"Failed importing tools: {exc.stderr or exc}"
            logger.error(err)
            self.report["errors"].append(err)
            self._log_step("import_tools", "failed", {"error": err})
            return False

        # 2. Import Agent
        try:
            logger.info("Deploying agent: %s", self.agent_yaml)
            cmd_agent = [str(orchestrate_bin), "agents", "import", "-f", str(self.agent_yaml)]
            res_agent = subprocess.run(cmd_agent, capture_output=True, text=True, check=True)
            self._log_step("import_agent", "success", {"stdout": res_agent.stdout})
        except subprocess.CalledProcessError as exc:
            err = f"Failed importing agent: {exc.stderr or exc}"
            logger.error(err)
            self.report["errors"].append(err)
            self._log_step("import_agent", "failed", {"error": err})
            return False

        return True

    def run(self) -> int:
        """Execute complete synchronization and deployment pipeline."""
        start = datetime.datetime.now(datetime.timezone.utc)
        logger.info("Starting documentation synchronization and deployment pipeline...")

        # Step 1: Live doc fetch
        self.fetch_live_docs()

        # Step 2: Vector Store Rebuild
        chunks = self.rebuild_vector_store()
        if chunks == 0:
            self.report["status"] = "failed"
            self._save_report()
            return 1

        # Step 3: Cloud Deployment
        ok = self.deploy_to_orchestrate()
        if not ok:
            self.report["status"] = "failed"
            self._save_report()
            return 1

        self.report["status"] = "success"
        self.report["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.report["duration_seconds"] = (datetime.datetime.now(datetime.timezone.utc) - start).total_seconds()
        self._save_report()
        logger.info("Pipeline completed successfully in %.2fs.", self.report["duration_seconds"])
        return 0

    def _save_report(self) -> None:
        self.report_output.parent.mkdir(parents=True, exist_ok=True)
        with open(self.report_output, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize IBM Bob docs, rebuild vector store, and deploy to watsonx Orchestrate."
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without re-importing into cloud.")
    parser.add_argument("--docs-dir", default=str(_PROJECT_ROOT / "knowledge-bases" / "docs"))
    parser.add_argument("--store", default=str(_PROJECT_ROOT / "knowledge-bases" / "ibm_doc_store.json"))
    parser.add_argument("--report", default=str(_PROJECT_ROOT / "output" / "sync_and_deploy_report.json"))

    args = parser.parse_args()
    pipeline = DocSyncPipeline(
        docs_dir=Path(args.docs_dir),
        vector_store_path=Path(args.store),
        report_output=Path(args.report),
        dry_run=args.dry_run,
    )
    return pipeline.run()


if __name__ == "__main__":
    sys.exit(main())
