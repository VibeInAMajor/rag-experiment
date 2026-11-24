"""Direct local-application YAML editing through the existing trusted-origin boundary."""

import asyncio
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from apps.workbench.api.boundary import error_response, request_meta
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.configuration.configuration import ConfigurationDocument, ConfigurationFailure, ConfigurationStore
from apps.workbench.configuration.document_processing import DocumentProcessingConfigurationError
from apps.workbench.contracts.schemas import (
    ConfigurationDocumentResponse,
    ConfigurationIssueResponse,
    ConfigurationSaveRequest,
    ConfigurationSaveResponse,
    ConfigurationValidationResponse,
    ConfigurationYamlRequest,
    ErrorResponse,
)
from apps.workbench.observability.events import log_event

_P = ParamSpec("_P")
_T = TypeVar("_T")


class ConfigurationRoutes:
    """Local Workbench requests need no login; non-simple headers and trusted Origin guard browser writes."""

    def __init__(self, settings: ApiSettings) -> None:
        self._settings = settings
        self._store = ConfigurationStore(settings)
        self._workers = asyncio.Semaphore(2)

    def _error(self, request: Request, code: str, status: int) -> JSONResponse:
        log_event(
            "configuration_operation",
            operation=request.method,
            actor="local_application",
            outcome=code,
            recorded_at_utc=datetime.now(UTC).isoformat(),
            trace_id=request_meta(request).trace_id,
        )
        messages = {
            403: "Use the local Workbench application for configuration.",
            409: "Configuration changed. Reload before saving.",
            413: "Configuration exceeds the 64 KiB limit.",
            400: "Configuration is invalid; validate it before saving.",
        }
        return error_response(
            request_meta(request),
            status=status,
            code=code,
            message=messages.get(status, "Configuration is unavailable. Retry after checking the service."),
            retryable=status in {429, 503, 504},
        )

    def _authorize(self, request: Request) -> JSONResponse | None:
        # This is a browser request-intent/CSRF guard, not an account or operator role.
        if request.headers.get("x-workbench-request") != "configuration":
            return self._error(request, "FORBIDDEN", 403)
        return None

    async def _work(self, operation: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> _T:
        async with self._workers:
            work = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
            try:
                return await asyncio.shield(work)
            except asyncio.CancelledError:
                await work
                raise

    def _document(
        self, request: Request, document: ConfigurationDocument, *, saved: bool = False
    ) -> ConfigurationDocumentResponse:
        model = ConfigurationSaveResponse if saved else ConfigurationDocumentResponse
        return model(
            **request_meta(request).model_dump(),
            **asdict(document),
            effective_default_language=self._settings.document_processing.default_language,
            deployment_overrides=["default_language"] if self._settings.configuration_language_override else [],
        )

    async def read(self, request: Request) -> ConfigurationDocumentResponse | JSONResponse:
        """Load the authoritative YAML directly for the local application, without keys or sessions."""
        rejected = self._authorize(request)
        if rejected is not None:
            return rejected
        try:
            document = await self._work(self._store.read)
            log_event(
                "configuration_read",
                actor="local_application",
                revision=document.revision,
                recorded_at_utc=datetime.now(UTC).isoformat(),
                trace_id=request_meta(request).trace_id,
            )
            return self._document(request, document)
        except ConfigurationFailure as error:
            return self._error(request, error.code, error.status)

    async def validate(
        self, request: Request, body: ConfigurationYamlRequest
    ) -> ConfigurationValidationResponse | JSONResponse:
        """Return canonical diagnostics without modifying saved configuration."""
        rejected = self._authorize(request)
        if rejected is not None:
            return rejected
        try:
            if len(body.yaml.encode("utf-8")) > 65536:
                return self._error(request, "CONFIGURATION_TOO_LARGE", 413)
            await self._work(self._store.validate, text=body.yaml)
            log_event(
                "configuration_validated",
                actor="local_application",
                outcome="valid",
                recorded_at_utc=datetime.now(UTC).isoformat(),
                trace_id=request_meta(request).trace_id,
            )
            return ConfigurationValidationResponse(**request_meta(request).model_dump(), valid=True)
        except DocumentProcessingConfigurationError as error:
            return ConfigurationValidationResponse(
                **request_meta(request).model_dump(),
                valid=False,
                errors=[ConfigurationIssueResponse(**asdict(issue)) for issue in error.issues],
            )
        except ConfigurationFailure as error:
            return self._error(request, error.code, error.status)
        except UnicodeError:
            return self._error(request, "INVALID_CONFIGURATION", 400)

    async def save(
        self, request: Request, body: ConfigurationSaveRequest
    ) -> ConfigurationDocumentResponse | JSONResponse:
        """Revalidate and atomically save against the loaded revision; activation remains explicit."""
        rejected = self._authorize(request)
        if rejected is not None:
            return rejected
        try:
            if len(body.yaml.encode("utf-8")) > 65536:
                return self._error(request, "CONFIGURATION_TOO_LARGE", 413)
            document = await self._work(self._store.save, text=body.yaml, expected_revision=body.expected_revision)
            log_event(
                "configuration_saved",
                actor="local_application",
                scope="application",
                revision=document.revision,
                activation=document.activation,
                recorded_at_utc=datetime.now(UTC).isoformat(),
                trace_id=request_meta(request).trace_id,
            )
            return self._document(request, document, saved=True)
        except DocumentProcessingConfigurationError:
            return self._error(request, "INVALID_CONFIGURATION", 400)
        except ConfigurationFailure as error:
            return self._error(request, error.code, error.status)
        except UnicodeError:
            return self._error(request, "INVALID_CONFIGURATION", 400)


def register_configuration_routes(app: FastAPI, *, settings: ApiSettings) -> None:
    """Add direct local configuration operations to the existing API."""
    routes = ConfigurationRoutes(settings)
    root = "/api/v1/configuration"
    errors: dict[int | str, dict[str, Any]] = {status: {"model": ErrorResponse} for status in (400, 403, 409, 413, 503)}
    app.add_api_route(
        root, routes.read, response_model=ConfigurationDocumentResponse, responses=errors, name="configuration_read"
    )
    app.add_api_route(
        root + "/validate",
        routes.validate,
        methods=["POST"],
        response_model=ConfigurationValidationResponse,
        responses=errors,
        name="configuration_validate",
    )
    app.add_api_route(
        root,
        routes.save,
        methods=["PUT"],
        response_model=ConfigurationSaveResponse,
        responses=errors,
        name="configuration_save",
    )
