"""Bounded TXT/Markdown ingestion through qualified processing and the existing atomic publication port."""

import asyncio
import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from functools import partial
from math import isfinite
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Literal, TypeVar

from apps.workbench.api.boundary import log_event
from apps.workbench.api.chunking import ChunkingInput, ExactModelCounter, ModelTokenAdmission, prepare_chunks
from apps.workbench.api.chunking_adapters import inspect_chunking_resources
from apps.workbench.api.chunking_profiles import (
    ChunkingDecision,
    ChunkingError,
    ChunkingErrorCode,
    ChunkingProfile,
    DocumentFeatures,
    PdfChunkingProfile,
    PythonChunkingProfile,
    resolve_profile,
)
from apps.workbench.api.document_processing import DocumentProcessingSettings
from apps.workbench.api.model_token_counter import LocalQwenTokenCounter
from apps.workbench.api.parser_registry import ElementKind, FormatId, ParseErrorCode, ParsingError, select_parser
from apps.workbench.api.parsing import ParsedDocument, parse_source
from apps.workbench.api.persistence import (
    Chunk,
    CorpusLimitExceeded,
    DocumentNotFound,
    IdempotencyConflict,
    IngestionInProgress,
    IngestionJob,
    IngestionOwnershipLost,
    IngestionTiming,
    PersistenceError,
    PersistencePort,
    Source,
    SourceVersion,
    UploadReservation,
    VersionConflict,
    WorkspaceContext,
    WorkspaceNotFound,
)
from apps.workbench.api.upload_policy import pdf_upload_candidate, upload_file_byte_limit

_T = TypeVar("_T")
_OPAQUE_ID = re.compile(r"[A-Za-z0-9_-]+")
_INGESTION_POLICY_REVISION = "txt-markdown-configured-v2"
_LANGUAGE_POLICY = "configured_sentence_language"
_NORMALIZATION_POLICY = "utf8-sig-exact-decoded-source-v1"
_ERROR_POLICIES = {
    "INVALID_REQUEST": (400, False),
    "INVALID_DOCUMENT": (400, False),
    "UNPARSEABLE_SOURCE": (400, False),
    "PDF_ENCRYPTED": (400, False),
    "NO_EXTRACTABLE_TEXT": (400, False),
    "PDF_TOO_LARGE": (413, False),
    "PDF_PARSE_TIMEOUT": (504, True),
    "PDF_LAYOUT_UNCERTAIN": (400, False),
    "PDF_CORRUPT": (400, False),
    "PDF_UNSAFE_CONTENT": (400, False),
    "PDF_RESOURCE_LIMIT": (413, False),
    "TABLE_STRUCTURE_UNCERTAIN": (400, False),
    "TABLE_OVERFLOW": (413, False),
    "PDF_BUSY": (429, True),
    "UNSUPPORTED_MEDIA_TYPE": (415, False),
    "PAYLOAD_TOO_LARGE": (413, False),
    "MODEL_TOKEN_LIMIT_EXCEEDED": (413, False),
    "DOCUMENT_NOT_FOUND": (404, False),
    "WORKSPACE_NOT_FOUND": (404, False),
    "IDEMPOTENCY_CONFLICT": (409, False),
    "VERSION_CONFLICT": (409, False),
    "INGESTION_IN_PROGRESS": (409, True),
    "INTERRUPTED": (409, True),
    "DEPENDENCY_UNAVAILABLE": (503, True),
    "INGESTION_TIMEOUT": (504, True),
    "INGESTION_FAILED": (500, True),
}


class IngestionError(Exception):
    """Safe application failure; raw source, filenames and dependency errors are never carried outward."""

    def __init__(self, code: str, *, job_id: str | None = None) -> None:
        self.code = code if code in _ERROR_POLICIES else "INGESTION_FAILED"
        self.status, self.retryable = _ERROR_POLICIES[self.code]
        self.job_id = job_id
        super().__init__(self.code)


@dataclass(frozen=True)
class UploadInput:
    """Bounded transport data; the shared parser remains authoritative for filename, MIME and content."""

    content: bytes
    filename: str
    declared_mime: str | None
    idempotency_key: str
    source_id: str | None = None
    expected_active_version_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes) or not isinstance(self.filename, str):
            raise IngestionError("INVALID_REQUEST")
        if len(self.content) > upload_file_byte_limit(filename=self.filename, declared_mime=self.declared_mime):
            raise IngestionError("PAYLOAD_TOO_LARGE")
        if (
            not self.filename
            or len(self.filename) > 1024
            or self.declared_mime is not None
            and (not isinstance(self.declared_mime, str) or len(self.declared_mime) > 256)
            or not isinstance(self.idempotency_key, str)
            or not 8 <= len(self.idempotency_key) <= 128
            or _OPAQUE_ID.fullmatch(self.idempotency_key) is None
            or (self.source_id is None) != (self.expected_active_version_id is None)
        ):
            raise IngestionError("INVALID_REQUEST")
        for value in (self.source_id, self.expected_active_version_id):
            if value is not None and (
                not isinstance(value, str) or not 1 <= len(value) <= 128 or _OPAQUE_ID.fullmatch(value) is None
            ):
                raise IngestionError("INVALID_REQUEST")
        try:
            self.filename.encode("utf-8")
            if self.declared_mime is not None:
                self.declared_mime.encode("utf-8")
        except UnicodeError:
            raise IngestionError("INVALID_REQUEST") from None


@dataclass(frozen=True)
class IngestionResult:
    """Only a durably completed job is returned as success; replay preserves its original identities."""

    job: IngestionJob
    replayed: bool = False


@dataclass
class _Progress:
    job: IngestionJob
    owner_token: str = field(repr=False)
    stages: list[IngestionTiming] = field(default_factory=list)


@dataclass(frozen=True)
class _Publication:
    source: Source
    version: SourceVersion
    chunks: tuple[Chunk, ...]
    decision: ChunkingDecision[ChunkingProfile | PythonChunkingProfile | PdfChunkingProfile]


def _request_fingerprint(upload: UploadInput, source_sha256: str) -> str:
    payload = {
        "request_contract": "txt-markdown-upload-v1",
        "source_sha256": source_sha256,
        "filename": unicodedata.normalize("NFC", upload.filename),
        "declared_mime": upload.declared_mime.strip().lower() if upload.declared_mime is not None else None,
        "source_id": upload.source_id,
        "expected_active_version_id": upload.expected_active_version_id,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _prepare_publication(
    *,
    upload: UploadInput,
    parsed: ParsedDocument,
    job: IngestionJob,
    profile: ChunkingProfile,
    language: str,
    language_policy: str,
    configuration: dict[str, Any],
    model_admission: ModelTokenAdmission | None,
    model_counter: ExactModelCounter | None,
) -> _Publication:
    prepared = prepare_chunks(
        ChunkingInput(
            parsed_document=parsed,
            normalized_content=parsed.extracted_text
            if parsed.extracted_text is not None
            else upload.content.decode("utf-8-sig"),
            workspace_id=job.workspace_id,
            source_id=job.source_id,
            source_version_id=job.reserved_version_id,
            language=language,
        ),
        profile=profile,
        model_admission=model_admission,
        model_counter=model_counter,
    )
    policy_revision = _INGESTION_POLICY_REVISION
    if parsed.format_id is FormatId.PYTHON:
        policy_revision = "python-ast-ingestion-v1"
        language_policy = "python_source_language_independent"
        configuration = {
            "python_splitter": asdict(PythonChunkingProfile()),
            "native_model_guard": configuration.get("native_model_guard", {}),
        }
    elif parsed.format_id is FormatId.PDF:
        policy_revision = "pdf-page-layout-ingestion-v1"
        language_policy = "pdf_source_locale_unqualified"
        configuration = {
            "pdf_profile": asdict(PdfChunkingProfile()),
            "native_model_guard": configuration.get("native_model_guard", {}),
        }
    warnings = tuple(
        dict.fromkeys(parsed.warning_codes + tuple(code for chunk in prepared for code in chunk.warning_codes))
    )
    processing = json.loads(json.dumps(asdict(prepared[0].decision)))
    ingestion_policy = {
        "ingestion_policy_revision": policy_revision,
        "language_policy": language_policy,
        "default_language": language if parsed.format_id not in (FormatId.PYTHON, FormatId.PDF) else None,
        "normalization_policy": _NORMALIZATION_POLICY,
        "chunking_profile_fingerprint": prepared[0].processing_fingerprint,
        "document_processing": configuration,
    }
    effective_policy = {
        **ingestion_policy,
        "document_processing": {
            key: value for key, value in configuration.items() if key != "configuration_provenance"
        },
    }
    fingerprint = hashlib.sha256(json.dumps(effective_policy, sort_keys=True).encode()).hexdigest()
    version_metadata = {
        "source_sha256": parsed.source_sha256,
        "source_bytes": parsed.inspected_source.bytes_count,
        **ingestion_policy,
        "format_id": parsed.format_id.value,
        "parser_id": parsed.parser_id,
        "parser_revision": parsed.parser_revision,
        "detector_revision": parsed.detector_revision,
        "parser_contract_revision": parsed.contract_revision,
        "parsed_element_count": len(parsed.elements),
        "processing_profile_fingerprint": fingerprint,
        "processing_profile": processing,
        "warnings": list(warnings),
        "original_content_available": False,
    }
    if parsed.pdf_document is not None:
        pdf = parsed.pdf_document
        version_metadata.update(
            {
                "pdf_pages": len(pdf.pages),
                "pdf_tables": sum(b.kind == "table" for b in pdf.blocks),
                "pdf_parser_seconds": pdf.parser_seconds,
                "pdf_peak_memory_bytes": pdf.peak_memory_bytes,
                "pdf_cpu_seconds": pdf.cpu_seconds,
                "pdf_assets_revision": pdf.assets_revision,
                "pdf_ocr_enabled": False,
                "visual_region_count": len(pdf.visual_regions),
                "visual_regions": [region.model_dump(mode="json") for region in pdf.visual_regions],
                "visual_processing_status": pdf.visual_processing_status,
                "visual_detection_coverage": pdf.visual_detection_coverage,
                "original_evidence_status": pdf.original_evidence_status,
                "evidence_processing_revision": pdf.processing_revision,
            }
        )
    chunks = []
    for item in prepared:
        chunk = item.to_chunk(title=parsed.inspected_source.safe_basename)
        chunk.metadata["ingestion_processing_fingerprint"] = fingerprint
        chunk.metadata["ingestion_policy_revision"] = policy_revision
        if parsed.format_id is FormatId.PYTHON:
            chunk.metadata["source_file"] = parsed.inspected_source.safe_basename
        chunk.metadata["language_policy"] = language_policy
        chunk.metadata["default_language"] = (
            language if parsed.format_id not in (FormatId.PYTHON, FormatId.PDF) else None
        )
        chunks.append(chunk)
    return _Publication(
        source=Source(
            workspace_id=job.workspace_id,
            source_id=job.source_id,
            title=parsed.inspected_source.safe_basename,
            media_type=parsed.inspected_source.verified_mime,
            metadata={"origin": "uploaded", "original_content_available": False},
        ),
        version=SourceVersion(
            workspace_id=job.workspace_id,
            source_id=job.source_id,
            version_id=job.reserved_version_id,
            content_hash=parsed.source_sha256,
            metadata=version_metadata,
        ),
        chunks=tuple(chunks),
        decision=prepared[0].decision,
    )


def _parse_failure_code(error: ParsingError) -> str:
    if error.code.value in _ERROR_POLICIES:
        return error.code.value
    if error.code is ParseErrorCode.UNPARSEABLE_SOURCE:
        return "UNPARSEABLE_SOURCE"
    if error.reason == "DEADLINE_EXCEEDED":
        return "INGESTION_TIMEOUT"
    if error.code is ParseErrorCode.CONTENT_LIMIT_EXCEEDED:
        return "PAYLOAD_TOO_LARGE"
    if error.code is ParseErrorCode.UNSUPPORTED_FORMAT or error.reason in {
        "FORMAT_NOT_QUALIFIED",
        "INVALID_MIME",
        "MIME_EXTENSION_CONFLICT",
        "BINARY_SIGNATURE",
    }:
        return "UNSUPPORTED_MEDIA_TYPE"
    if error.code is ParseErrorCode.PARSER_UNAVAILABLE:
        return "DEPENDENCY_UNAVAILABLE"
    return "INGESTION_FAILED" if error.code is ParseErrorCode.PARSE_FAILED else "INVALID_DOCUMENT"


def _chunk_failure_code(error: ChunkingError) -> str:
    if error.reason == "TABLE_OVERFLOW":
        return "TABLE_OVERFLOW"
    if error.reason.startswith("PDF_TABLE_"):
        return "TABLE_STRUCTURE_UNCERTAIN"
    if error.code is ChunkingErrorCode.MODEL_TOKEN_LIMIT_EXCEEDED:
        return "MODEL_TOKEN_LIMIT_EXCEEDED"
    if error.code is ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED:
        return "PAYLOAD_TOO_LARGE"
    if error.code in {
        ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE,
        ChunkingErrorCode.SENTENCE_RESOURCE_UNAVAILABLE,
        ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE,
    }:
        return "DEPENDENCY_UNAVAILABLE"
    return "INGESTION_FAILED" if error.code is ChunkingErrorCode.CHUNKING_FAILED else "INVALID_DOCUMENT"


def _mapped_error(error: Exception, *, job_id: str | None = None) -> IngestionError:
    if isinstance(error, IngestionError):
        return IngestionError(error.code, job_id=job_id or error.job_id)
    if isinstance(error, ParsingError):
        return IngestionError(_parse_failure_code(error), job_id=job_id)
    if isinstance(error, ChunkingError):
        return IngestionError(_chunk_failure_code(error), job_id=job_id)
    for kind, code in (
        (WorkspaceNotFound, "WORKSPACE_NOT_FOUND"),
        (DocumentNotFound, "DOCUMENT_NOT_FOUND"),
        (IdempotencyConflict, "IDEMPOTENCY_CONFLICT"),
        (VersionConflict, "VERSION_CONFLICT"),
        (IngestionOwnershipLost, "INGESTION_IN_PROGRESS"),
        (IngestionInProgress, "INGESTION_IN_PROGRESS"),
        (CorpusLimitExceeded, "PAYLOAD_TOO_LARGE"),
        (PersistenceError, "DEPENDENCY_UNAVAILABLE"),
    ):
        if isinstance(error, kind):
            return IngestionError(code, job_id=job_id or getattr(error, "job_id", None))
    return IngestionError("INGESTION_FAILED", job_id=job_id)


def _processing_available(*, profile: ChunkingProfile, language: str) -> bool:
    select_parser(FormatId.PLAIN_TEXT)
    select_parser(FormatId.MARKDOWN)
    resolve_profile(
        DocumentFeatures(FormatId.PLAIN_TEXT, False, (ElementKind.PARAGRAPH,), language=language),
        profile=profile,
        resources=inspect_chunking_resources(),
    )
    return True


class IngestionService:
    """Coordinate durable checkpoints; workers hold no persistence reference and never publish."""

    def __init__(
        self,
        repository: PersistencePort,
        *,
        profile: ChunkingProfile | None = None,
        processing: DocumentProcessingSettings | None = None,
        model_counter: ExactModelCounter | None = None,
    ) -> None:
        if profile is not None and processing is not None:
            raise ValueError("Choose one processing configuration")
        self._repository = repository
        self._processing = processing or DocumentProcessingSettings()
        self._profile = profile or self._processing.to_profile()
        self._language = (
            (profile.sentence_language or "en") if profile is not None else self._processing.default_language
        )
        self._language_policy = (
            "unqualified_source_locale"
            if profile is not None
            else _LANGUAGE_POLICY
            if self._profile.sentence_language is not None
            else "configured_structural_boundaries"
        )
        self._counter = model_counter
        self._counter_lock = Lock()
        self._workers = asyncio.Semaphore(2)

    def _model_counter(self) -> ExactModelCounter | None:
        guard = self._processing.native_model_guard
        if not guard.enabled:
            return None
        with self._counter_lock:
            if self._counter is None:
                if guard.local_asset_directory is None:
                    raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE)
                self._counter = LocalQwenTokenCounter(Path(guard.local_asset_directory))
            try:
                ModelTokenAdmission(counter_revision=self._counter.counter_revision, max_tokens=guard.max_tokens)
                empty_length = self._counter.count_tokens("")
            except Exception:
                raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE) from None
            if type(empty_length) is not int or empty_length <= 0:
                raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE)
            return self._counter

    def processing_manifest(self) -> dict[str, Any]:
        """Project effective operator policy without local asset paths or document text."""
        manifest = self._processing.safe_manifest()
        manifest["recursive_splitter"] = {
            "split_length": self._profile.target_size,
            "split_overlap": self._profile.overlap,
            "split_unit": self._profile.unit,
            "tokenizer_encoding": self._profile.tokenizer_encoding,
            "separators": list(self._profile.separators),
            "sentence_splitter_params": {
                "language": self._language,
                "keep_white_spaces": self._profile.sentence_keep_white_spaces,
            },
        }
        if self._counter is not None and self._processing.native_model_guard.enabled:
            manifest["native_model_guard"]["counter_revision"] = self._counter.counter_revision
        return manifest

    def _prepare(self, *, upload: UploadInput, parsed: ParsedDocument, job: IngestionJob) -> _Publication:
        counter = self._model_counter()
        guard = self._processing.native_model_guard
        admission = (
            ModelTokenAdmission(
                counter_revision=counter.counter_revision,
                max_tokens=guard.max_tokens,
                prefix=guard.prefix,
                suffix=guard.suffix,
                include_heading_path=guard.include_heading_path,
            )
            if counter is not None
            else None
        )
        return _prepare_publication(
            upload=upload,
            parsed=parsed,
            job=job,
            profile=self._profile,
            language=self._language,
            language_policy=self._language_policy,
            configuration=self.processing_manifest(),
            model_admission=admission,
            model_counter=counter,
        )

    def _ready_processing(self) -> bool:
        _processing_available(profile=self._profile, language=self._language)
        self._model_counter()
        return True

    async def ready(self, context: WorkspaceContext) -> bool:
        """Qualify migrated durable storage and installed processing resources without downloading assets."""
        try:
            if not await self._repository.ingestion_ready(context):
                return False
            return await self._pure(self._ready_processing)
        except (PersistenceError, ParsingError, ChunkingError, OSError):
            return False

    async def _pure(self, operation: Callable[[], _T]) -> _T:
        await self._workers.acquire()
        try:
            future = asyncio.get_running_loop().run_in_executor(None, operation)
        except BaseException:
            self._workers.release()
            raise

        def finished(work: asyncio.Future[_T]) -> None:
            self._workers.release()
            if not work.cancelled():
                work.exception()

        future.add_done_callback(finished)
        return await asyncio.shield(future)

    async def _transition(
        self, context: WorkspaceContext, progress: _Progress, stage: Literal["parsing", "chunking", "publishing"]
    ) -> None:
        progress.job = await self._repository.transition_ingestion(
            context, job_id=progress.job.job_id, owner_token=progress.owner_token, stage=stage
        )
        log_event("ingestion_stage", trace_id=context.trace_id or "none", job_id=progress.job.job_id, stage=stage)

    async def _stage(
        self,
        context: WorkspaceContext,
        progress: _Progress,
        stage: Literal["parsing", "chunking"],
        operation: Callable[[], _T],
    ) -> _T:
        await self._transition(context, progress, stage)
        started = perf_counter()
        try:
            return await self._pure(operation)
        finally:
            progress.stages.append(IngestionTiming(stage=stage, duration_ms=(perf_counter() - started) * 1000))

    async def _execute(self, context: WorkspaceContext, upload: UploadInput, progress: _Progress) -> IngestionResult:
        parsed = await self._stage(
            context,
            progress,
            "parsing",
            partial(parse_source, upload.content, safe_basename=upload.filename, declared_type=upload.declared_mime),
        )
        publication = await self._stage(
            context, progress, "chunking", partial(self._prepare, upload=upload, parsed=parsed, job=progress.job)
        )
        await self._transition(context, progress, "publishing")
        started = perf_counter()
        try:
            job = await self._repository.complete_ingestion_with_publication(
                context,
                job_id=progress.job.job_id,
                owner_token=progress.owner_token,
                source=publication.source,
                version=publication.version,
                chunks=list(publication.chunks),
                stages=progress.stages,
            )
        except BaseException:
            progress.stages.append(IngestionTiming(stage="publication", duration_ms=(perf_counter() - started) * 1000))
            raise
        if job.status != "completed" or job.effective_version_id is None or job.chunk_count is None:
            raise IngestionError("INGESTION_FAILED", job_id=job.job_id)
        effective = publication.decision.profile
        log_event(
            "ingestion_processing_completed",
            trace_id=context.trace_id or "none",
            workspace_id=context.workspace_id,
            job_id=job.job_id,
            profile_id=effective.profile_id,
            profile_revision=effective.profile_revision,
            strategy=publication.decision.strategy,
            split_length=effective.target_size,
            split_overlap=effective.overlap,
            split_unit=effective.unit,
            tokenizer_encoding=self._profile.tokenizer_encoding,
            sentence_language=(effective.sentence_language or "none")
            if isinstance(effective, ChunkingProfile)
            else "none",
            sentence_keep_white_spaces=int(effective.sentence_keep_white_spaces)
            if isinstance(effective, ChunkingProfile)
            else 0,
            chunk_count=job.chunk_count,
            native_guard_enabled=int(self._processing.native_model_guard.enabled),
            model_counter_revision=self._counter.counter_revision
            if self._processing.native_model_guard.enabled and self._counter is not None
            else "none",
        )
        return IngestionResult(job=job)

    async def _fail(self, context: WorkspaceContext, progress: _Progress, error: IngestionError) -> None:
        try:
            async with asyncio.timeout(3):
                await self._repository.fail_ingestion(
                    context,
                    job_id=progress.job.job_id,
                    owner_token=progress.owner_token,
                    error_code=error.code,
                    retryable=error.retryable,
                    stages=progress.stages,
                )
        except Exception:
            log_event(
                "ingestion_failure_unconfirmed",
                trace_id=context.trace_id or "none",
                job_id=progress.job.job_id,
                code=error.code,
            )

    async def _owned(
        self,
        context: WorkspaceContext,
        upload: UploadInput,
        reservation: UploadReservation,
        *,
        processing_deadline: float,
        total_timeout: asyncio.Timeout,
        on_job: Callable[[IngestionJob], None] | None,
    ) -> IngestionResult:
        job = reservation.job
        if not reservation.newly_reserved:
            if on_job is not None:
                on_job(job)
            if job.status == "completed":
                return IngestionResult(job=job, replayed=True)
            if job.status == "failed":
                raise IngestionError(job.error_code or "INGESTION_FAILED", job_id=job.job_id)
            raise IngestionError("INGESTION_IN_PROGRESS", job_id=job.job_id)
        if reservation.owner_token is None or job.workspace_id != context.workspace_id:
            raise IngestionError("INGESTION_FAILED", job_id=job.job_id)
        progress = _Progress(job=job, owner_token=reservation.owner_token)
        try:
            if on_job is not None:
                on_job(job)
            async with asyncio.timeout_at(processing_deadline):
                return await self._execute(context, upload, progress)
        except asyncio.CancelledError:
            timed_out = total_timeout.expired() or asyncio.get_running_loop().time() >= processing_deadline
            code = "INGESTION_TIMEOUT" if timed_out else "INTERRUPTED"
            await self._fail(context, progress, IngestionError(code, job_id=job.job_id))
            raise
        except Exception as original:
            error = (
                IngestionError("INGESTION_TIMEOUT", job_id=job.job_id)
                if isinstance(original, TimeoutError)
                else (_mapped_error(original, job_id=job.job_id))
            )
            if error.code == "MODEL_TOKEN_LIMIT_EXCEEDED":
                log_event(
                    "ingestion_native_overflow",
                    trace_id=context.trace_id or "none",
                    workspace_id=context.workspace_id,
                    job_id=job.job_id,
                    max_tokens=self._processing.native_model_guard.max_tokens,
                    code=error.code,
                )
            await self._fail(context, progress, error)
            raise error from None

    async def ingest(
        self,
        context: WorkspaceContext,
        *,
        upload: UploadInput,
        timeout_seconds: float = 30.0,
        on_job: Callable[[IngestionJob], None] | None = None,
    ) -> IngestionResult:
        """
        Reserve immutable identity, process once and publish with the completed durable job atomically.

        :param context: Server-resolved scope and safe request trace correlation.
        :param upload: Bounded bytes and immutable operation parameters; no filenames become paths or identities.
        :param timeout_seconds: At most 30 seconds for text or 210 for PDF; includes terminal failure persistence.
        :param on_job: Optional server callback exposing reserved or replayed job identity before processing starts.
        :returns: A committed completed job, with replay identity preserved and no duplicate publication.
        :raises IngestionError: Safe input, processing, ownership, availability or timeout failure.
        :raises asyncio.CancelledError: After best-effort durable interruption handling; no worker can later publish.
        """
        if (
            not isinstance(upload, UploadInput)
            or type(timeout_seconds) not in (int, float)
            or not isfinite(timeout_seconds)
            or not 0
            < timeout_seconds
            <= (210 if pdf_upload_candidate(upload.filename, upload.declared_mime, upload.content) else 30)
        ):
            raise IngestionError("INVALID_REQUEST")
        source_sha256 = hashlib.sha256(upload.content).hexdigest()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        processing_deadline = deadline - min(3.0, timeout_seconds / 5)
        total_timeout = asyncio.timeout_at(deadline)
        job_id: str | None = None
        try:
            async with (
                total_timeout,
                self._repository.reserve_ingestion(
                    context,
                    idempotency_key=upload.idempotency_key,
                    request_fingerprint=_request_fingerprint(upload, source_sha256),
                    source_content_sha256=source_sha256,
                    source_id=upload.source_id,
                    expected_active_version_id=upload.expected_active_version_id,
                ) as reservation,
            ):
                job_id = reservation.job.job_id
                return await self._owned(
                    context,
                    upload,
                    reservation,
                    processing_deadline=processing_deadline,
                    total_timeout=total_timeout,
                    on_job=on_job,
                )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise IngestionError("INGESTION_TIMEOUT", job_id=job_id) from None
        except Exception as original:
            raise _mapped_error(original, job_id=job_id) from None
