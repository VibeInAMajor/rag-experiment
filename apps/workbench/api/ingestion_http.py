"""Additive upload and durable document inspection routes; ranking remains in the existing service."""

import asyncio
import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Protocol

from fastapi import FastAPI, Query, Request
from starlette.responses import JSONResponse

from apps.workbench.api.boundary import _ClientDisconnected, error_response, request_meta
from apps.workbench.api.contracts import (
    ActiveChunkItem,
    ActiveChunkPageResponse,
    DocumentDetail,
    ErrorResponse,
    IngestionJobResponse,
    IngestionResponse,
    IngestionStageTiming,
)
from apps.workbench.api.ingestion import IngestionError, IngestionResult, IngestionService, UploadInput
from apps.workbench.api.persistence import (
    DocumentNotFound,
    IngestionJob,
    PersistencePort,
    RecordConflict,
    SchemaIncompatible,
    WorkspaceContext,
)
from apps.workbench.api.upload_transport import UploadTransportError, read_upload

_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")
_CHUNK_METADATA = frozenset(
    {
        "ordinal",
        "source_span",
        "heading_path",
        "parent_structural_id",
        "processing_fingerprint",
        "source_sha256",
        "parser_id",
        "parser_revision",
        "detector_revision",
        "parser_contract_revision",
        "strategy",
        "profile_id",
        "profile_revision",
        "unit",
        "target_size",
        "requested_overlap",
        "actual_overlap_tokens",
        "length_tiktoken",
        "tokenizer_ref",
        "token_counter_revision",
        "separator_profile_id",
        "separators",
        "sentence_language",
        "sentence_keep_white_spaces",
        "sentence_resource_revision",
        "length_model_token",
        "model_counter_revision",
        "model_minus_tiktoken",
        "length_tiktoken_model_input",
        "model_minus_tiktoken_model_input",
        "selection_reason",
        "fallback_reasons",
        "warnings",
        "source_id",
        "parent_id",
        "split_id",
        "split_idx_start",
        "header",
        "parent_headers",
        "language_policy",
        "default_language",
        "ingestion_processing_fingerprint",
        "ingestion_policy_revision",
        "verified_document_type",
        "start_line",
        "end_line",
        "unit_kinds",
        "symbols",
        "qualified_symbol",
        "class_name",
        "decorators",
        "secondary_split",
        "secondary_split_index",
        "secondary_split_total",
        "actual_overlap_lines",
        "length_effective_line",
        "source_file",
    }
)


class CursorCodec(Protocol):
    def encode(self, *, kind: str, context: WorkspaceContext, revision: str, after: str) -> str:
        """Sign an actual keyset position for this scope and corpus."""
        ...

    def after(self, token: str, *, kind: str, context: WorkspaceContext) -> tuple[str, str]:
        """Verify a cursor and return its corpus revision and position."""
        ...


def _document_id(source_id: str) -> None:
    if _IDENTIFIER.fullmatch(source_id) is None:
        raise DocumentNotFound()


def _text_metadata(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _count_metadata(metadata: Mapping[str, object], key: str) -> int | None:
    value = metadata.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


async def _upload_result(work: asyncio.Task[IngestionResult], disconnected: asyncio.Task[None]) -> IngestionResult:
    finished, _pending = await asyncio.wait({work, disconnected}, return_when=asyncio.FIRST_COMPLETED)
    if disconnected in finished:
        disconnected.result()
        raise _ClientDisconnected
    return await work


class IngestionRoutes:
    def __init__(
        self,
        *,
        repository: PersistencePort | None,
        service: IngestionService | None,
        cursors: CursorCodec,
        context: Callable[[Request, str], WorkspaceContext],
        failure: Callable[[Request, Exception], JSONResponse],
        ensure_running: Callable[[], None],
        timeout_seconds: float,
    ) -> None:
        self.repository = repository
        self.service = service
        self.cursors = cursors
        self.context = context
        self.failure = failure
        self.ensure_running = ensure_running
        self.timeout_seconds = timeout_seconds

    async def _repository(self, context: WorkspaceContext) -> PersistencePort:
        self.ensure_running()
        if self.repository is None or not await self.repository.ingestion_ready(context):
            raise SchemaIncompatible()
        return self.repository

    def _error(self, request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, (UploadTransportError, IngestionError)):
            return error_response(
                request_meta(request),
                status=error.status,
                code=error.code,
                message="The upload or document operation could not be completed.",
                retryable=error.retryable if isinstance(error, IngestionError) else False,
                job_id=error.job_id if isinstance(error, IngestionError) else None,
            )
        if isinstance(error, DocumentNotFound):
            return error_response(
                request_meta(request), status=404, code="DOCUMENT_NOT_FOUND", message="Document is not available."
            )
        return self.failure(request, error)

    async def upload(self, request: Request, workspace_id: str) -> IngestionResponse | JSONResponse:
        """Ingest bounded UTF-8 TXT, Markdown or Python; return success only after atomic source/job publication."""
        work: asyncio.Task[IngestionResult] | None = None
        disconnected: asyncio.Task[None] | None = None
        try:
            context = self.context(request, workspace_id)
            self.ensure_running()
            if self.service is None:
                return self._error(request, SchemaIncompatible())
            parts = await read_upload(request)
            await self._repository(context)
            remaining = min(self.timeout_seconds, request.state.ingestion_deadline - asyncio.get_running_loop().time())
            if remaining <= 0:
                return self._error(request, IngestionError("INGESTION_TIMEOUT"))

            def observe_job(job: IngestionJob) -> None:
                request.state.ingestion_job_id = job.job_id

            work = asyncio.create_task(
                self.service.ingest(
                    context, upload=UploadInput(**asdict(parts)), timeout_seconds=remaining, on_job=observe_job
                )
            )

            async def wait_disconnect() -> None:
                while (await request.receive())["type"] != "http.disconnect":
                    pass

            disconnected = asyncio.create_task(wait_disconnect())
            result = await _upload_result(work, disconnected)
            self.ensure_running()
            job = result.job
            if (
                job.effective_version_id is None
                or job.outcome is None
                or job.corpus_revision is None
                or job.chunk_count is None
            ):
                return self._error(request, IngestionError("INGESTION_FAILED"))
            payload = IngestionResponse(
                **request_meta(request).model_dump(),
                workspace_id=context.workspace_id,
                source_id=job.source_id,
                source_version_id=job.effective_version_id,
                job_id=job.job_id,
                outcome=job.outcome,
                chunk_count=job.chunk_count,
                corpus_revision=job.corpus_revision,
                stages=[IngestionStageTiming.model_validate(stage.model_dump()) for stage in job.stages],
                replayed=result.replayed,
            )
            return JSONResponse(
                status_code=201 if job.outcome == "created" and not result.replayed else 200,
                content=payload.model_dump(),
            )
        except Exception as error:
            return self._error(request, error)
        finally:
            tasks = [task for task in (work, disconnected) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def detail(self, request: Request, workspace_id: str, source_id: str) -> DocumentDetail | JSONResponse:
        """Expose active processing metadata without paths or a fabricated original download."""
        try:
            context = self.context(request, workspace_id)
            repository = await self._repository(context)
            _document_id(source_id)
            detail = await repository.get_source_detail(context, source_id=source_id)
            if detail is None:
                return self._error(request, DocumentNotFound())
            self.ensure_running()
            metadata = detail.version.metadata if detail.version else {}
            profile = metadata.get("processing_profile")
            parser = {
                key: metadata[key] for key in ("parser_id", "parser_revision", "detector_revision") if key in metadata
            }
            warnings = metadata.get("warnings", [])
            language_policy = metadata.get("language_policy")
            default_language = metadata.get("default_language")
            processing = metadata.get("document_processing")
            return DocumentDetail(
                **request_meta(request).model_dump(),
                workspace_id=context.workspace_id,
                corpus_revision=detail.corpus_revision,
                source_id=detail.source.source_id,
                title=detail.source.title,
                media_type=detail.source.media_type,
                status="ready" if detail.version else "processing",
                active_version_id=detail.version.version_id if detail.version else None,
                chunk_count=detail.chunk_count,
                updated_at=detail.updated_at,
                processing_profile=profile if isinstance(profile, dict) else None,
                processing_profile_fingerprint=_text_metadata(metadata, "processing_profile_fingerprint"),
                ingestion_policy_revision=_text_metadata(metadata, "ingestion_policy_revision"),
                language_policy="configured_sentence_language"
                if language_policy == "configured_sentence_language"
                else "configured_structural_boundaries"
                if language_policy == "configured_structural_boundaries"
                else "unqualified_source_locale"
                if language_policy == "unqualified_source_locale"
                else None,
                default_language="en" if default_language == "en" else "ru" if default_language == "ru" else None,
                document_processing=processing if isinstance(processing, dict) else None,
                source_content_sha256=_text_metadata(metadata, "source_sha256"),
                source_bytes=_count_metadata(metadata, "source_bytes"),
                parsed_element_count=_count_metadata(metadata, "parsed_element_count"),
                parser=parser or None,
                warnings=[item for item in warnings if isinstance(item, str)] if isinstance(warnings, list) else [],
            )
        except Exception as error:
            return self._error(request, error)

    async def chunks(
        self,
        request: Request,
        workspace_id: str,
        source_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=512),
    ) -> ActiveChunkPageResponse | JSONResponse:
        """Read one active-version keyset page, rejecting stale or foreign cursors."""
        try:
            context = self.context(request, workspace_id)
            repository = await self._repository(context)
            _document_id(source_id)
            kind = "chunks-" + hashlib.sha256(source_id.encode()).hexdigest()
            revision, after = self.cursors.after(cursor, kind=kind, context=context) if cursor else (None, None)
            try:
                page = await repository.list_active_chunks(
                    context, source_id=source_id, limit=limit, after_chunk_id=after, expected_corpus_revision=revision
                )
            except RecordConflict:
                return error_response(
                    request_meta(request), status=400, code="INVALID_CURSOR", message="Restart from the first page."
                )
            if page is None:
                return self._error(request, DocumentNotFound())
            items = []
            for chunk in page.items:
                ordinal = chunk.metadata.get("ordinal", 0)
                headings = chunk.metadata.get("heading_path", [])
                items.append(
                    ActiveChunkItem(
                        chunk_id=chunk.chunk_id,
                        order=ordinal if isinstance(ordinal, int) and ordinal >= 0 else 0,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        page=chunk.page,
                        section_path=[item for item in headings if isinstance(item, str)]
                        if isinstance(headings, list)
                        else [],
                        metadata={key: value for key, value in chunk.metadata.items() if key in _CHUNK_METADATA},
                    )
                )
            following = (
                self.cursors.encode(kind=kind, context=context, revision=page.corpus_revision, after=page.next_after)
                if page.next_after
                else None
            )
            self.ensure_running()
            return ActiveChunkPageResponse(
                **request_meta(request).model_dump(),
                workspace_id=context.workspace_id,
                source_id=source_id,
                source_version_id=page.source_version_id,
                corpus_revision=page.corpus_revision,
                items=items,
                next_cursor=following,
            )
        except Exception as error:
            return self._error(request, error)

    async def job(self, request: Request, workspace_id: str, job_id: str) -> IngestionJobResponse | JSONResponse:
        """Read durable last-confirmed state without the idempotency key or owner token."""
        try:
            context = self.context(request, workspace_id)
            repository = await self._repository(context)
            record = (
                await repository.get_ingestion_job(context, job_id=job_id) if _IDENTIFIER.fullmatch(job_id) else None
            )
            if record is None:
                return error_response(
                    request_meta(request), status=404, code="JOB_NOT_FOUND", message="Job is not available."
                )
            self.ensure_running()
            return IngestionJobResponse(
                **request_meta(request).model_dump(),
                workspace_id=context.workspace_id,
                job_id=record.job_id,
                source_id=record.source_id,
                source_version_id=record.effective_version_id,
                reserved_version_id=record.reserved_version_id,
                status=record.status,
                stage=record.stage,
                retryable=record.retryable,
                error_code=record.error_code,
                chunk_count=record.chunk_count,
                outcome=record.outcome,
                created_at=record.created_at,
                updated_at=record.updated_at,
                finished_at=record.finished_at,
                stages=[IngestionStageTiming.model_validate(stage.model_dump()) for stage in record.stages],
            )
        except Exception as error:
            return self._error(request, error)


def register_ingestion_routes(app: FastAPI, routes: IngestionRoutes) -> None:
    """Publish actual typed v1 operations, including explicit bounded multipart schema."""
    documents = "/api/v1/workspaces/{workspace_id}/documents"
    app.add_api_route(
        documents,
        routes.upload,
        methods=["POST"],
        response_model=IngestionResponse,
        status_code=201,
        name="upload_document",
        responses={
            200: {"model": IngestionResponse},
            **{status: {"model": ErrorResponse} for status in (409, 413, 415, 429, 504)},
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["file"],
                            "properties": {
                                "file": {
                                    "type": "string",
                                    "format": "binary",
                                    "description": "One UTF-8 TXT or Markdown, at most 1 MiB.",
                                },
                                "source_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,128}$"},
                                "expected_active_version_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,128}$"},
                            },
                        }
                    }
                },
            },
            "parameters": [
                {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "schema": {"type": "string", "pattern": "^[A-Za-z0-9_-]{8,128}$"},
                }
            ],
        },
    )
    app.add_api_route(documents + "/{source_id}", routes.detail, response_model=DocumentDetail, name="document_detail")
    app.add_api_route(
        documents + "/{source_id}/chunks", routes.chunks, response_model=ActiveChunkPageResponse, name="document_chunks"
    )
    app.add_api_route(
        "/api/v1/workspaces/{workspace_id}/jobs/{job_id}",
        routes.job,
        response_model=IngestionJobResponse,
        name="ingestion_job",
    )
