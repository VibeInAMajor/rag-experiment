"""Safety guards for explicitly enabled acceptance; these tests perform no database or GPU work."""

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from psycopg.conninfo import conninfo_to_dict

from scripts import workbench_embedding_acceptance as acceptance


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only fake local credentials are installed; any attempted connection remains forbidden."""
    monkeypatch.setenv("WORKBENCH_TEST_ADMIN_DSN", "postgresql://admin:private-canary@127.0.0.1:5432/workbench")
    monkeypatch.setenv("WORKBENCH_TEST_APP_DSN", "postgresql://app:private-canary@127.0.0.1:5432/workbench")


@pytest.mark.parametrize("name", ["workbench", "postgres", "rag_test_known", "rag_test_" + "a" * 32 + ";DROP"])
def test_refuses_any_database_not_named_by_full_disposable_uuid(name: str) -> None:
    """Neither a configured application database nor a misleading prefix is an acceptance target."""
    with pytest.raises(acceptance.AcceptanceError):
        acceptance._database(name, "b" * 32)


def test_derives_both_connections_to_one_new_database_without_exposing_credentials() -> None:
    """Administrative and application operations refer to exactly the owned disposable database."""
    database = acceptance._database("rag_test_" + "a" * 32, "b" * 32)
    assert (
        conninfo_to_dict(database.admin_dsn)["dbname"] == conninfo_to_dict(database.app_dsn)["dbname"] == database.name
    )
    assert "private-canary" not in repr(database)


def test_wrong_database_endpoint_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """An application connection cannot silently point to another host/port during cleanup or fixture writes."""
    monkeypatch.setenv("WORKBENCH_TEST_APP_DSN", "postgresql://app:private-canary@127.0.0.1:9999/workbench")
    with pytest.raises(acceptance.AcceptanceError):
        acceptance._database("rag_test_" + "a" * 32, "b" * 32)


def test_cleanup_refuses_owner_mismatch_before_any_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even an appropriately named existing test database needs its run-specific persisted owner marker."""
    database = acceptance._database("rag_test_" + "a" * 32, "b" * 32)

    def mismatch(_database: Any) -> None:
        raise acceptance.AcceptanceError("DISPOSABLE_DATABASE_OWNER_MISMATCH")

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("DROP must not reach a connection after owner mismatch")

    monkeypatch.setattr(acceptance, "_assert_owner", mismatch)
    monkeypatch.setattr(acceptance.psycopg, "connect", forbidden)
    with pytest.raises(acceptance.AcceptanceError, match="OWNER_MISMATCH"):
        acceptance._drop_database(database)


def test_public_evidence_omits_private_operator_paths_and_endpoint() -> None:
    """Only the ignored resume manifest may retain operator locations and the internal service address."""
    manifest = {
        "endpoint": "private-endpoint-canary",
        "model_directory": "private-model-canary",
        "capacity_config": "private-config-canary",
        "quality_before_file": "private-file-canary",
        "load_text": "private-descriptor-canary",
        "database_name": "rag_test_" + "a" * 32,
        "target_tokens_per_item": 4096,
    }
    encoded = json.dumps(acceptance._public_preparation(manifest))
    assert "private-" not in encoded and "4096" in encoded


def test_real_http_edit_fixture_changes_one_word_without_moving_source_offsets() -> None:
    """The guarded replacement keeps surrounding chunks eligible for actual unchanged-input cache reuse."""
    first, changed = acceptance._upload_content(), acceptance._upload_content(edited=True)
    assert len(first) == len(changed)
    assert first != changed
    assert first.replace(b"version", b"release", 1) == changed


def test_backlog_builder_is_unique_exact_length_and_fits_persisted_chunk_bound() -> None:
    """A small offline counter isolates packing bounds without claiming actual Qwen capacity."""

    class Counter:
        counter_revision = "offline-test-only"

        def count_tokens(self, text: str) -> int:
            return len(text.split()) + 1

    counter = Counter()
    first = acceptance._unique_text(counter, 4096, "tenant-a", 0, "a" * 32)
    other = acceptance._unique_text(counter, 4096, "tenant-a", 1, "a" * 32)
    assert counter.count_tokens(first) == counter.count_tokens(other) == 4096
    assert len(first) < 32768 and len(other) < 32768
    assert first != other


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", [0.0, 599.9, float("nan"), float("inf"), 1800.1])
async def test_invalid_duration_cannot_open_or_remove_a_prepared_database(
    duration: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A short or unbounded run cannot become a fake ten-minute proof or accidentally destroy preparation."""

    def forbidden(_path: Path) -> Any:
        raise AssertionError("Manifest and database must remain untouched")

    monkeypatch.setattr(acceptance, "_load_manifest", forbidden)
    with pytest.raises(acceptance.AcceptanceError):
        await acceptance.run_acceptance(argparse.Namespace(duration=duration))
