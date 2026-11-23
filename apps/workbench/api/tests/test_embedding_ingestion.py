"""Worker tests exercise actual input preparation, safe cache keys and source/lease fencing."""

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import create_autospec

import pytest

from apps.workbench.api.document_processing import DocumentProcessingSettings
from apps.workbench.api.embedding import (
    EmbeddingBatch,
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingProfile,
    EmbeddingRequest,
    prepare_embedding_request,
    validate_embedding_batch,
)
from apps.workbench.api.embedding_ingestion import EmbeddingIngestionService, embedding_candidate_input
from apps.workbench.api.embedding_jobs import (
    EmbeddingCandidate,
    EmbeddingJob,
    EmbeddingOwnershipLost,
    EmbeddingPersistencePort,
)
from apps.workbench.api.persistence import WorkspaceContext


class _Counter:
    counter_revision = "worker-test-counter-r1"

    def count_tokens(self, text: str) -> int:
        return len(text.split()) + 1


class _Provider:
    def __init__(self, profile: EmbeddingProfile) -> None:
        self.profile = profile
        self.requests: list[EmbeddingRequest] = []
        self.error: EmbeddingErrorCode | None = None
        self.change_identity = False

    async def warm_up_async(self) -> None:
        return None

    async def close_async(self) -> None:
        return None

    async def embed(self, request: EmbeddingRequest) -> EmbeddingBatch:
        self.requests.append(request)
        if self.error is not None:
            raise EmbeddingError(self.error)
        prepared = prepare_embedding_request(self.profile, request, _Counter())
        batch = validate_embedding_batch(
            self.profile,
            request,
            prepared,
            vectors=tuple((1.0,) + (0.0,) * 31 for _ in request.items),
            usage_tokens=sum(item.token_count for item in prepared),
            usage_provenance="provider_reported",
            duration_ms=1.0,
        )
        return batch.model_copy(update={"model_digest": "0" * 64}) if self.change_identity else batch


def _profile(**changes: Any) -> EmbeddingProfile:
    return EmbeddingProfile(
        **{
            "profile_id": "worker-test",
            "profile_revision": "worker-test-r1",
            "provider_adapter_id": "tei-openai",
            "model_id": "fake-unit-test",
            "model_revision": "a" * 40,
            "model_digest": "b" * 64,
            "tokenizer_digest": "c" * 64,
            "tokenizer_revision": _Counter.counter_revision,
            "dimensions": 32,
            **changes,
        }
    )


def _candidate(chunk_id: str, text: str = "same reusable text") -> EmbeddingCandidate:
    return EmbeddingCandidate(
        workspace_id="development",
        source_id="source",
        version_id="version",
        chunk_id=chunk_id,
        content=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        metadata={"heading_path": ["Section"]},
        version_metadata={"parser_revision": "parser-r1", "processing_profile_fingerprint": "processing-r1"},
    )


def _job() -> EmbeddingJob:
    profile = _profile()
    return EmbeddingJob(
        workspace_id="development",
        job_id="job",
        source_id="source",
        version_id="version",
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_fingerprint=profile.fingerprint,
        status="running",
        attempts=1,
        owner_token="lease-owner",
    )


def _store() -> Any:
    store = create_autospec(EmbeddingPersistencePort, instance=True)
    store.lease_embedding_job.return_value = _job()
    store.lookup_embedding_cache.return_value = {}

    def commit(
        _context: WorkspaceContext, job: EmbeddingJob, _profile: EmbeddingProfile, **fields: Any
    ) -> EmbeddingJob:
        return job.model_copy(
            update={"cursor": fields["cursor"], "status": "completed" if fields.get("complete") else "running"}
        )

    store.commit_embedding_batch.side_effect = commit
    return store


def _worker(store: Any, provider: _Provider, *, profile: EmbeddingProfile | None = None) -> EmbeddingIngestionService:
    return EmbeddingIngestionService(store, provider, profile=profile or provider.profile, counter=_Counter())


def test_input_reuse_ignores_occurrence_but_binds_processing_and_model_policy() -> None:
    """Compatible content may cross source versions only within an identical input/processing namespace."""
    candidate, profile = _candidate("first"), _profile()
    original = embedding_candidate_input(candidate, profile)
    assert (
        embedding_candidate_input(candidate.model_copy(update={"version_id": "next", "chunk_id": "other"}), profile)
        == original
    )
    assert (
        embedding_candidate_input(
            candidate.model_copy(
                update={"version_metadata": {**candidate.version_metadata, "parser_revision": "parser-r2"}}
            ),
            profile,
        )[1]
        != original[1]
    )
    assert embedding_candidate_input(candidate, profile.model_copy(update={"model_digest": "d" * 64}))[1] != original[1]


def test_stored_heading_prefix_policy_is_reconstructed_and_mismatch_refused(tmp_path: Path) -> None:
    """Actual admission prefixes must match the historical hashes before any model call."""
    processing = DocumentProcessingSettings.model_validate(
        {
            "native_model_guard": {
                "enabled": True,
                "prefix": "passage: ",
                "include_heading_path": True,
                "local_asset_directory": str(tmp_path),
            }
        }
    )
    candidate = _candidate("item").model_copy(
        update={
            "version_metadata": {
                "document_processing": {"native_model_guard": processing.safe_manifest()["native_model_guard"]}
            }
        }
    )
    text, _ = embedding_candidate_input(candidate, _profile(), processing=processing)
    assert text == "passage: Section\n\nsame reusable text"
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.INVALID_REQUEST):
        embedding_candidate_input(candidate, _profile())


def test_valid_long_heading_retains_the_existing_chunking_contract() -> None:
    """Accepted Markdown headings must not poison a job, including headings omitted from model input."""
    candidate = _candidate("long-heading").model_copy(update={"metadata": {"heading_path": ["Д" * 3000]}})
    text, _ = embedding_candidate_input(candidate, _profile())
    assert text == candidate.content


@pytest.mark.parametrize("heading", ["Д" * 4096, "\ud800"])
def test_heading_metadata_remains_bounded_by_canonical_utf8_bytes(heading: str) -> None:
    """The existing 8192-byte total bound and valid Unicode still apply before any inference."""
    candidate = _candidate("invalid-heading").model_copy(update={"metadata": {"heading_path": [heading]}})
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.INVALID_REQUEST):
        embedding_candidate_input(candidate, _profile())


@pytest.mark.asyncio
async def test_duplicate_occurrences_generate_one_input_and_commit_all_source_mappings() -> None:
    """Deduplication saves inference while retaining separate version/chunk references."""
    store, provider = _store(), _Provider(_profile())
    store.embedding_job_chunks.side_effect = [(_candidate("a"), _candidate("b")), ()]
    worker = _worker(store, provider)
    context = WorkspaceContext(workspace_id="development")
    assert await worker.process_one(context)
    records = store.commit_embedding_batch.call_args.kwargs["records"]
    assert [item.chunk_id for item in records] == ["a", "b"]
    assert len(provider.requests) == 1 and len(provider.requests[0].items) == 1
    assert records[0].input_hash == records[1].input_hash
    assert await worker.process_one(context)
    assert store.commit_embedding_batch.call_args.kwargs["complete"] is True
    assert worker.statistics()["processed_chunks"] == 2
    assert worker.statistics()["generated_inputs"] == 1


@pytest.mark.asyncio
async def test_compatible_cache_avoids_provider_dispatch() -> None:
    """Cached ready vectors attach to the new occurrence without opening another inference path."""
    store, provider = _store(), _Provider(_profile())
    candidate = _candidate("cached")
    text, processing_digest = embedding_candidate_input(candidate, provider.profile)
    store.lookup_embedding_cache.return_value = {
        (processing_digest, hashlib.sha256(text.encode()).hexdigest()): (1.0,) + (0.0,) * 31
    }
    store.embedding_job_chunks.return_value = (candidate,)
    worker = _worker(store, provider)
    assert await worker.process_one(WorkspaceContext(workspace_id="development"))
    assert not provider.requests
    assert worker.statistics()["reused_chunks"] == 1


@pytest.mark.asyncio
async def test_batch_token_bound_commits_only_a_contiguous_prefix() -> None:
    """A smaller profile batch cap must not skip unprocessed chunk IDs in the durable cursor."""
    profile = _profile(max_tokens=4, max_batch_tokens=4)
    store, provider = _store(), _Provider(profile)
    store.embedding_job_chunks.return_value = (_candidate("a", "first text"), _candidate("b", "second text"))
    assert await _worker(store, provider).process_one(WorkspaceContext(workspace_id="development"))
    fields = store.commit_embedding_batch.call_args.kwargs
    assert fields["cursor"] == "a" and len(fields["records"]) == 1
    assert len(provider.requests[0].items) == 1


@pytest.mark.asyncio
async def test_smaller_page_preserves_profile_identity_and_limits_database_read() -> None:
    """Quota smoothing may reduce a packet without creating an uncalibrated model profile."""
    profile = _profile(max_batch_items=8)
    store, provider = _store(), _Provider(profile)
    store.embedding_job_chunks.return_value = (_candidate("a"),)
    context = WorkspaceContext(workspace_id="development")
    assert await _worker(store, provider).process_one(context, max_items=4)
    assert store.embedding_job_chunks.call_args.kwargs["limit"] == 4
    assert provider.requests[0].profile_revision == profile.profile_revision


@pytest.mark.asyncio
@pytest.mark.parametrize("page_size", [0, 9, True])
async def test_page_limit_cannot_expand_calibrated_batch_or_start_work(page_size: int) -> None:
    """Invalid operator pacing bounds fail before leasing or provider dispatch."""
    store, provider = _store(), _Provider(_profile(max_batch_items=8))
    with pytest.raises(ValueError, match="page size"):
        await _worker(store, provider).process_one(WorkspaceContext(workspace_id="development"), max_items=page_size)
    store.lease_embedding_job.assert_not_called()
    assert not provider.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [EmbeddingErrorCode.RATE_LIMITED, EmbeddingErrorCode.MODEL_UNAVAILABLE])
async def test_retryable_provider_failure_preserves_queue_without_writing_vectors(code: EmbeddingErrorCode) -> None:
    """A transport failure records bounded retry state and never advances the cursor."""
    store, provider = _store(), _Provider(_profile())
    provider.error = code
    store.embedding_job_chunks.return_value = (_candidate("a"),)
    assert await _worker(store, provider).process_one(WorkspaceContext(workspace_id="development"))
    store.commit_embedding_batch.assert_not_called()
    assert store.fail_embedding_job.call_args.kwargs["retryable"] is True
    assert store.fail_embedding_job.call_args.kwargs["error_code"] == code.value


@pytest.mark.asyncio
async def test_expired_capacity_pauses_worker_without_poisoning_the_corpus() -> None:
    """Recalibration is an operator concern rather than a permanent document failure."""
    store, provider = _store(), _Provider(_profile())
    provider.error = EmbeddingErrorCode.NOT_QUALIFIED
    store.embedding_job_chunks.return_value = (_candidate("a"),)
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.NOT_QUALIFIED):
        await _worker(store, provider).process_one(WorkspaceContext(workspace_id="development"))
    store.commit_embedding_batch.assert_not_called()
    assert store.fail_embedding_job.call_args.kwargs["retryable"] is True
    assert store.fail_embedding_job.call_args.kwargs["retry_after_seconds"] == 60


@pytest.mark.asyncio
async def test_wrong_model_response_is_poisoned_before_persistence() -> None:
    """A typed but forged provider result cannot certify another model's vector."""
    store, provider = _store(), _Provider(_profile())
    provider.change_identity = True
    store.embedding_job_chunks.return_value = (_candidate("a"),)
    assert await _worker(store, provider).process_one(WorkspaceContext(workspace_id="development"))
    store.commit_embedding_batch.assert_not_called()
    assert store.fail_embedding_job.call_args.kwargs["retryable"] is False


@pytest.mark.asyncio
async def test_source_replacement_abandons_late_result_and_leases_fresh_work() -> None:
    """A stale lease is a normal fence outcome and cannot attach paid output to a new source version."""
    store, provider = _store(), _Provider(_profile())
    store.embedding_job_chunks.return_value = (_candidate("a"),)
    store.commit_embedding_batch.side_effect = EmbeddingOwnershipLost()
    worker = _worker(store, provider)
    context = WorkspaceContext(workspace_id="development")
    assert await worker.process_one(context)
    store.lease_embedding_job.return_value = None
    assert not await worker.process_one(context)
    assert worker.statistics()["processed_chunks"] == 0
