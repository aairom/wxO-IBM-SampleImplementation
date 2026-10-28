"""Tests for the automatic doc sync and deployment pipeline script."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.sync_and_deploy_docs import DocSyncPipeline


def test_sync_pipeline_dry_run(tmp_path: Path):
    """Test full pipeline execution in dry-run mode."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "01_test.txt").write_text("# Test Title\nThis is a sample documentation text.")

    store_file = tmp_path / "test_store.json"
    report_file = tmp_path / "test_report.json"
    yaml_file = tmp_path / "test_agent.yaml"
    yaml_file.write_text("spec_version: v1\nname: test_agent")
    tools_file = tmp_path / "tools.py"
    tools_file.write_text("# tools")

    pipeline = DocSyncPipeline(
        docs_dir=docs_dir,
        vector_store_path=store_file,
        agent_yaml=yaml_file,
        tools_py=tools_file,
        report_output=report_file,
        dry_run=True,
    )

    exit_code = pipeline.run()
    assert exit_code == 0
    assert store_file.exists()
    assert report_file.exists()

    with open(report_file, "r") as f:
        data = json.load(f)
        assert data["status"] == "success"
        step_names = [s["step"] for s in data["steps"]]
        assert "fetch_live_docs" in step_names
        assert "rebuild_vector_store" in step_names
        assert "deploy_to_orchestrate" in step_names
