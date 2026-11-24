"""Compose the approved, read-only PostgreSQL lexical HTTP boundary."""

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from apps.workbench.api.boundary import RequestBoundary, _ClientDisconnected, error_response, request_meta
from apps.workbench.api.configuration_http import register_configuration_routes
from apps.workbench.api.database_dependency import DatabaseDependency, create_database_dependency
from apps.workbench.api.ingestion_http import IngestionRoutes, register_ingestion_routes
from apps.workbench.api.projection import project_search
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.contracts.schemas import (
    CapabilitiesResponse,
    Dependencies,
    DocumentItem,
    DocumentPage,
    ErrorResponse,
    Features,
    LiveResponse,
    LocalSourceFileResponse,
    PdfIngestionCapabilities,
    ReadyResponse,
    RevealSourceRequest,
    RevealSourceResponse,
    SearchRequest,
    SearchResponse,
    ServiceState,
    WorkspaceItem,
    WorkspacePage,
)
from apps.workbench.embedding.embedding import EmbeddingError, EmbeddingErrorCode
from apps.workbench.ingestion.ingestion import IngestionService
from apps.workbench.observability.events import log_event
from apps.workbench.parsing.parser_registry import FormatId, parser_descriptors
from apps.workbench.persistence.models import (
    DatabaseUnavailable,
    InvalidSearchParameters,
    LexicalSearchSnapshot,
    PersistenceError,
    PersistencePort,
    ProfileNotAvailable,
    SchemaIncompatible,
    WorkspaceContext,
    WorkspaceNotFound,
    resolve_development_workspace,
)
from apps.workbench.retrieval.dense import DenseSearchResult, DenseService
from apps.workbench.retrieval.profile_registry import ProfileRegistry
from apps.workbench.retrieval.profiles import resolve_profile, validate_search_policy
from apps.workbench.retrieval.services import LexicalServicePort, ReadinessProbe, ReadinessSnapshot, RetrievalService
from apps.workbench.sources.local_sources import (
    FileRevealFailed,
    LocalFileLauncher,
    LocalSources,
    SourceFileUnavailable,
    SourceNotFound,
    WindowsExplorer,
)

_READINESS_TIMEOUT_SECONDS = 1.0
_SEARCH_TIMEOUT_SECONDS = 10.0


class _InvalidCursor(ValueError):
    pass


class _ServiceStopping(PersistenceError):
    pass


def _ensure_running(app: FastAPI) -> None:
    if app.state.lifecycle != ServiceState.RUNNING:
        raise _ServiceStopping("The service is not running.")


class _Cursors:
    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)

    def encode(self, *, kind: str, context: WorkspaceContext, revision: str, after: str) -> str:
        payload = base64.urlsafe_b64encode(
            json.dumps([kind, context.workspace_id, revision, after], separators=(",", ":")).encode()
        ).rstrip(b"=")
        signature = base64.urlsafe_b64encode(hmac.digest(self._key, payload, "sha256")).rstrip(b"=")
        return (payload + b"." + signature).decode("ascii")

    def offset(self, token: str | None, *, kind: str, context: WorkspaceContext, revision: str, ids: list[str]) -> int:
        if token is None:
            return 0
        cursor_revision, after = self.after(token, kind=kind, context=context)
        if cursor_revision != revision or after not in ids:
            raise _InvalidCursor("Expired cursor")
        return ids.index(after) + 1

    def after(self, token: str, *, kind: str, context: WorkspaceContext) -> tuple[str, str]:
        """Verify a scoped keyset cursor; persistence checks its revision and position atomically."""
        if not 1 <= len(token) <= 512:
            raise _InvalidCursor("Invalid cursor")
        try:
            payload, signature = token.encode("ascii").split(b".")
            expected = base64.urlsafe_b64encode(hmac.digest(self._key, payload, "sha256")).rstrip(b"=")
            decoded = json.loads(base64.b64decode(payload + b"=" * (-len(payload) % 4), altchars=b"-_", validate=True))
        except (ValueError, UnicodeError, TypeError):
            raise _InvalidCursor("Invalid cursor") from None
        if (
            not hmac.compare_digest(expected, signature)
            or not isinstance(decoded, list)
            or len(decoded) != 4
            or decoded[:2] != [kind, context.workspace_id]
            or not all(isinstance(value, str) and value for value in decoded[2:])
        ):
            raise _InvalidCursor("Invalid cursor")
        return decoded[2], decoded[3]


def _context(request: Request, workspace_id: str = "development") -> WorkspaceContext:
    return resolve_development_workspace(workspace_id).model_copy(update={"trace_id": request_meta(request).trace_id})


async def _wait_for_disconnect(request: Request) -> None:
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return


async def _execute_search(
    request: Request, service: LexicalServicePort, *, context: WorkspaceContext, body: SearchRequest
) -> LexicalSearchSnapshot | DenseSearchResult:
    work = asyncio.create_task(
        service.search(
            context,
            query=body.query,
            top_k=body.top_k,
            profile_id=body.profile_id,
            expected_profile_revision=body.expected_profile_revision,
        )
    )
    disconnected = asyncio.create_task(_wait_for_disconnect(request))
    try:
        finished, _pending = await asyncio.wait({work, disconnected}, return_when=asyncio.FIRST_COMPLETED)
        if disconnected in finished:
            disconnected.result()
            raise _ClientDisconnected
        return await work
    finally:
        work.cancel()
        disconnected.cancel()
        # Keep the admission slot until the owned pipeline and SQL cancellation finish.
        await asyncio.gather(work, disconnected, return_exceptions=True)


def _failure(request: Request, error: Exception, *, run_id: str | None = None) -> JSONResponse:
    if isinstance(error, EmbeddingError):
        if error.code == EmbeddingErrorCode.TIMEOUT:
            status = 504
        elif error.code in {EmbeddingErrorCode.RATE_LIMITED, EmbeddingErrorCode.CAPACITY_BUSY}:
            status = 429
        elif error.code in {EmbeddingErrorCode.INVALID_REQUEST, EmbeddingErrorCode.REQUEST_TOO_LARGE}:
            status = 400
        else:
            status = 503
        code, message = error.code.value, "The qualified local embedding dependency could not complete the request."
    elif isinstance(error, WorkspaceNotFound):
        status, code, message = (404, "WORKSPACE_NOT_FOUND", "Workspace is not available.")
    elif isinstance(error, SourceNotFound):
        status, code, message = (404, "SOURCE_NOT_FOUND", "The source version is not available.")
    elif isinstance(error, SourceFileUnavailable):
        status, code, message = (409, "SOURCE_FILE_UNAVAILABLE", "The local original is not available.")
    elif isinstance(error, FileRevealFailed):
        status, code, message = (503, "FILE_REVEAL_FAILED", "Explorer could not select the original file.")
    elif isinstance(error, _InvalidCursor):
        status, code, message = (400, "INVALID_CURSOR", "Restart the list from its first page.")
    elif isinstance(error, InvalidSearchParameters):
        status, code, message = (400, "INVALID_REQUEST", "The request exceeds the selected profile policy.")
    elif isinstance(error, ProfileNotAvailable):
        status, code, message = (409, "PROFILE_NOT_AVAILABLE", "Refresh executable profiles before searching.")
    elif isinstance(error, DatabaseUnavailable):
        status, code, message = (503, "DEPENDENCY_UNAVAILABLE", "The data dependency is unavailable.")
    elif isinstance(error, _ServiceStopping):
        status, code, message = (503, "SERVICE_UNAVAILABLE", "The service is not running.")
    elif isinstance(error, (SchemaIncompatible, PersistenceError)):
        status, code, message = (503, "NOT_READY", "The persisted corpus is not ready.")
    else:
        status, code, message = (500, "INTERNAL_ERROR", "The service could not complete the request.")
    if run_id is not None:
        log_event(
            "search_failed", run_id=run_id, trace_id=request_meta(request).trace_id, code=code, http_status=status
        )
    return error_response(
        request_meta(request),
        status=status,
        code=code,
        message=message,
        retryable=status in {429, 503, 504},
        run_id=run_id,
    )


async def _http_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, HTTPException):
        return _failure(request, exception)
    definitions = {
        404: ("ENDPOINT_NOT_FOUND", "The endpoint does not exist."),
        405: ("METHOD_NOT_ALLOWED", "The HTTP method is not supported."),
    }
    code, message = definitions.get(exception.status_code, ("INVALID_REQUEST", "The request could not be accepted."))
    response = error_response(request_meta(request), status=exception.status_code, code=code, message=message)
    if exception.status_code == 405 and exception.headers and ("Allow" in exception.headers):
        response.headers["Allow"] = exception.headers["Allow"]
    return response


async def _validation_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, RequestValidationError):
        return _failure(request, exception)
    cursor_error = any(error["loc"][:2] == ("query", "cursor") for error in exception.errors())
    return error_response(
        request_meta(request),
        status=400,
        code="INVALID_CURSOR" if cursor_error else "INVALID_REQUEST",
        message="The request is invalid.",
    )


class _Routes:
    def __init__(
        self,
        *,
        app: FastAPI,
        configuration: ApiSettings,
        database: DatabaseDependency,
        service: LexicalServicePort | None,
        readiness: ReadinessProbe | None,
        local_sources: LocalSources,
        ingestion: IngestionService | None,
        registry: ProfileRegistry,
    ) -> None:
        self.app = app
        self.configuration = configuration
        self.database = database
        self.service = service
        self.readiness = readiness
        self.local_sources = local_sources
        self.ingestion = ingestion
        self.registry = registry
        self.cursors = _Cursors()
        self.active_searches = 0
        self.profile_searches: dict[tuple[str, str], int] = {}

    async def _local_file(
        self, request: Request, workspace_id: str, source_id: str, version_id: str
    ) -> LocalSourceFileResponse | JSONResponse:
        try:
            context = _context(request, workspace_id)
            _ensure_running(self.app)
            return await self.local_sources.describe(
                context, source_id=source_id, version_id=version_id, meta=request_meta(request)
            )
        except Exception as error:
            return _failure(request, error)

    async def _reveal_local_file(
        self, request: Request, workspace_id: str, source_id: str, version_id: str, _body: RevealSourceRequest
    ) -> RevealSourceResponse | JSONResponse:
        async def before_dispatch() -> None:
            _ensure_running(self.app)
            if await request.is_disconnected():
                raise _ClientDisconnected

        try:
            context = _context(request, workspace_id)
            _ensure_running(self.app)
            await self.local_sources.reveal(
                context, source_id=source_id, version_id=version_id, before_dispatch=before_dispatch
            )
            return RevealSourceResponse(**request_meta(request).model_dump())
        except Exception as error:
            return _failure(request, error)

    async def _snapshot(self, request: Request) -> ReadinessSnapshot:
        if self.app.state.lifecycle != ServiceState.RUNNING or self.service is None:
            return ReadinessSnapshot()
        try:
            async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
                current = await self.service.snapshot(_context(request))
                if self.readiness is not None and (not (await self.readiness.snapshot()).profiles):
                    return ReadinessSnapshot()
        except Exception:
            log_event("readiness_unavailable", code="DEPENDENCY_UNAVAILABLE")
            return ReadinessSnapshot()
        return current if self.app.state.lifecycle == ServiceState.RUNNING else ReadinessSnapshot()

    async def _live(self, request: Request) -> LiveResponse | JSONResponse:
        if self.app.state.lifecycle != ServiceState.RUNNING:
            return error_response(
                request_meta(request),
                status=503,
                code="SERVICE_UNAVAILABLE",
                message="The service is not running.",
                retryable=True,
            )
        return LiveResponse(**request_meta(request).model_dump(), backend_revision=self.configuration.backend_revision)

    async def _ready(self, request: Request) -> ReadyResponse | JSONResponse:
        current = await self._snapshot(request)
        dependency = await self.database.snapshot(trace_id=request_meta(request).trace_id)
        if self.app.state.lifecycle != ServiceState.RUNNING or dependency.status != "ready" or not current.profiles:
            return error_response(
                request_meta(request),
                status=503,
                code="NOT_READY",
                message="No execution profile is ready.",
                retryable=True,
            )
        return ReadyResponse(
            **request_meta(request).model_dump(),
            backend_revision=self.configuration.backend_revision,
            ready_profile_ids=[profile.profile_id for profile in current.profiles],
        )

    async def _capabilities(self, request: Request) -> CapabilitiesResponse:
        current = await self._snapshot(request)
        dependency = await self.database.snapshot(trace_id=request_meta(request).trace_id)
        available = (
            self.app.state.lifecycle == ServiceState.RUNNING and dependency.status == "ready" and bool(current.profiles)
        )
        ingestion_available = False
        details_available = False
        if self.app.state.lifecycle == ServiceState.RUNNING and self.database.persistence is not None:
            try:
                async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
                    context = _context(request)
                    details_available = bool(await self.database.persistence.ingestion_ready(context))
                    ingestion_available = (
                        details_available and self.ingestion is not None and await self.ingestion.ready(context)
                    )
            except Exception:
                pass
        pdf_available = ingestion_available and any(
            item.qualified and item.available and FormatId.PDF in item.accepted_format_ids
            for item in parser_descriptors()
        )
        return CapabilitiesResponse(
            **request_meta(request).model_dump(),
            backend_revision=self.configuration.backend_revision,
            service_state=self.app.state.lifecycle,
            profiles=current.profiles if available else [],
            features=Features(
                documents=available,
                search=available,
                upload=ingestion_available,
                document_details=details_available,
                jobs=details_available,
            ),
            dependencies=Dependencies(database=dependency),
            pdf_ingestion=PdfIngestionCapabilities(
                available=pdf_available,
                text_layer=pdf_available,
                page_provenance=pdf_available,
                table_rows=pdf_available,
            ),
        )

    def _unavailable(self, request: Request) -> JSONResponse:
        return error_response(
            request_meta(request),
            status=503,
            code="NOT_READY",
            message="No execution profile is ready.",
            retryable=True,
        )

    async def _workspaces(
        self,
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=512),
    ) -> WorkspacePage | JSONResponse:
        if self.service is None or self.app.state.lifecycle != ServiceState.RUNNING:
            return self._unavailable(request)
        try:
            context = _context(request)
            await self.service.documents(context)
            records = sorted(await self.service.workspaces(context), key=lambda item: item.workspace_id)
            _ensure_running(self.app)
            if any(item.workspace_id != context.workspace_id for item in records):
                return _failure(request, WorkspaceNotFound("Workspace is not available."))
            items = [WorkspaceItem(workspace_id=item.workspace_id, name=item.name, status="ready") for item in records]
            revision = hashlib.sha256(
                json.dumps([item.model_dump() for item in items], sort_keys=True).encode()
            ).hexdigest()
            ids = [item.workspace_id for item in items]
            offset = self.cursors.offset(cursor, kind="workspaces", context=context, revision=revision, ids=ids)
            page = items[offset : offset + limit]
            following = (
                self.cursors.encode(kind="workspaces", context=context, revision=revision, after=page[-1].workspace_id)
                if page and offset + limit < len(items)
                else None
            )
            return WorkspacePage(**request_meta(request).model_dump(), items=page, next_cursor=following)
        except Exception as error:
            return _failure(request, error)

    async def _documents(
        self,
        request: Request,
        workspace_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=512),
    ) -> DocumentPage | JSONResponse:
        try:
            context = _context(request, workspace_id)
            if self.service is None or self.app.state.lifecycle != ServiceState.RUNNING:
                return self._unavailable(request)
            corpus = await self.service.documents(context)
            _ensure_running(self.app)
            records = sorted(corpus.documents, key=lambda item: item.source_id)
            offset = self.cursors.offset(
                cursor,
                kind="documents",
                context=context,
                revision=corpus.corpus_revision,
                ids=[item.source_id for item in records],
            )
            page = [DocumentItem.model_validate(item.model_dump()) for item in records[offset : offset + limit]]
            following = (
                self.cursors.encode(
                    kind="documents", context=context, revision=corpus.corpus_revision, after=page[-1].source_id
                )
                if page and offset + limit < len(records)
                else None
            )
            payload = DocumentPage(
                **request_meta(request).model_dump(),
                workspace_id=context.workspace_id,
                corpus_revision=corpus.corpus_revision,
                items=page,
                next_cursor=following,
            ).model_dump()
            for item in payload["items"]:
                if item["error_code"] is None:
                    del item["error_code"]
            return JSONResponse(payload)
        except Exception as error:
            return _failure(request, error)

    async def _search(self, request: Request, workspace_id: str, body: SearchRequest) -> SearchResponse | JSONResponse:
        try:
            context = _context(request, workspace_id)
        except WorkspaceNotFound as error:
            return _failure(request, error)
        try:
            definition = resolve_profile(
                self.registry,
                profile_id=body.profile_id,
                profile_revision=body.expected_profile_revision,
                workspace_id=context.workspace_id,
            )
            validate_search_policy(definition, query=body.query, top_k=body.top_k)
        except PersistenceError as error:
            return _failure(request, error)
        if self.service is None or self.app.state.lifecycle != ServiceState.RUNNING:
            return self._unavailable(request)
        profile_key = (definition.profile_id, definition.profile_revision)
        if self.active_searches >= 2 or self.profile_searches.get(profile_key, 0) >= definition.max_concurrent:
            response = error_response(
                request_meta(request),
                status=429,
                code="SEARCH_BUSY",
                message="Search capacity is busy.",
                retryable=True,
            )
            response.headers["Retry-After"] = "1"
            return response
        self.active_searches += 1
        self.profile_searches[profile_key] = self.profile_searches.get(profile_key, 0) + 1
        started = monotonic()
        run_id = uuid4().hex
        try:
            async with asyncio.timeout(min(_SEARCH_TIMEOUT_SECONDS, definition.timeout_ms / 1000)):
                result = await _execute_search(request, self.service, context=context, body=body)
                _ensure_running(self.app)
                search_response = project_search(
                    result,
                    context=context,
                    top_k=body.top_k,
                    meta=request_meta(request),
                    run_id=run_id,
                    started=started,
                    expected_profile=definition,
                )
                log_event(
                    "search_completed",
                    run_id=run_id,
                    trace_id=context.trace_id or "",
                    workspace_id=context.workspace_id,
                    profile_id=definition.profile_id,
                    profile_revision=definition.profile_revision,
                    policy_hash=definition.policy_hash,
                    corpus_revision=result.corpus_revision,
                    **(
                        {"index_generation_id": result.index_generation_id}
                        if result.index_generation_id is not None
                        else {}
                    ),
                    result_count=len(search_response.results),
                    duration_ms=search_response.duration_ms,
                    corpus_load_ms=result.corpus_load_duration_ms,
                    retrieval_ms=result.retrieval_duration_ms,
                )
                return search_response
        except TimeoutError:
            log_event(
                "search_failed", run_id=run_id, trace_id=context.trace_id or "", code="SEARCH_TIMEOUT", http_status=504
            )
            return error_response(
                request_meta(request),
                status=504,
                code="SEARCH_TIMEOUT",
                message="The search deadline elapsed.",
                retryable=True,
                run_id=run_id,
            )
        except Exception as error:
            return _failure(request, error, run_id=run_id)
        finally:
            self.active_searches -= 1
            remaining = self.profile_searches[profile_key] - 1
            if remaining:
                self.profile_searches[profile_key] = remaining
            else:
                del self.profile_searches[profile_key]


class _Application(FastAPI):
    def openapi(self) -> dict[str, Any]:
        """Publish the actual normalized 400 validation contract instead of automatic 422 responses."""
        specification = super().openapi()
        for path in specification["paths"].values():
            for operation in path.values():
                if isinstance(operation, dict):
                    operation.get("responses", {}).pop("422", None)
        schemas = specification.get("components", {}).get("schemas", {})
        schemas.pop("HTTPValidationError", None)
        schemas.pop("ValidationError", None)
        return specification


def create_app(
    *,
    settings: ApiSettings | None = None,
    readiness: ReadinessProbe | None = None,
    persistence: PersistencePort | None = None,
    lexical: LexicalServicePort | None = None,
    local_file_launcher: LocalFileLauncher | None = None,
    registry: ProfileRegistry | None = None,
    dense: DenseService | None = None,
) -> FastAPI:
    """Bind the qualified lexical service to the existing persistent corpus."""
    configuration = ApiSettings.from_env() if settings is None else settings
    approved_registry = configuration.profile_registry if registry is None else registry
    database = create_database_dependency(
        configuration.database_dsn, persistence=persistence, snapshot_mode=configuration.corpus_snapshot_mode
    )
    service = lexical
    ingestion = (
        IngestionService(database.persistence, processing=configuration.document_processing)
        if database.persistence is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        await database.start()
        if database.persistence is not None:
            try:
                async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
                    context = resolve_development_workspace()
                    if await database.persistence.ingestion_ready(context):
                        await database.persistence.recover_ingestions(context)
            except PersistenceError:
                log_event("ingestion_recovery_unavailable", code="DEPENDENCY_UNAVAILABLE")
            except TimeoutError:
                log_event("ingestion_recovery_unavailable", code="DEPENDENCY_UNAVAILABLE")
        application.state.lifecycle = ServiceState.RUNNING
        log_event("service_state", state=ServiceState.RUNNING.value)
        try:
            yield
        finally:
            application.state.lifecycle = ServiceState.STOPPING
            log_event("service_state", state=ServiceState.STOPPING.value)
            await database.close()
            application.state.lifecycle = ServiceState.STOPPED
            log_event("service_state", state=ServiceState.STOPPED.value)

    if service is None and database.persistence is not None:
        from apps.workbench.retrieval.lexical import LexicalService

        service = LexicalService(database.persistence, registry=approved_registry)
    if service is not None and dense is not None:
        service = RetrievalService(service, dense=dense, registry=approved_registry)
    app = _Application(
        title="Workbench API",
        version="rag-api-v1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        responses={status: {"model": ErrorResponse} for status in (400, 403, 404, 405, 500, 503)},
    )
    app.state.lifecycle = ServiceState.STARTING
    app.add_middleware(RequestBoundary, settings=configuration)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    local_sources = LocalSources(
        persistence=database.persistence,
        root=configuration.local_source_root,
        launcher=WindowsExplorer() if local_file_launcher is None else local_file_launcher,
    )
    routes = _Routes(
        app=app,
        configuration=configuration,
        database=database,
        service=service,
        readiness=readiness,
        local_sources=local_sources,
        ingestion=ingestion,
        registry=approved_registry,
    )
    app.add_api_route("/api/v1/health/live", routes._live, response_model=LiveResponse, name="live")
    app.add_api_route("/api/v1/health/ready", routes._ready, response_model=ReadyResponse, name="ready")
    app.add_api_route(
        "/api/v1/capabilities",
        routes._capabilities,
        response_model=CapabilitiesResponse,
        response_model_exclude_none=True,
        name="capabilities",
    )
    app.add_api_route("/api/v1/workspaces", routes._workspaces, response_model=WorkspacePage, name="workspaces")
    app.add_api_route(
        "/api/v1/workspaces/{workspace_id}/documents", routes._documents, response_model=DocumentPage, name="documents"
    )
    app.add_api_route(
        "/api/v1/workspaces/{workspace_id}/search",
        routes._search,
        methods=["POST"],
        response_model=SearchResponse,
        response_model_exclude_none=True,
        name="search",
        responses={status: {"model": ErrorResponse} for status in (409, 413, 415, 429, 504)},
    )
    app.add_api_route(
        "/api/v1/workspaces/{workspace_id}/sources/{source_id}/versions/{version_id}/local-file",
        routes._local_file,
        response_model=LocalSourceFileResponse,
        name="local_file",
    )
    app.add_api_route(
        "/api/v1/workspaces/{workspace_id}/sources/{source_id}/versions/{version_id}/local-file/reveal",
        routes._reveal_local_file,
        methods=["POST"],
        response_model=RevealSourceResponse,
        name="reveal_local_file",
        responses={status: {"model": ErrorResponse} for status in (409, 413, 415)},
    )
    register_ingestion_routes(
        app,
        IngestionRoutes(
            repository=database.persistence,
            service=ingestion,
            cursors=routes.cursors,
            context=_context,
            failure=_failure,
            ensure_running=lambda: _ensure_running(app),
            timeout_seconds=configuration.ingestion_timeout_seconds,
            pdf_timeout_seconds=configuration.pdf_ingestion_timeout_seconds,
        ),
    )
    register_configuration_routes(app, settings=configuration)
    return app
