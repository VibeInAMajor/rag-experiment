"""Storage benchmark guards and explicit disposable-only executions; never call a model."""

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from apps.workbench.api.tests.conftest import DisposableDatabase
from scripts.workbench_embedding_storage_benchmark import StorageBenchmarkError, _validate_target, run_storage_benchmark

_DATABASE = "rag_test_" + "1" * 32
_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("database", ["workbench", "postgres", "rag_test_production", "rag_test_" + "g" * 32, ""])
def test_benchmark_refuses_main_or_unverifiable_database(database: str) -> None:
    """The caller cannot accidentally benchmark a production or arbitrarily named database."""
    dsn = f"host=127.0.0.1 port=5432 dbname='{database}' user=not-used"
    with pytest.raises(StorageBenchmarkError, match="INVALID_DISPOSABLE_BENCHMARK_TARGET"):
        _validate_target(dsn, dsn)


@pytest.mark.parametrize("other", ["host=remote.example", "port=5433", "dbname=rag_test_" + "2" * 32])
def test_benchmark_refuses_different_admin_and_app_targets(other: str) -> None:
    """Both roles must point at the same explicit local disposable database."""
    base = f"host=127.0.0.1 port=5432 dbname={_DATABASE}"
    with pytest.raises(StorageBenchmarkError, match="INVALID_DISPOSABLE_BENCHMARK_TARGET"):
        _validate_target(base, f"{base} {other}")


def test_benchmark_accepts_role_changes_only_with_the_same_disposable_target() -> None:
    """Separate privileged migration and restricted application roles share the fixture target only."""
    base = f"host=127.0.0.1 port=5432 dbname={_DATABASE}"
    assert _validate_target(f"{base} user=fixture-admin", f"{base} user=fixture-app") == _DATABASE


@pytest.mark.asyncio
@pytest.mark.parametrize("workspaces,chunks", [(0, 10000), (11, 10000), (1, 10001), (True, 1)])
async def test_benchmark_scale_refuses_before_connecting(workspaces: int, chunks: int) -> None:
    """A valid-looking target still cannot expand beyond the existing workspace/corpus bounds."""
    dsn = f"host=127.0.0.1 port=5432 dbname={_DATABASE}"
    with pytest.raises(StorageBenchmarkError, match="INVALID_BENCHMARK_SCALE"):
        await run_storage_benchmark(admin_dsn=dsn, app_dsn=dsn, workspaces=workspaces, chunks_per_workspace=chunks)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="function")
async def test_small_storage_run_checks_restart_update_and_fake_provenance(
    disposable_database: DisposableDatabase,
) -> None:
    """The actual benchmark exercises multiple bounded pages and unchanged-input cache reuse."""
    report = await run_storage_benchmark(
        admin_dsn=disposable_database.admin_dsn,
        app_dsn=disposable_database.app_dsn,
        workspaces=1,
        chunks_per_workspace=129,
    )
    assert report["kind"] == "SYNTHETIC_STORAGE_ONLY" and report["real_model_calls"] == 0
    assert report["initial_active_chunks"] == 129
    assert report["initial"][0]["pool_restart_checkpoint"]["mappings_after"] == 128
    assert report["pool_reopen_counts_before"] == report["pool_reopen_counts_after"]
    assert report["updated_source"]["cache_hit_occurrences"] == 129
    assert report["final_counts"]["cache_vectors"] == 1
    assert report["final_counts"]["chunk_mappings"] == 258


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.skipif(
    os.environ.get("WORKBENCH_TEST_STORAGE_BENCHMARK") != "1",
    reason="Explicitly enable the large disposable storage benchmark",
)
async def test_large_disposable_storage_benchmark(disposable_database: DisposableDatabase) -> None:
    """Run 100k synthetic mappings only when the user has explicitly allocated the test window."""
    report = await run_storage_benchmark(
        admin_dsn=disposable_database.admin_dsn,
        app_dsn=disposable_database.app_dsn,
        workspaces=10,
        chunks_per_workspace=10000,
    )
    assert report["initial_active_chunks"] == 100000 and report["final_counts"]["cache_vectors"] == 10
    assert report["final_counts"]["chunk_mappings"] == 110000
    destination = os.environ.get("WORKBENCH_TEST_STORAGE_BENCHMARK_REPORT")
    if destination:
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(output.write_text, json.dumps(report, indent=2) + "\n", encoding="utf-8")


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.skipif(
    os.environ.get("WORKBENCH_TEST_STORAGE_SERVER_RESTART") != "1",
    reason="An operator must coordinate the PostgreSQL restart",
)
async def test_disposable_storage_survives_real_server_restart(disposable_database: DisposableDatabase) -> None:
    """Pause after 10k committed mappings and independently verify the server start timestamp changed."""
    ready = _ROOT / ".cache/workbench-embedding-storage-restart-ready.json"
    proceed = _ROOT / ".cache/workbench-embedding-storage-restart-continue.json"

    async def checkpoint(details: dict[str, object]) -> None:
        await asyncio.to_thread(ready.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(ready.write_text, json.dumps(details, indent=2) + "\n", encoding="utf-8")
        started = time.monotonic()
        while time.monotonic() - started < 180:
            if proceed.exists():
                content = await asyncio.to_thread(proceed.read_text, encoding="utf-8")
                acknowledgement = json.loads(content)
                if (
                    acknowledgement.get("database") == details["database"]
                    and acknowledgement.get("postgres_restarted") is True
                ):
                    return
            await asyncio.sleep(0.5)
        pytest.fail("The matching operator restart acknowledgement did not arrive within 180 seconds")

    report = await run_storage_benchmark(
        admin_dsn=disposable_database.admin_dsn,
        app_dsn=disposable_database.app_dsn,
        workspaces=1,
        chunks_per_workspace=10000,
        before_restart_audit=checkpoint,
    )
    assert report["initial_active_chunks"] == 10000 and report["server_restart"]["changed"] is True
    assert report["pool_reopen_counts_before"] == report["pool_reopen_counts_after"]
    assert report["final_counts"]["chunk_mappings"] == 20000
    destination = os.environ.get("WORKBENCH_TEST_STORAGE_BENCHMARK_REPORT")
    if destination:
        output = Path(destination)
        await asyncio.to_thread(output.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(output.write_text, json.dumps(report, indent=2) + "\n", encoding="utf-8")
