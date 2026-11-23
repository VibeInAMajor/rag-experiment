"""Explicitly enabled real local-model qualification, separate from offline adapter tests."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from scripts.workbench_embedding_qualify import _DEFAULT_CONTAINER, _DEFAULT_ENDPOINT, run_qualification


@pytest.mark.asyncio
async def test_real_local_qwen_query_and_document_qualification() -> None:
    """Use the actual pinned assets and GPU; never replace an unavailable model with fake vectors."""
    if os.environ.get("WORKBENCH_TEST_EMBEDDING_LIVE") != "1":
        pytest.skip("WORKBENCH_TEST_EMBEDDING_LIVE=1 explicitly enables bounded local GPU inference")
    directory = os.environ.get("WORKBENCH_TEST_QWEN_TOKENIZER_DIR")
    if not directory:
        pytest.fail("Live qualification requires WORKBENCH_TEST_QWEN_TOKENIZER_DIR")
    report = await run_qualification(
        directory=Path(directory),
        container=os.environ.get("WORKBENCH_TEST_EMBEDDING_CONTAINER", _DEFAULT_CONTAINER),
        endpoint=os.environ.get("WORKBENCH_TEST_EMBEDDING_ENDPOINT", _DEFAULT_ENDPOINT),
        run_model=True,
    )
    assert report["inference"]["status"] == "PASS"
    assert report["inference"]["representative_texts"] == 30
    assert report["full_asset_hashes_unchanged_after_run"] is True
    assert report["full_cached_asset_hashes_unchanged_after_run"] is True
    assert report["governor"]["attempts_sent"] == report["governor"]["attempts_successful"]
    assert report["governor"]["max_in_flight"] == 1
    assert report["governor"]["production_capacity_status"] == "NOT_QUALIFIED"
    assert report["negative_diagnostics"]["inference_attempts_added"] == 0
    destination = os.environ.get("WORKBENCH_TEST_EMBEDDING_REPORT")
    if destination:
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            output.write_text, json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
