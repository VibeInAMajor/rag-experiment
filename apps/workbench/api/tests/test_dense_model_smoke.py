"""Explicit gated real-model HTTP/SQL evidence; default test runs never dispatch GPU traffic."""

import argparse
import asyncio
import json
import os
from pathlib import Path

import pytest

from scripts.workbench_dense_evaluate import _run

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.asyncio(loop_scope="function")]


async def test_real_dense_http_matches_independent_sql_oracle() -> None:
    """Audit 102 real persisted vectors and all fixed multilingual query labels through HTTP."""
    if os.environ.get("WORKBENCH_DENSE_LIVE_TEST") != "1":
        pytest.skip("Set WORKBENCH_DENSE_LIVE_TEST=1 for explicit local GPU and disposable PostgreSQL evaluation")
    capacity = os.environ.get("WORKBENCH_DENSE_CAPACITY_CONFIG")
    if not capacity:
        pytest.fail("WORKBENCH_DENSE_CAPACITY_CONFIG must select fresh actual calibration")
    report = await _run(
        argparse.Namespace(
            capacity_config=Path(capacity),
            model_directory=Path(os.environ.get("WORKBENCH_EMBEDDING_MODEL_DIRECTORY", "A:/AI/TEI/qwen3-4b")),
            endpoint="http://127.0.0.1:8082",
            container="rag-workbench-embedding-1",
        )
    )
    assert report["status"] == "PASS"
    assert report["coverage"]["ready_embeddings"] >= 100
    assert report["semantic_queries"] >= 30
    assert report["lexical_exact_queries"] >= 10
    assert all(case["sql_oracle_agrees"] for case in report["cases"])
    assert report["application_restart"]["status"] == "PASS"
    output = os.environ.get("WORKBENCH_DENSE_EVIDENCE")
    if output:
        await asyncio.to_thread(
            Path(output).write_text, json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
