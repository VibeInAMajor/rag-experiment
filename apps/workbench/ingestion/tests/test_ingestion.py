"""Application orchestration tests use real qualified processing and an explicit persistence double."""

import asyncio
import hashlib
import json
import logging
import socket
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

import pytest

from apps.workbench.chunking import chunking_adapters as adapters
from apps.workbench.chunking.chunking_profiles import ChunkingError, ChunkingErrorCode, structural_token_profile
from apps.workbench.configuration.document_processing import DocumentProcessingSettings, load_document_processing
from apps.workbench.embedding.embedding import EmbeddingProfile
from apps.workbench.embedding.embedding_ingestion import embedding_candidate_input
from apps.workbench.embedding.embedding_jobs import EmbeddingCandidate
from apps.workbench.ingestion import ingestion as ingestion_module
from apps.workbench.ingestion.ingestion import IngestionError, IngestionService, UploadInput
from apps.workbench.parsing.parsing import ParsedDocument
from apps.workbench.persistence.models import (
    Chunk,
    DatabaseUnavailable,
    DocumentNotFound,
    IdempotencyConflict,
    IngestionInProgress,
    IngestionJob,
    IngestionTiming,
    Source,
    SourceVersion,
    UploadReservation,
    VersionConflict,
    WorkspaceContext,
)
from apps.workbench.testing.persistence import _DatabaseProbe
from haystack.components.converters import TextFileToDocument

_CONTEXT = WorkspaceContext(workspace_id="development", trace_id="ingestion-test-trace")
_CREATED = "2026-11-22T12:00:00Z"


class _Repository(_DatabaseProbe):
    """Only unit-test state; real atomicity, RLS and SQL visibility are tested by the PostgreSQL contour."""

    get_ingestion_job = _DatabaseProbe._unexpected
    get_source_detail = _DatabaseProbe._unexpected
    list_active_chunks = _DatabaseProbe._unexpected

    def __init__(self) -> None:
        super().__init__()
        self.jobs: dict[str, IngestionJob] = {}
        self.keys: dict[str, tuple[str, str]] = {}
        self.active: dict[str, tuple[Source, SourceVersion, list[Chunk]]] = {}
        self.versions: dict[str, SourceVersion] = {}
        self.transitions: list[str] = []
        self.complete_calls = 0
        self.publication_failure: Exception | None = None
        self.failure_recording_failure = False
        self.available = True

    async def ingestion_ready(self, context: WorkspaceContext) -> bool:
        assert context.workspace_id == _CONTEXT.workspace_id
        return self.available

    @asynccontextmanager
    async def reserve_ingestion(
        self,
        context: WorkspaceContext,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        source_content_sha256: str,
        source_id: str | None = None,
        expected_active_version_id: str | None = None,
    ) -> AsyncIterator[UploadReservation]:
        if idempotency_key in self.keys:
            fingerprint, job_id = self.keys[idempotency_key]
            if fingerprint != request_fingerprint:
                raise IdempotencyConflict()
            job = self.jobs[job_id]
            if job.status not in {"completed", "failed"}:
                raise IngestionInProgress(job_id)
            yield UploadReservation(job=job, newly_reserved=False)
            return
        if source_id is not None:
            if source_id not in self.active:
                raise DocumentNotFound()
            if self.active[source_id][1].version_id != expected_active_version_id:
                raise VersionConflict()
        job = IngestionJob(
            workspace_id=context.workspace_id,
            job_id=uuid4().hex,
            source_id=source_id or uuid4().hex,
            reserved_version_id=uuid4().hex,
            operation="create" if source_id is None else "update",
            expected_active_version_id=expected_active_version_id,
            status="pending",
            stage="pending",
            source_content_sha256=source_content_sha256,
            created_at=_CREATED,
            updated_at=_CREATED,
        )
        self.jobs[job.job_id] = job
        self.keys[idempotency_key] = (request_fingerprint, job.job_id)
        yield UploadReservation(job=job, newly_reserved=True, owner_token=uuid4().hex)

    async def transition_ingestion(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        stage: Literal["parsing", "chunking", "publishing"],
    ) -> IngestionJob:
        assert context.workspace_id == _CONTEXT.workspace_id and owner_token
        self.transitions.append(stage)
        self.jobs[job_id] = self.jobs[job_id].model_copy(update={"status": stage, "stage": stage})
        return self.jobs[job_id]

    async def complete_ingestion_with_publication(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        source: Source,
        version: SourceVersion,
        chunks: list[Chunk],
        stages: list[IngestionTiming],
    ) -> IngestionJob:
        assert context.workspace_id == _CONTEXT.workspace_id and owner_token
        started = perf_counter()
        self.complete_calls += 1
        if self.publication_failure:
            raise self.publication_failure
        job = self.jobs[job_id]
        existing = self.active.get(source.source_id)
        if job.operation == "update" and existing and existing[1].version_id != job.expected_active_version_id:
            raise VersionConflict()
        unchanged = existing is not None and (
            existing[1].content_hash == version.content_hash
            and existing[1].metadata["processing_profile_fingerprint"]
            == version.metadata["processing_profile_fingerprint"]
        )
        if unchanged and existing:
            effective_version = existing[1]
            effective_chunks = existing[2]
            outcome = "unchanged"
        else:
            self.active[source.source_id] = (source, version, chunks)
            self.versions[version.version_id] = version
            effective_version, effective_chunks = version, chunks
            outcome = "created" if job.operation == "create" else "updated"
        corpus = hashlib.sha256(json.dumps(sorted(self.versions)).encode()).hexdigest()
        self.jobs[job_id] = job.model_copy(
            update={
                "status": "completed",
                "stage": "completed",
                "effective_version_id": effective_version.version_id,
                "processing_profile_fingerprint": effective_version.metadata["processing_profile_fingerprint"],
                "chunk_count": len(effective_chunks),
                "outcome": outcome,
                "corpus_revision": f"corpus-{corpus}",
                "stages": stages
                + [IngestionTiming(stage="publication", duration_ms=(perf_counter() - started) * 1000)],
                "finished_at": _CREATED,
            }
        )
        return self.jobs[job_id]

    async def fail_ingestion(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        error_code: str,
        retryable: bool,
        stages: list[IngestionTiming],
    ) -> IngestionJob:
        assert context.workspace_id == _CONTEXT.workspace_id and owner_token
        if self.failure_recording_failure:
            raise DatabaseUnavailable()
        if self.jobs[job_id].status == "completed":
            return self.jobs[job_id]
        self.jobs[job_id] = self.jobs[job_id].model_copy(
            update={
                "status": "failed",
                "error_code": error_code,
                "retryable": retryable,
                "stages": stages,
                "finished_at": _CREATED,
            }
        )
        return self.jobs[job_id]


@pytest.fixture(autouse=True)
def deny_processing_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Application processing never reads a remote document or downloads indexing resources."""

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Ingestion processing attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden)


def _upload(content: bytes, *, key: str = "test-upload-key", filename: str = "notes.txt", **kwargs: Any) -> UploadInput:
    return UploadInput(content=content, filename=filename, declared_mime=None, idempotency_key=key, **kwargs)


def _embedding_inputs(version: SourceVersion, chunks: list[Chunk]) -> dict[str, tuple[str, str]]:
    profile = EmbeddingProfile(
        profile_id="reuse-regression",
        profile_revision="reuse-regression-r1",
        provider_adapter_id="tei-openai",
        model_id="fake-no-inference",
        model_revision="a" * 40,
        model_digest="b" * 64,
        tokenizer_digest="c" * 64,
        tokenizer_revision="reuse-test-r1",
        dimensions=32,
    )
    return {
        chunk.content_hash: embedding_candidate_input(
            EmbeddingCandidate(
                workspace_id=chunk.workspace_id,
                source_id=chunk.source_id,
                version_id=chunk.version_id,
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                content_hash=chunk.content_hash,
                metadata=chunk.metadata,
                version_metadata=version.metadata,
            ),
            profile,
        )
        for chunk in chunks
    }


async def test_actual_source_update_preserves_unchanged_embedding_inputs_and_policy() -> None:
    """Real parser/chunker occurrence fingerprints change without invalidating unchanged input cache keys."""
    repository = _Repository()
    service = IngestionService(repository, profile=replace(structural_token_profile(), target_size=32, overlap=0))
    content = "# Stable\n\n" + "Unchanged searchable passage. " * 40 + "\n\n# Edited\n\n" + "Original value. " * 40
    first = await service.ingest(_CONTEXT, upload=_upload(content.encode(), filename="notes.md"))
    _, old_version, old_chunks = repository.active[first.job.source_id]
    old_inputs = _embedding_inputs(old_version, old_chunks)
    await service.ingest(
        _CONTEXT,
        upload=_upload(
            content.replace("Original", "Modified", 1).encode(),
            filename="notes.md",
            key="source-edit-reuse-key",
            source_id=first.job.source_id,
            expected_active_version_id=first.job.effective_version_id,
        ),
    )
    _, version, chunks = repository.active[first.job.source_id]
    inputs = _embedding_inputs(version, chunks)
    unchanged = inputs.keys() & old_inputs.keys()
    assert unchanged and inputs.keys() - old_inputs.keys()
    for name in ("processing_profile_fingerprint", "chunking_profile_fingerprint", "source_sha256"):
        assert version.metadata[name] != old_version.metadata[name]
    assert all(inputs[key] == old_inputs[key] for key in unchanged)
    assert chunks[0].chunk_id != old_chunks[0].chunk_id


async def test_actual_processing_policy_changes_invalidate_embedding_reuse(tmp_path: Path) -> None:
    """Effective chunker/native guard policy matters; YAML comments and selection provenance do not."""
    content = b"Short identical text stays in one chunk."

    async def prepare(settings: DocumentProcessingSettings) -> tuple[SourceVersion, list[Chunk]]:
        repository = _Repository()
        result = await IngestionService(repository, processing=settings).ingest(_CONTEXT, upload=_upload(content))
        _, version, chunks = repository.active[result.job.source_id]
        return version, chunks

    baseline = await prepare(DocumentProcessingSettings())
    initial = _embedding_inputs(*baseline)
    configuration = tmp_path / "processing.yaml"
    configuration.write_text("# Same effective policy\ndocument_processing: {}\n", encoding="utf-8")
    loaded = await prepare(load_document_processing({"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": str(configuration)}))
    assert baseline[0].metadata["document_processing"] != loaded[0].metadata["document_processing"]
    assert _embedding_inputs(*loaded) == initial
    for policy in ({"recursive_splitter": {"split_length": 400}}, {"native_model_guard": {"max_tokens": 4096}}):
        changed = await prepare(DocumentProcessingSettings.model_validate(policy))
        inputs = _embedding_inputs(*changed)
        assert inputs.keys() == initial.keys()
        assert next(iter(inputs.values()))[0] == next(iter(initial.values()))[0]
        assert next(iter(inputs.values()))[1] != next(iter(initial.values()))[1]


@pytest.mark.parametrize("bom", [False, True])
@pytest.mark.parametrize("filename", ["notes.txt", "notes.md"])
@pytest.mark.parametrize(
    "text", ["English searchabletoken.", "Русский поисковыйтокен.", "Український пошуковиймаркер."]
)
async def test_real_processing_publishes_only_complete_lexical_records(filename: str, text: str, bom: bool) -> None:
    """Actual parsers and prepared chunks feed the one atomic publication port, without embeddings/pages."""
    repository = _Repository()
    source = ("# Heading\r\n\r\n" if filename.endswith(".md") else "") + text
    content = (b"\xef\xbb\xbf" if bom else b"") + source.encode()
    result = await IngestionService(repository).ingest(_CONTEXT, upload=_upload(content, filename=filename))
    job = result.job
    assert job.status == "completed" and job.outcome == "created" and not result.replayed
    assert repository.transitions == ["parsing", "chunking", "publishing"]
    assert [timing.stage for timing in job.stages] == ["parsing", "chunking", "publication"]
    assert all(timing.duration_ms >= 0 for timing in job.stages)
    source_record, version, chunks = repository.active[job.source_id]
    assert source_record.title == filename
    assert version.content_hash == hashlib.sha256(content).hexdigest()
    assert version.metadata["source_sha256"] == version.content_hash
    assert version.metadata["language_policy"] == "configured_sentence_language"
    assert version.metadata["default_language"] == "en"
    assert version.metadata["original_content_available"] is False
    assert "local_original" not in version.metadata
    assert chunks and job.chunk_count == len(chunks)
    assert {chunk.metadata["unit"] for chunk in chunks} == {"token"}
    assert {chunk.metadata["target_size"] for chunk in chunks} == {500}
    assert {chunk.metadata["requested_overlap"] for chunk in chunks} == {50}
    assert all(chunk.metadata["sentence_language"] == "en" for chunk in chunks)
    assert all(chunk.embedding is chunk.embedding_profile_id is chunk.dimensions is None for chunk in chunks)
    assert all(chunk.page is None for chunk in chunks)
    for chunk in chunks:
        span = chunk.metadata["source_span"]
        assert isinstance(span, dict)
        start, end = span["start"], span["end"]
        assert type(start) is int and type(end) is int
        assert chunk.content == source[start:end]
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


async def test_completed_replay_never_reprocesses_even_after_server_profile_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same HTTP key replays its committed job independently of deployment policy revisions."""
    repository = _Repository()
    upload = _upload(b"actual persisted identity")
    first = await IngestionService(repository).ingest(_CONTEXT, upload=upload)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Terminal idempotency replay attempted processing")

    monkeypatch.setattr(ingestion_module, "parse_source", forbidden)
    monkeypatch.setattr(ingestion_module, "prepare_chunks", forbidden)
    monkeypatch.setattr(ingestion_module, "_INGESTION_POLICY_REVISION", "txt-markdown-structural-v2")
    changed = replace(structural_token_profile(), profile_revision="text-token-r2")
    replay = await IngestionService(repository, profile=changed).ingest(_CONTEXT, upload=upload)
    assert replay.replayed and replay.job == first.job
    assert len(repository.jobs) == len(repository.versions) == repository.complete_calls == 1


async def test_same_key_changed_bytes_conflicts_without_mutation() -> None:
    """A key reserves one immutable request, rather than a reusable upload slot."""
    repository = _Repository()
    service = IngestionService(repository)
    first = await service.ingest(_CONTEXT, upload=_upload(b"original content"))
    with pytest.raises(IngestionError) as failure:
        await service.ingest(_CONTEXT, upload=_upload(b"different content"))
    assert (failure.value.status, failure.value.code) == (409, "IDEMPOTENCY_CONFLICT")
    assert repository.jobs[first.job.job_id] == first.job
    assert len(repository.jobs) == len(repository.versions) == 1


async def test_job_callback_exposes_identity_before_processing_and_on_terminal_replay() -> None:
    """The HTTP boundary can retain a durable job ID even when its outer deadline expires."""
    repository = _Repository()
    service = IngestionService(repository)
    observed: list[tuple[str, str, int]] = []

    def on_job(job: IngestionJob) -> None:
        observed.append((job.job_id, job.status, len(repository.transitions)))

    upload = _upload(b"callback identity")
    first = await service.ingest(_CONTEXT, upload=upload, on_job=on_job)
    replay = await service.ingest(_CONTEXT, upload=upload, on_job=on_job)
    assert replay.job.job_id == first.job.job_id
    assert observed == [(first.job.job_id, "pending", 0), (first.job.job_id, "completed", 3)]


async def test_unchanged_content_reports_actual_existing_count_without_new_version() -> None:
    """A fresh key may confirm unchanged content while retaining all original chunk/version identities."""
    repository = _Repository()
    service = IngestionService(repository)
    content = b"Long text for actual token-based chunking. " * 400
    first = await service.ingest(_CONTEXT, upload=_upload(content))
    old_chunks = repository.active[first.job.source_id][2]
    assert len(old_chunks) > 1
    result = await service.ingest(
        _CONTEXT,
        upload=_upload(
            content,
            key="another-upload-key",
            source_id=first.job.source_id,
            expected_active_version_id=first.job.effective_version_id,
        ),
    )
    assert result.job.outcome == "unchanged"
    assert result.job.effective_version_id == first.job.effective_version_id
    assert result.job.chunk_count == len(old_chunks)
    assert repository.active[first.job.source_id][2] == old_chunks
    assert len(repository.versions) == 1 and len(repository.jobs) == 2


async def test_new_key_current_policy_change_reprocesses_same_bytes() -> None:
    """Unchanged bytes cannot hide a different current processing fingerprint."""
    repository = _Repository()
    content = b"processing revision example"
    first = await IngestionService(repository).ingest(_CONTEXT, upload=_upload(content))
    changed = replace(structural_token_profile(), profile_revision="text-token-r2")
    result = await IngestionService(repository, profile=changed).ingest(
        _CONTEXT,
        upload=_upload(
            content,
            key="changed-profile-key",
            source_id=first.job.source_id,
            expected_active_version_id=first.job.effective_version_id,
        ),
    )
    assert result.job.outcome == "updated"
    assert result.job.effective_version_id != first.job.effective_version_id
    assert result.job.processing_profile_fingerprint != first.job.processing_profile_fingerprint
    assert len(repository.versions) == 2


async def test_upload_policy_revision_changes_aggregate_identity_without_relabeling_chunker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new upload policy reprocesses a fresh key while retaining the independently versioned chunker identity."""
    repository = _Repository()
    content = b"same bytes and same core chunker"
    first = await IngestionService(repository).ingest(_CONTEXT, upload=_upload(content))
    old_version = repository.active[first.job.source_id][1]
    old_chunks = repository.active[first.job.source_id][2]
    monkeypatch.setattr(ingestion_module, "_INGESTION_POLICY_REVISION", "txt-markdown-structural-v2")
    updated = await IngestionService(repository).ingest(
        _CONTEXT,
        upload=_upload(
            content,
            key="new-upload-policy-key",
            source_id=first.job.source_id,
            expected_active_version_id=first.job.effective_version_id,
        ),
    )
    new_version = repository.active[first.job.source_id][1]
    chunks = repository.active[first.job.source_id][2]
    assert updated.job.outcome == "updated"
    assert updated.job.processing_profile_fingerprint != first.job.processing_profile_fingerprint
    assert new_version.metadata["chunking_profile_fingerprint"] == old_version.metadata["chunking_profile_fingerprint"]
    assert chunks[0].metadata["processing_fingerprint"] == old_chunks[0].metadata["processing_fingerprint"]
    assert chunks[0].metadata["ingestion_processing_fingerprint"] == updated.job.processing_profile_fingerprint


async def test_markdown_protected_units_and_heading_provenance_are_preserved() -> None:
    """A real Markdown upload records faithful protected spans instead of invented table cells or pages."""
    repository = _Repository()
    content = b"# Heading\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n```python\n# not a heading\n```\n"
    result = await IngestionService(repository).ingest(_CONTEXT, upload=_upload(content, filename="notes.md"))
    _, version, chunks = repository.active[result.job.source_id]
    warnings = version.metadata["warnings"]
    assert isinstance(warnings, list)
    assert {"TABLE_UNPARSED", "CODE_FENCE_UNPARSED"} <= set(warnings)
    assert any("# not a heading" in chunk.content for chunk in chunks)
    assert all(chunk.page is None for chunk in chunks)
    assert all(chunk.metadata["heading_path"] == ["Heading"] for chunk in chunks)


async def test_empty_converter_output_cannot_complete_an_ingestion(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Haystack converter's silent skip becomes a real failed job, never an empty successful source."""

    def empty_conversion(*_args: Any, **_kwargs: Any) -> dict[str, list[Any]]:
        return {"documents": []}

    monkeypatch.setattr(TextFileToDocument, "run", empty_conversion)
    repository = _Repository()
    with pytest.raises(IngestionError) as failure:
        await IngestionService(repository).ingest(_CONTEXT, upload=_upload(b"valid UTF-8 source"))
    assert failure.value.code == "INVALID_DOCUMENT"
    assert failure.value.job_id is not None
    assert repository.jobs[failure.value.job_id].status == "failed"
    assert repository.complete_calls == 0 and not repository.active


@pytest.mark.parametrize(
    ("content", "filename", "mime", "status", "code"),
    [
        (b"\xffbroken", "notes.txt", None, 400, "INVALID_DOCUMENT"),
        (b"hello\0world", "notes.txt", None, 400, "INVALID_DOCUMENT"),
        (b" \t\r\n", "notes.md", None, 400, "INVALID_DOCUMENT"),
        (b"text", "../notes.txt", None, 400, "INVALID_DOCUMENT"),
        (b"text", "notes.md", "application/pdf", 415, "UNSUPPORTED_MEDIA_TYPE"),
        (b"%PDF-1.7", "notes.pdf", "application/pdf", 400, "PDF_CORRUPT"),
        (b"PK\x03\x04", "notes.zip", None, 415, "UNSUPPORTED_MEDIA_TYPE"),
    ],
)
async def test_parser_refusals_leave_durable_failure_without_publication(
    content: bytes, filename: str, mime: str | None, status: int, code: str
) -> None:
    """No malformed or unsupported source becomes a successful empty ingestion."""
    repository = _Repository()
    upload = UploadInput(content=content, filename=filename, declared_mime=mime, idempotency_key="bad-document-key")
    with pytest.raises(IngestionError) as failure:
        await IngestionService(repository).ingest(_CONTEXT, upload=upload)
    assert (failure.value.status, failure.value.code) == (status, code)
    assert failure.value.job_id
    assert repository.jobs[failure.value.job_id].status == "failed"
    assert repository.jobs[failure.value.job_id].stage == "parsing"
    assert repository.complete_calls == 0 and repository.active == {}


async def test_failed_replay_is_terminal_without_reprocessing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed immutable job requires a new key; replay cannot silently retry its parser."""
    repository = _Repository()
    service = IngestionService(repository)
    upload = _upload(b"\xffbroken")
    with pytest.raises(IngestionError) as first:
        await service.ingest(_CONTEXT, upload=upload)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Failed replay attempted processing")

    monkeypatch.setattr(ingestion_module, "parse_source", forbidden)
    with pytest.raises(IngestionError) as replay:
        await service.ingest(_CONTEXT, upload=upload)
    assert replay.value.code == first.value.code
    assert replay.value.job_id == first.value.job_id
    assert len(repository.jobs) == 1


@pytest.mark.parametrize("filename", ["notes.txt", "module.py"])
async def test_failed_publication_keeps_old_active_version(filename: str) -> None:
    """No standalone source writer or job-success update can escape the atomic port failure."""
    repository = _Repository()
    service = IngestionService(repository)
    first = await service.ingest(_CONTEXT, upload=_upload(b"# old searchabletoken", filename=filename))
    old_active = repository.active[first.job.source_id]
    repository.publication_failure = DatabaseUnavailable()
    with pytest.raises(IngestionError) as failure:
        await service.ingest(
            _CONTEXT,
            upload=_upload(
                b"# new searchabletoken",
                filename=filename,
                key="replacement-upload-key",
                source_id=first.job.source_id,
                expected_active_version_id=first.job.effective_version_id,
            ),
        )
    assert failure.value.code == "DEPENDENCY_UNAVAILABLE"
    assert repository.active[first.job.source_id] == old_active
    assert len(repository.versions) == 1
    assert failure.value.job_id is not None
    failed = repository.jobs[failure.value.job_id]
    assert failed.status == "failed" and failed.stage == "publishing"
    assert [timing.stage for timing in failed.stages] == ["parsing", "chunking", "publication"]


@pytest.mark.parametrize(
    ("error_code", "expected"),
    [
        (ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE, "DEPENDENCY_UNAVAILABLE"),
        (ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, "PAYLOAD_TOO_LARGE"),
    ],
)
async def test_chunk_failure_is_durable_and_never_publishes(
    monkeypatch: pytest.MonkeyPatch, error_code: ChunkingErrorCode, expected: str
) -> None:
    """Missing counter assets and structure overflow have stable failure outcomes."""

    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        raise ChunkingError(error_code)

    repository = _Repository()
    monkeypatch.setattr(ingestion_module, "prepare_chunks", unavailable)
    with pytest.raises(IngestionError) as failure:
        await IngestionService(repository).ingest(_CONTEXT, upload=_upload(b"valid source"))
    assert failure.value.code == expected
    assert failure.value.job_id is not None
    assert repository.jobs[failure.value.job_id].stage == "chunking"
    assert not repository.active


async def test_cancellation_never_publishes_after_pure_worker_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cancelled request can leave bounded pure work running, but it retains no publication continuation."""
    repository = _Repository()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = ingestion_module.parse_source

    def delayed_parse(*args: Any, **kwargs: Any) -> ParsedDocument:
        started.set()
        try:
            release.wait(timeout=3)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(ingestion_module, "parse_source", delayed_parse)
    task = asyncio.create_task(IngestionService(repository).ingest(_CONTEXT, upload=_upload(b"bounded pure task")))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        job = next(iter(repository.jobs.values()))
        assert job.status == "failed" and job.error_code == "INTERRUPTED"
    finally:
        release.set()
    assert await asyncio.to_thread(finished.wait, 2)
    await asyncio.sleep(0)
    assert repository.complete_calls == 0 and not repository.active


async def test_timeout_preserves_safe_terminal_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """A processing deadline is explicit and persists its failure before the request returns."""
    repository = _Repository()
    release = threading.Event()
    original = ingestion_module.parse_source

    def delayed_parse(*args: Any, **kwargs: Any) -> ParsedDocument:
        release.wait(timeout=2)
        return original(*args, **kwargs)

    monkeypatch.setattr(ingestion_module, "parse_source", delayed_parse)
    try:
        with pytest.raises(IngestionError) as failure:
            await IngestionService(repository).ingest(_CONTEXT, upload=_upload(b"deadline source"), timeout_seconds=0.2)
        assert (failure.value.status, failure.value.code) == (504, "INGESTION_TIMEOUT")
        assert failure.value.job_id is not None
        assert repository.jobs[failure.value.job_id].error_code == "INGESTION_TIMEOUT"
    finally:
        release.set()
    assert repository.complete_calls == 0


async def test_cancelled_workers_keep_cpu_slots_until_they_actually_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated cancelled HTTP work cannot create an unbounded queue of live conversion threads."""
    repository = _Repository()
    service = IngestionService(repository)
    release, both_started = threading.Event(), threading.Event()
    lock = threading.Lock()
    calls = 0
    original = ingestion_module.parse_source

    def delayed_parse(*args: Any, **kwargs: Any) -> ParsedDocument:
        nonlocal calls
        with lock:
            calls += 1
            if calls == 2:
                both_started.set()
        release.wait(timeout=3)
        return original(*args, **kwargs)

    monkeypatch.setattr(ingestion_module, "parse_source", delayed_parse)
    tasks = [
        asyncio.create_task(service.ingest(_CONTEXT, upload=_upload(b"bounded worker", key=f"worker-key-{index}")))
        for index in range(2)
    ]
    try:
        assert await asyncio.to_thread(both_started.wait, 1)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        with pytest.raises(IngestionError) as failure:
            await service.ingest(
                _CONTEXT, upload=_upload(b"third worker must wait", key="third-worker-key"), timeout_seconds=0.2
            )
        assert failure.value.code == "INGESTION_TIMEOUT"
        assert calls == 2
        assert repository.complete_calls == 0
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_dependency_failure_during_failure_recording_is_not_claimed_durable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unavailable database leaves a recovery-visible job rather than inventing a terminal commit."""
    repository = _Repository()
    repository.failure_recording_failure = True
    caplog.set_level(logging.INFO, logger="workbench.api")

    def broken_parse(*_args: Any, **_kwargs: Any) -> ParsedDocument:
        raise RuntimeError("private-body-and-dependency-canary")

    monkeypatch.setattr(ingestion_module, "parse_source", broken_parse)
    with pytest.raises(IngestionError) as failure:
        await IngestionService(repository).ingest(_CONTEXT, upload=_upload(b"private-source-canary"))
    assert failure.value.code == "INGESTION_FAILED"
    assert failure.value.job_id is not None
    assert repository.jobs[failure.value.job_id].status == "parsing"
    assert "ingestion_failure_unconfirmed" in caplog.text
    assert "private-body-and-dependency-canary" not in caplog.text
    assert "private-source-canary" not in caplog.text


async def test_ready_requires_both_storage_and_real_local_processing_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    """A running database alone does not advertise an executable upload capability."""
    repository = _Repository()
    service = IngestionService(repository)
    assert await service.ready(_CONTEXT)
    repository.available = False
    assert not await service.ready(_CONTEXT)
    repository.available = True

    def unavailable(**_kwargs: Any) -> bool:
        raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE)

    monkeypatch.setattr(ingestion_module, "_processing_available", unavailable)
    assert not await service.ready(_CONTEXT)


@pytest.mark.parametrize("language", ["en", "ru"])
async def test_configured_policy_controls_actual_ingestion_and_is_path_free(language: str) -> None:
    """The service uses the same explicit language and token settings that it persists."""
    repository = _Repository()
    settings = DocumentProcessingSettings.model_validate(
        {
            "default_language": language,
            "recursive_splitter": {
                "split_length": 40,
                "split_overlap": 7,
                "sentence_splitter_params": {"keep_white_spaces": False},
            },
        }
    )
    service = IngestionService(repository, processing=settings)
    result = await service.ingest(
        _CONTEXT, upload=_upload(("Dr. Smith read the report. Another sentence. " * 50).encode())
    )
    _source, version, chunks = repository.active[result.job.source_id]
    assert len(chunks) > 1
    assert version.metadata["default_language"] == language
    assert version.metadata["document_processing"] == service.processing_manifest()
    assert all(chunk.metadata["sentence_language"] == language for chunk in chunks)
    assert all(chunk.metadata["default_language"] == language for chunk in chunks)
    assert all(chunk.metadata["target_size"] == 40 and chunk.metadata["requested_overlap"] == 7 for chunk in chunks)
    for chunk in chunks:
        length = chunk.metadata["length_tiktoken"]
        assert isinstance(length, int) and length <= 40
    assert all(chunk.metadata["fallback_reasons"] == [] for chunk in chunks)
    decision = version.metadata["processing_profile"]
    assert isinstance(decision, dict)
    profile = decision["profile"]
    assert isinstance(profile, dict) and profile["sentence_keep_white_spaces"] is False
    assert "local_asset_directory" not in json.dumps(service.processing_manifest())


async def test_configured_missing_sentence_resource_refuses_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Required English Punkt qualification cannot become structural fallback during ingestion."""
    resources = replace(adapters.inspect_chunking_resources(), sentence_resource_revisions=())
    monkeypatch.setattr(adapters, "inspect_chunking_resources", lambda: resources)
    monkeypatch.setattr(ingestion_module, "inspect_chunking_resources", lambda: resources)
    repository = _Repository()
    service = IngestionService(repository)
    assert not await service.ready(_CONTEXT)
    with pytest.raises(IngestionError) as failure:
        await service.ingest(_CONTEXT, upload=_upload(b"No sentence fallback is allowed."))
    assert failure.value.code == "DEPENDENCY_UNAVAILABLE"
    assert failure.value.job_id is not None
    assert repository.jobs[failure.value.job_id].status == "failed"
    assert not repository.active


async def test_explicit_configured_structural_separators_do_not_claim_sentence_segmentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An intentional no-sentence configuration is distinct from an unavailable-resource fallback."""
    resources = replace(adapters.inspect_chunking_resources(), sentence_resource_revisions=())
    monkeypatch.setattr(adapters, "inspect_chunking_resources", lambda: resources)
    monkeypatch.setattr(ingestion_module, "inspect_chunking_resources", lambda: resources)
    settings = DocumentProcessingSettings.model_validate(
        {"recursive_splitter": {"split_length": 30, "split_overlap": 5, "separators": ["\n\n", "\n", " "]}}
    )
    repository = _Repository()
    service = IngestionService(repository, processing=settings)
    assert await service.ready(_CONTEXT)
    result = await service.ingest(_CONTEXT, upload=_upload(b"Explicit token boundaries preserve this text. " * 30))
    _source, version, chunks = repository.active[result.job.source_id]
    assert version.metadata["language_policy"] == "configured_structural_boundaries"
    assert version.metadata["default_language"] == "en"
    assert all(chunk.metadata["sentence_language"] is None for chunk in chunks)
    assert all(chunk.metadata["language_policy"] == "configured_structural_boundaries" for chunk in chunks)
    assert all(chunk.metadata["fallback_reasons"] == ["structural_profile_requested"] for chunk in chunks)


async def test_native_counter_loads_once_off_loop_and_qualified_input_is_guarded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A controlled counter proves service wiring; native tokenizer fidelity has separate actual-asset tests."""
    repository = _Repository()
    loads: list[int] = []
    inputs: list[str] = []

    class Counter:
        counter_revision = "injected-counter-r1"

        def count_tokens(self, text: str) -> int:
            inputs.append(text)
            return len(text) + 1

    def load(_directory: Path) -> Counter:
        loads.append(threading.get_ident())
        return Counter()

    monkeypatch.setattr(ingestion_module, "LocalQwenTokenCounter", load)
    settings = DocumentProcessingSettings.model_validate(
        {
            "native_model_guard": {
                "enabled": True,
                "local_asset_directory": str(tmp_path),
                "max_tokens": 500,
                "prefix": "operator-prefix-canary:",
                "suffix": ":operator-suffix-canary",
                "include_heading_path": True,
            }
        }
    )
    service = IngestionService(repository, processing=settings)
    assert not loads
    caplog.set_level(logging.INFO)
    assert await service.ready(_CONTEXT)
    result = await service.ingest(_CONTEXT, upload=_upload(b"# Heading\n\nBody", filename="native.md"))
    assert len(loads) == 1 and loads[0] != threading.get_ident()
    chunk = repository.active[result.job.source_id][2][0]
    expected = "operator-prefix-canary:Heading\n\n# Heading\n\nBody:operator-suffix-canary"
    assert expected in inputs
    assert chunk.metadata["length_model_token"] == len(expected) + 1
    assert chunk.metadata["model_counter_revision"] == "injected-counter-r1"
    manifest = json.dumps(service.processing_manifest())
    assert str(tmp_path) not in manifest
    assert "operator-prefix-canary" not in manifest and "operator-suffix-canary" not in manifest
    assert "prefix_sha256" in manifest and "suffix_sha256" in manifest
    events = [json.loads(record.message) for record in caplog.records if record.name == "workbench.api"]
    completed = [event for event in events if event.get("event") == "ingestion_processing_completed"]
    assert len(completed) == 1
    event = completed[0]
    assert event["job_id"] == result.job.job_id and event["workspace_id"] == _CONTEXT.workspace_id
    assert event["split_length"] == 500 and event["split_overlap"] == 50
    assert event["split_unit"] == "token" and event["tokenizer_encoding"] == "o200k_base"
    assert event["sentence_language"] == "en" and event["chunk_count"] == result.job.chunk_count
    assert event["native_guard_enabled"] == 1 and event["model_counter_revision"] == "injected-counter-r1"
    assert "operator-prefix-canary" not in caplog.text and "operator-suffix-canary" not in caplog.text
    assert str(tmp_path) not in caplog.text and "# Heading" not in caplog.text


async def test_enabled_missing_native_assets_are_durable_dependency_failure(tmp_path: Path) -> None:
    """Enabled guards remain enabled when approved assets are absent."""
    repository = _Repository()
    settings = DocumentProcessingSettings.model_validate(
        {"native_model_guard": {"enabled": True, "local_asset_directory": str(tmp_path)}}
    )
    service = IngestionService(repository, processing=settings)
    assert not await service.ready(_CONTEXT)
    with pytest.raises(IngestionError) as failure:
        await service.ingest(_CONTEXT, upload=_upload(b"A guarded document."))
    assert failure.value.code == "DEPENDENCY_UNAVAILABLE"
    assert failure.value.job_id is not None
    assert repository.jobs[failure.value.job_id].error_code == "DEPENDENCY_UNAVAILABLE"
    assert not repository.active


async def test_native_overflow_is_explicit_durable_and_content_free(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A separate model budget rejects without silently changing the tiktoken profile."""

    class Counter:
        counter_revision = "injected-overflow-counter-r1"

        def count_tokens(self, text: str) -> int:
            return len(text) + 1

    repository = _Repository()
    settings = DocumentProcessingSettings.model_validate(
        {"native_model_guard": {"enabled": True, "local_asset_directory": str(tmp_path), "max_tokens": 1}}
    )
    service = IngestionService(repository, processing=settings, model_counter=Counter())
    with caplog.at_level(logging.INFO), pytest.raises(IngestionError) as failure:
        await service.ingest(_CONTEXT, upload=_upload(b"native-overflow-source-canary"))
    assert (failure.value.code, failure.value.status, failure.value.retryable) == (
        "MODEL_TOKEN_LIMIT_EXCEEDED",
        413,
        False,
    )
    assert failure.value.job_id is not None
    assert repository.jobs[failure.value.job_id].error_code == "MODEL_TOKEN_LIMIT_EXCEEDED"
    assert not repository.active
    assert "ingestion_native_overflow" in caplog.text
    assert "native-overflow-source-canary" not in caplog.text


def test_legacy_profile_and_typed_processing_cannot_compete() -> None:
    """Internal profile injection cannot silently override the operator configuration."""
    with pytest.raises(ValueError, match="Choose one processing configuration"):
        IngestionService(_Repository(), profile=structural_token_profile(), processing=DocumentProcessingSettings())


async def test_configuration_provenance_changes_do_not_reindex_identical_effective_policy(tmp_path: Path) -> None:
    """File formatting and configuration source remain observable without changing effective processing identity."""
    repository = _Repository()
    content = b"Stable effective configuration."
    first = await IngestionService(repository, processing=DocumentProcessingSettings()).ingest(
        _CONTEXT, upload=_upload(content)
    )
    selected = tmp_path / "processing.yaml"
    selected.write_text("# Operator comment\ndocument_processing: {}\n", encoding="utf-8")
    settings = load_document_processing({"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": str(selected)})
    assert settings.safe_manifest()["configuration_provenance"]["source"] == "selected_operator_file"
    changed = await IngestionService(repository, processing=settings).ingest(
        _CONTEXT,
        upload=_upload(
            content,
            key="config-provenance-change",
            source_id=first.job.source_id,
            expected_active_version_id=first.job.effective_version_id,
        ),
    )
    assert changed.job.outcome == "unchanged"
    assert changed.job.effective_version_id == first.job.effective_version_id
    assert changed.job.processing_profile_fingerprint == first.job.processing_profile_fingerprint
    assert len(repository.versions) == 1
