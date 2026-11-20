"""Compose the discovery-only Workbench API without enabling runtime providers."""

from asyncio import timeout
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from apps.workbench.api.boundary import RequestBoundary, error_response, log_event, request_meta
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.contracts import (
    CapabilitiesResponse,
    Dependencies,
    ErrorResponse,
    Features,
    LiveResponse,
    ReadyResponse,
    ServiceState,
)
from apps.workbench.api.database_dependency import create_database_dependency
from apps.workbench.api.persistence import PersistencePort
from apps.workbench.api.services import ReadinessProbe, ReadinessSnapshot, UnconfiguredReadiness

_READINESS_TIMEOUT_SECONDS = 1.0


def create_app(
    *,
    settings: ApiSettings | None = None,
    readiness: ReadinessProbe | None = None,
    persistence: PersistencePort | None = None,
) -> FastAPI:
    """Create the local API; injected readiness must certify actual executable profiles."""
    configuration = ApiSettings.from_env() if settings is None else settings
    probe = UnconfiguredReadiness() if readiness is None else readiness
    database = create_database_dependency(configuration.database_dsn, persistence=persistence)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        await database.start()
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

    app = FastAPI(
        title="Workbench API",
        version="rag-api-v1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        responses={status: {"model": ErrorResponse} for status in (400, 403, 404, 405, 500)},
    )
    app.state.lifecycle = ServiceState.STARTING
    app.add_middleware(RequestBoundary, settings=configuration)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exception: HTTPException) -> JSONResponse:
        definitions = {
            404: ("ENDPOINT_NOT_FOUND", "The endpoint does not exist."),
            405: ("METHOD_NOT_ALLOWED", "The HTTP method is not supported."),
            400: ("INVALID_REQUEST", "The request is invalid."),
        }
        code, message = definitions.get(
            exception.status_code, ("INVALID_REQUEST", "The request could not be accepted.")
        )
        response = error_response(request_meta(request), status=exception.status_code, code=code, message=message)
        if exception.status_code == 405 and exception.headers and "Allow" in exception.headers:
            response.headers["Allow"] = exception.headers["Allow"]
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exception: RequestValidationError) -> JSONResponse:
        return error_response(
            request_meta(request), status=400, code="INVALID_REQUEST", message="The request is invalid."
        )

    async def snapshot() -> ReadinessSnapshot:
        if app.state.lifecycle != ServiceState.RUNNING:
            return ReadinessSnapshot()
        try:
            async with timeout(_READINESS_TIMEOUT_SECONDS):
                current = await probe.snapshot()
        except Exception:
            log_event("readiness_unavailable", code="DEPENDENCY_UNAVAILABLE")
            return ReadinessSnapshot()
        return current if app.state.lifecycle == ServiceState.RUNNING else ReadinessSnapshot()

    @app.get("/api/v1/health/live", response_model=LiveResponse, responses={503: {"model": ErrorResponse}})
    async def live(request: Request) -> LiveResponse | JSONResponse:
        if app.state.lifecycle != ServiceState.RUNNING:
            return error_response(
                request_meta(request),
                status=503,
                code="SERVICE_UNAVAILABLE",
                message="The service is not running.",
                retryable=True,
            )
        return LiveResponse(**request_meta(request).model_dump(), backend_revision=configuration.backend_revision)

    @app.get("/api/v1/health/ready", response_model=ReadyResponse, responses={503: {"model": ErrorResponse}})
    async def ready(request: Request) -> ReadyResponse | JSONResponse:
        dependency = await database.snapshot(trace_id=request_meta(request).trace_id)
        current = await snapshot()
        if dependency.status != "ready" or not current.profiles:
            return error_response(
                request_meta(request),
                status=503,
                code="NOT_READY",
                message="No execution profile is ready.",
                retryable=True,
            )
        return ReadyResponse(
            **request_meta(request).model_dump(),
            backend_revision=configuration.backend_revision,
            ready_profile_ids=[profile.profile_id for profile in current.profiles],
        )

    @app.get("/api/v1/capabilities", response_model=CapabilitiesResponse)
    async def capabilities(request: Request) -> CapabilitiesResponse:
        current = await snapshot()
        dependency = await database.snapshot(trace_id=request_meta(request).trace_id)
        return CapabilitiesResponse(
            **request_meta(request).model_dump(),
            backend_revision=configuration.backend_revision,
            service_state=app.state.lifecycle,
            profiles=current.profiles if dependency.status == "ready" else [],
            features=Features(),
            dependencies=Dependencies(database=dependency),
        )

    return app
