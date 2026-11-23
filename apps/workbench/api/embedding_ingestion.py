"""Bounded durable embedding work; lexical publication and GPU admission retain their existing owners."""

import asyncio
import hashlib
import json
from contextlib import suppress
from dataclasses import dataclass
from time import monotonic
from typing import Any

from pydantic import ValidationError

from apps.workbench.api.chunking import ExactModelCounter, ModelTokenAdmission
from apps.workbench.api.document_processing import DocumentProcessingSettings
from apps.workbench.api.embedding import (
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingItem,
    EmbeddingPort,
    EmbeddingProfile,
    EmbeddingRequest,
    PreparedEmbeddingItem,
    prepare_embedding_request,
    validate_embedding_batch,
)
from apps.workbench.api.embedding_jobs import (
    EmbeddingCacheKey,
    EmbeddingCandidate,
    EmbeddingJob,
    EmbeddingOwnershipLost,
    EmbeddingPersistencePort,
    EmbeddingVector,
    EmbeddingWrite,
)
from apps.workbench.api.persistence import PersistenceError, WorkspaceContext


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def embedding_candidate_input(
    candidate: EmbeddingCandidate, profile: EmbeddingProfile, *, processing: DocumentProcessingSettings | None = None
) -> tuple[str, str]:
    """Reconstruct the admitted document format and fingerprint reusable processing policy, excluding occurrence IDs."""
    configuration = candidate.version_metadata.get("document_processing", {})
    stored_guard = configuration.get("native_model_guard", {}) if isinstance(configuration, dict) else {}
    prefix, suffix, include_heading = "", "", False
    if isinstance(stored_guard, dict) and stored_guard.get("enabled") is True:
        configured_guard = (processing or DocumentProcessingSettings()).native_model_guard
        prefix, suffix, include_heading = (
            configured_guard.prefix,
            configured_guard.suffix,
            configured_guard.include_heading_path,
        )
        if (
            stored_guard.get("prefix_sha256") != hashlib.sha256(prefix.encode()).hexdigest()
            or stored_guard.get("suffix_sha256") != hashlib.sha256(suffix.encode()).hexdigest()
            or stored_guard.get("include_heading_path", False) != include_heading
        ):
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
    headings = candidate.metadata.get("heading_path", [])
    if not isinstance(headings, list) or len(headings) > 6 or any(not isinstance(part, str) for part in headings):
        raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
    try:
        heading_bytes = json.dumps(headings, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except UnicodeError:
        raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST) from None
    if len(heading_bytes) > 8192:
        raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
    admission = ModelTokenAdmission(
        counter_revision=profile.tokenizer_revision,
        max_tokens=profile.max_tokens,
        prefix=prefix,
        suffix=suffix,
        include_heading_path=include_heading,
    )
    text = admission.embedding_input(candidate.content, heading_path=tuple(headings))
    decision = candidate.version_metadata.get("processing_profile", {})
    policy = {
        "input_revision": "durable-document-input-r2",
        "profile_fingerprint": profile.fingerprint,
        "processing": {
            name: candidate.version_metadata.get(name)
            for name in (
                "parser_id",
                "parser_revision",
                "detector_revision",
                "parser_contract_revision",
                "normalization_policy",
                "format_id",
                "ingestion_policy_revision",
                "language_policy",
                "default_language",
            )
        },
        # Publication fingerprints include source bytes and structure; only effective policy is reusable.
        "document_processing": {
            name: value for name, value in configuration.items() if name != "configuration_provenance"
        }
        if isinstance(configuration, dict)
        else {},
        "effective_chunking": {name: decision.get(name) for name in ("profile", "strategy", "token_counter_revision")}
        if isinstance(decision, dict)
        else {},
        "chunk_processing": {
            name: candidate.metadata.get(name)
            for name in (
                "ingestion_policy_revision",
                "strategy",
                "profile_id",
                "profile_revision",
                "unit",
                "target_size",
                "requested_overlap",
                "tokenizer_ref",
                "token_counter_revision",
                "model_counter_revision",
                "separator_profile_id",
                "separators",
                "sentence_language",
                "sentence_keep_white_spaces",
                "sentence_resource_revision",
            )
        },
        "prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        "suffix_sha256": hashlib.sha256(suffix.encode()).hexdigest(),
        "include_heading_path": include_heading,
    }
    return text, _digest(policy)


@dataclass(frozen=True)
class _PreparedOccurrence:
    candidate: EmbeddingCandidate
    item: EmbeddingItem
    prepared: PreparedEmbeddingItem
    processing_digest: str

    @property
    def key(self) -> EmbeddingCacheKey:
        return self.processing_digest, self.prepared.input_hash


class EmbeddingIngestionService:
    """Advance one leased source at a time with bounded pages, cache reuse and transactional commit fences."""

    def __init__(
        self,
        persistence: EmbeddingPersistencePort,
        provider: EmbeddingPort,
        *,
        profile: EmbeddingProfile,
        counter: ExactModelCounter,
        processing: DocumentProcessingSettings | None = None,
        lease_seconds: int = 120,
    ) -> None:
        if not 15 <= lease_seconds <= 600:
            raise ValueError("Embedding leases must be bounded between 15 and 600 seconds")
        self._persistence = persistence
        self._provider = provider
        self._profile = profile
        self._counter = counter
        self._processing = processing
        self._lease_seconds = lease_seconds
        self._job: EmbeddingJob | None = None
        self._context: str | None = None
        self._busy = asyncio.Lock()
        self._counts = {
            "processed_chunks": 0,
            "reused_chunks": 0,
            "generated_inputs": 0,
            "completed_jobs": 0,
            "failed_jobs": 0,
        }

    def statistics(self) -> dict[str, int]:
        """Return counts without retaining source text, vectors or provider diagnostics."""
        return dict(self._counts)

    def _request(self, context: WorkspaceContext, items: tuple[EmbeddingItem, ...]) -> EmbeddingRequest:
        return EmbeddingRequest(
            profile_id=self._profile.profile_id,
            profile_revision=self._profile.profile_revision,
            task_kind="document",
            workspace_id=context.workspace_id,
            trace_id=context.trace_id or "embedding-worker",
            items=items,
            deadline=monotonic() + self._profile.timeout_seconds,
        )

    def _prepare(self, context: WorkspaceContext, candidate: EmbeddingCandidate) -> _PreparedOccurrence:
        if candidate.workspace_id != context.workspace_id:
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        text, processing_digest = embedding_candidate_input(candidate, self._profile, processing=self._processing)
        item = EmbeddingItem(
            item_id=candidate.chunk_id, text=text, input_hash=hashlib.sha256(text.encode()).hexdigest()
        )
        prepared = prepare_embedding_request(self._profile, self._request(context, (item,)), self._counter)[0]
        return _PreparedOccurrence(
            candidate=candidate, item=item, prepared=prepared, processing_digest=processing_digest
        )

    async def _heartbeat(self, context: WorkspaceContext, job: EmbeddingJob) -> None:
        while True:
            await asyncio.sleep(min(20.0, self._lease_seconds / 3))
            await self._persistence.renew_embedding_job(context, job, lease_seconds=self._lease_seconds)

    async def _vectors(
        self, context: WorkspaceContext, occurrences: list[_PreparedOccurrence]
    ) -> tuple[list[_PreparedOccurrence], dict[EmbeddingCacheKey, EmbeddingVector], int]:
        keys = tuple(dict.fromkeys(item.key for item in occurrences))
        vectors = await self._persistence.lookup_embedding_cache(context, self._profile, keys=keys)
        misses: dict[EmbeddingCacheKey, _PreparedOccurrence] = {}
        chosen = []
        tokens = 0
        reused = 0
        for occurrence in occurrences:
            if occurrence.key not in vectors and occurrence.key not in misses:
                if tokens + occurrence.prepared.token_count > self._profile.max_batch_tokens:
                    break
                misses[occurrence.key] = occurrence
                tokens += occurrence.prepared.token_count
            elif occurrence.key in vectors:
                reused += 1
            chosen.append(occurrence)
        if misses:
            request = self._request(context, tuple(item.item for item in misses.values()))
            expected = prepare_embedding_request(self._profile, request, self._counter)
            output = await self._provider.embed(request)
            if (
                output.profile_id != self._profile.profile_id
                or output.profile_revision != self._profile.profile_revision
                or output.model_revision != self._profile.model_revision
                or output.model_digest != self._profile.model_digest
                or output.tokenizer_digest != self._profile.tokenizer_digest
                or output.task_kind != "document"
                or output.item_ids != tuple(item.item_id for item in expected)
                or output.input_hashes != tuple(item.input_hash for item in expected)
                or output.source_hashes != tuple(item.source_hash for item in expected)
                or output.token_counts != tuple(item.token_count for item in expected)
            ):
                raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
            checked = validate_embedding_batch(
                self._profile,
                request,
                expected,
                vectors=output.vectors,
                usage_tokens=output.usage_tokens,
                usage_provenance=output.usage_provenance,
                duration_ms=output.duration_ms,
            )
            vectors.update(zip(misses, checked.vectors, strict=True))
            self._counts["generated_inputs"] += len(misses)
        return chosen, vectors, reused

    async def _advance(self, context: WorkspaceContext, job: EmbeddingJob, *, max_items: int) -> None:
        candidates = await self._persistence.embedding_job_chunks(context, job, limit=max_items)
        if not candidates:
            completed = await self._persistence.commit_embedding_batch(
                context, job, self._profile, records=(), cursor=job.cursor, complete=True
            )
            self._counts["completed_jobs"] += int(completed.status == "completed")
            self._job = None
            return
        occurrences = [self._prepare(context, candidate) for candidate in candidates]
        chosen, vectors, reused = await self._vectors(context, occurrences)
        records = tuple(
            EmbeddingWrite(
                source_id=item.candidate.source_id,
                version_id=item.candidate.version_id,
                chunk_id=item.candidate.chunk_id,
                expected_content_hash=item.candidate.content_hash,
                processing_digest=item.processing_digest,
                input_hash=item.prepared.input_hash,
                vector=vectors[item.key],
            )
            for item in chosen
        )
        if not records or any(len(record.vector) != self._profile.dimensions for record in records):
            raise EmbeddingError(EmbeddingErrorCode.INVALID_DIMENSION)
        committed = await self._persistence.commit_embedding_batch(
            context, job, self._profile, records=records, cursor=records[-1].chunk_id
        )
        self._job = committed if committed.status == "running" else None
        self._counts["processed_chunks"] += len(records)
        self._counts["reused_chunks"] += reused

    async def process_one(self, context: WorkspaceContext, *, max_items: int | None = None) -> bool:
        """Advance one bounded page; return false only when no currently leaseable work remains."""
        page_size = self._profile.max_batch_items if max_items is None else max_items
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= self._profile.max_batch_items
        ):
            raise ValueError("Embedding page size must fit the immutable profile batch bound")
        if self._busy.locked():
            raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY)
        async with self._busy:
            if self._job is not None and self._context != context.workspace_id:
                raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
            job = self._job or await self._persistence.lease_embedding_job(
                context, self._profile, lease_seconds=self._lease_seconds
            )
            if job is None:
                return False
            self._job, self._context = job, context.workspace_id
            heartbeat = asyncio.create_task(self._heartbeat(context, job))
            work = asyncio.create_task(self._advance(context, job, max_items=page_size))
            try:
                done, _ = await asyncio.wait((work, heartbeat), return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in done:
                    await heartbeat
                await work
            except (EmbeddingError, ValidationError) as error:
                code = error.code.value if isinstance(error, EmbeddingError) else "INVALID_RESPONSE"
                unavailable = code in {"NOT_QUALIFIED", "IDENTITY_MISMATCH", "TOKENIZER_MISMATCH"}
                retryable = unavailable or code in {"MODEL_UNAVAILABLE", "RATE_LIMITED", "TIMEOUT", "CAPACITY_BUSY"}
                with suppress(EmbeddingOwnershipLost):
                    await self._persistence.fail_embedding_job(
                        context,
                        job,
                        error_code=code,
                        retryable=retryable,
                        retry_after_seconds=60 if unavailable else min(300, 2 ** min(job.attempts, 8)),
                    )
                self._job = None
                self._counts["failed_jobs"] += 1
                if unavailable:
                    raise
            except EmbeddingOwnershipLost:
                self._job = None
            except (PersistenceError, asyncio.CancelledError):
                self._job = None
                raise
            finally:
                work.cancel()
                heartbeat.cancel()
                await asyncio.gather(work, heartbeat, return_exceptions=True)
            return True
