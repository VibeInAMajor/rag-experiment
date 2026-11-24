"""Version-bound original registration on isolated real PostgreSQL databases."""

import asyncio
from collections.abc import AsyncIterator
from hashlib import sha256
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from pydantic import JsonValue

from apps.workbench.persistence.models import (
    Chunk,
    LocalOriginalRegistration,
    RecordConflict,
    Source,
    SourceVersion,
    Workspace,
    WorkspaceContext,
)
from apps.workbench.postgres.db_migrations import migrate
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.sources.source_registration import register_original_file
from apps.workbench.testing.database import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_CONTEXT = WorkspaceContext(workspace_id="development")
_SHA = "a" * 64


@pytest_asyncio.fixture(loop_scope="function")
async def original_repository(disposable_database: DisposableDatabase) -> AsyncIterator[PostgresPersistence]:
    """Migrate only the fixture-owned database and connect with the normal app role."""
    migrate(disposable_database.admin_dsn)
    repository = PostgresPersistence(disposable_database.app_dsn)
    await repository.start()
    try:
        await repository.create_workspace(_CONTEXT, Workspace(workspace_id="development", name="Development"))
        yield repository
    finally:
        await repository.close()


async def _publish_original(
    repository: PostgresPersistence,
    *,
    source_id: str = "real-document",
    version_id: str = "original-version",
    context: WorkspaceContext = _CONTEXT,
    source_metadata: dict[str, JsonValue] | None = None,
    version_metadata: dict[str, JsonValue] | None = None,
) -> None:
    source = Source(
        workspace_id=context.workspace_id,
        source_id=source_id,
        title="Registered source",
        metadata=source_metadata or {},
    )
    version = SourceVersion(
        workspace_id=context.workspace_id,
        source_id=source_id,
        version_id=version_id,
        content_hash="parsed-content-hash",
        metadata=version_metadata or {},
    )
    chunk = Chunk(
        workspace_id=context.workspace_id,
        source_id=source_id,
        version_id=version_id,
        chunk_id=f"{version_id}-chunk",
        title=source.title,
        content="Actual persisted parsed content for the original registration.",
        content_hash=version.content_hash,
    )
    await repository.publish_source(context, source=source, version=version, chunks=[chunk])


async def test_original_registration_preserves_records_and_survives_pool_restart(
    original_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Registration changes only version metadata and its derived corpus fingerprint."""
    await _publish_original(original_repository, version_metadata={"parser": "existing-parser"})
    before = await original_repository.corpus_snapshot(_CONTEXT)
    record = await original_repository.get_local_original(
        _CONTEXT, source_id="real-document", version_id="original-version"
    )
    assert record is not None and record.registration is None and record.is_demo is False
    await original_repository.register_local_original(
        _CONTEXT,
        source_id="real-document",
        version_id="original-version",
        relative_path="manuals/Original.pdf",
        sha256=_SHA,
    )
    after = await original_repository.corpus_snapshot(_CONTEXT)
    assert after.corpus_revision != before.corpus_revision
    assert after.chunk_count == before.chunk_count
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT metadata,content_hash,status FROM workbench.source_versions WHERE source_id='real-document'"
        ).fetchone()
    assert row == (
        {"parser": "existing-parser", "local_original": {"relative_path": "manuals/Original.pdf", "sha256": _SHA}},
        "parsed-content-hash",
        "active",
    )
    reopened = PostgresPersistence(disposable_database.app_dsn)
    await reopened.start()
    try:
        persisted = await reopened.get_local_original(
            _CONTEXT, source_id="real-document", version_id="original-version"
        )
        assert persisted is not None
        assert persisted.registration == LocalOriginalRegistration(relative_path="manuals/Original.pdf", sha256=_SHA)
    finally:
        await reopened.close()


async def test_exact_retry_is_idempotent_and_conflicting_registration_cannot_replace_original(
    original_repository: PostgresPersistence,
) -> None:
    """An explicit registration cannot silently rebind an immutable version."""
    await _publish_original(original_repository)
    values = {
        "source_id": "real-document",
        "version_id": "original-version",
        "relative_path": "Original.pdf",
        "sha256": _SHA,
    }
    await original_repository.register_local_original(_CONTEXT, **values)
    revision = (await original_repository.corpus_snapshot(_CONTEXT)).corpus_revision
    await original_repository.register_local_original(_CONTEXT, **values)
    assert (await original_repository.corpus_snapshot(_CONTEXT)).corpus_revision == revision
    for change in ({"relative_path": "Different.pdf"}, {"sha256": "b" * 64}):
        with pytest.raises(RecordConflict, match="already bound"):
            await original_repository.register_local_original(_CONTEXT, **(values | change))
    assert (await original_repository.corpus_snapshot(_CONTEXT)).corpus_revision == revision


@pytest.mark.parametrize(
    ("source_id", "source_metadata", "version_metadata"),
    [
        ("demo-reserved", {}, {}),
        ("real-document", {"synthetic": True}, {}),
        ("real-document", {}, {"synthetic": True}),
        ("real-document", {"development_seed": "development-corpus-v1"}, {}),
        ("real-document", {}, {"development_seed": "development-corpus-v1"}),
        ("real-document", {}, {"development_seed": None}),
    ],
)
async def test_demo_and_synthetic_provenance_cannot_be_registered(
    original_repository: PostgresPersistence,
    source_id: str,
    source_metadata: dict[str, JsonValue],
    version_metadata: dict[str, JsonValue],
) -> None:
    """Either level of synthetic provenance forbids an original-file association."""
    await _publish_original(
        original_repository, source_id=source_id, source_metadata=source_metadata, version_metadata=version_metadata
    )
    record = await original_repository.get_local_original(_CONTEXT, source_id=source_id, version_id="original-version")
    assert record is not None and record.is_demo is True
    with pytest.raises(RecordConflict, match="cannot be registered"):
        await original_repository.register_local_original(
            _CONTEXT, source_id=source_id, version_id="original-version", relative_path="Original.pdf", sha256=_SHA
        )


async def test_unknown_foreign_and_inactive_versions_never_expose_or_accept_a_registration(
    original_repository: PostgresPersistence,
) -> None:
    """Scope and active-version conditions apply to both lookup and registration."""
    foreign = WorkspaceContext(workspace_id="other-owner")
    await original_repository.create_workspace(foreign, Workspace(workspace_id=foreign.workspace_id, name="Other"))
    await _publish_original(
        original_repository, context=foreign, source_id="private-source", version_id="private-version"
    )
    await _publish_original(original_repository)
    await _publish_original(original_repository, version_id="replacement-version")
    for source_id, version_id in (
        ("unknown", "unknown"),
        ("private-source", "private-version"),
        ("real-document", "unknown"),
        ("real-document", "original-version"),
    ):
        assert (
            await original_repository.get_local_original(_CONTEXT, source_id=source_id, version_id=version_id) is None
        )
        with pytest.raises(RecordConflict, match="cannot be registered"):
            await original_repository.register_local_original(
                _CONTEXT, source_id=source_id, version_id=version_id, relative_path="Original.pdf", sha256=_SHA
            )


async def test_malformed_metadata_is_unavailable_and_cannot_be_silently_overwritten(
    original_repository: PostgresPersistence,
) -> None:
    """Corrupt metadata fails closed and requires an explicit future repair mechanism."""
    await _publish_original(
        original_repository, version_metadata={"local_original": {"relative_path": "../secret", "sha256": _SHA}}
    )
    record = await original_repository.get_local_original(
        _CONTEXT, source_id="real-document", version_id="original-version"
    )
    assert record is not None and record.registration is None
    with pytest.raises(RecordConflict, match="already bound"):
        await original_repository.register_local_original(
            _CONTEXT,
            source_id="real-document",
            version_id="original-version",
            relative_path="Original.pdf",
            sha256=_SHA,
        )


async def test_parallel_registration_serializes_with_the_existing_source_lock(
    original_repository: PostgresPersistence,
) -> None:
    """Two competing original registrations cannot both claim the same active version."""
    await _publish_original(original_repository)
    outcomes = await asyncio.gather(
        *(
            original_repository.register_local_original(
                _CONTEXT,
                source_id="real-document",
                version_id="original-version",
                relative_path="Original.pdf",
                sha256=digest,
            )
            for digest in (_SHA, "b" * 64)
        ),
        return_exceptions=True,
    )
    assert sum(outcome is None for outcome in outcomes) == 1
    assert sum(isinstance(outcome, RecordConflict) for outcome in outcomes) == 1
    record = await original_repository.get_local_original(
        _CONTEXT, source_id="real-document", version_id="original-version"
    )
    assert record is not None and record.registration is not None
    assert record.registration.sha256 in {_SHA, "b" * 64}


async def test_trusted_registration_hashes_real_original_bytes_without_changing_parsed_content(
    original_repository: PostgresPersistence, tmp_path: Path
) -> None:
    """Byte fingerprint and original location persist separately from parsed passage identity."""
    await _publish_original(original_repository)
    directory = tmp_path / "manuals"
    directory.mkdir()
    original = directory / "Оригінал document.pdf"
    content = b"Actual local original bytes, distinct from parsed text."
    original.write_bytes(content)
    await register_original_file(
        original_repository,
        context=_CONTEXT,
        source_id="real-document",
        version_id="original-version",
        root=tmp_path,
        path=original,
    )
    record = await original_repository.get_local_original(
        _CONTEXT, source_id="real-document", version_id="original-version"
    )
    assert record is not None and record.registration is not None
    assert record.registration.relative_path == "manuals/Оригінал document.pdf"
    assert record.registration.sha256 == sha256(content).hexdigest()
    chunk = await original_repository.get_chunk(_CONTEXT, "original-version-chunk")
    assert chunk is not None and chunk.content_hash == "parsed-content-hash"
