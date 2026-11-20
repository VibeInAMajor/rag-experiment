"""HTTP transport policy and sanitized operational correlation."""

import json
import logging
import re
from time import monotonic
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apps.workbench.api.config import ApiSettings
from apps.workbench.api.contracts import ApiError, ErrorResponse, Meta

_logger = logging.getLogger("workbench.api")
_ORIGIN = b"origin"
_HOST = b"host"
_CONTENT_LENGTH = b"content-length"
_TRANSFER_ENCODING = b"transfer-encoding"


def request_meta(request: Request) -> Meta:
    """Read server-generated correlation metadata for a response."""
    return Meta(request_id=request.state.request_id, trace_id=request.state.trace_id)


def error_response(meta: Meta, *, status: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    """Serialize the common error contract without exception details."""
    payload = ErrorResponse(
        **meta.model_dump(), error=ApiError(code=code, message=message, retryable=retryable, http_status=status)
    )
    return JSONResponse(status_code=status, content=payload.model_dump(exclude_none=True))


def log_event(event: str, **metadata: str | int | float) -> None:
    """Emit operational metadata only, without request paths or payloads."""
    _logger.info(json.dumps({"event": event, **metadata}, separators=(",", ":")))


def _trusted_host(raw: str) -> bool:
    matched = re.fullmatch(r"(localhost|127\.0\.0\.1|\[::1\])(?::([0-9]{1,5}))?", raw, flags=re.IGNORECASE)
    if matched is None:
        return False
    port = matched.group(2)
    return port is None or 1 <= int(port) <= 65535


class RequestBoundary:
    def __init__(self, app: ASGIApp, *, settings: ApiSettings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply local transport policy and correlate every HTTP response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = monotonic()
        meta = Meta(request_id=uuid4().hex, trace_id=uuid4().hex)
        scope.setdefault("state", {}).update(request_id=meta.request_id, trace_id=meta.trace_id)
        headers = [(key.lower(), value.decode("latin-1")) for key, value in scope["headers"]]
        origins = [value for key, value in headers if key == _ORIGIN]
        origin = origins[0] if len(origins) == 1 else None
        allowed_origin = origin if origin in self.settings.allowed_origins else None
        response_started = False
        response_status = 500

        async def correlated_send(message: Message) -> None:
            nonlocal response_started, response_status
            if message["type"] == "http.response.start":
                response_started = True
                response_status = message["status"]
                outgoing = list(message.get("headers", []))
                outgoing.append((b"x-request-id", meta.request_id.encode("ascii")))
                if allowed_origin is not None:
                    outgoing.extend(
                        [
                            (b"access-control-allow-origin", allowed_origin.encode("ascii")),
                            (b"access-control-expose-headers", b"X-Request-ID"),
                            (b"vary", b"Origin"),
                        ]
                    )
                message["headers"] = outgoing
            await send(message)

        try:
            rejection = self._reject(scope, headers, origins, meta)
            if rejection is not None:
                await rejection(scope, receive, correlated_send)
            elif scope["method"] == "OPTIONS" and origin is not None:
                response = JSONResponse(content=meta.model_dump())
                response.headers["Access-Control-Allow-Methods"] = "GET"
                response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
                await response(scope, receive, correlated_send)
            else:
                await self.app(scope, receive, correlated_send)
        except Exception:
            if response_started:
                # Headers cannot be replaced after transport starts; avoid leaking
                # exception details to the server's default traceback logger.
                log_event("response_interrupted", code="INTERNAL_ERROR")
                return
            response = error_response(
                meta, status=500, code="INTERNAL_ERROR", message="The service could not complete the request."
            )
            await response(scope, receive, correlated_send)
        finally:
            log_event(
                "http_request",
                request_id=meta.request_id,
                trace_id=meta.trace_id,
                http_status=response_status,
                duration_ms=round((monotonic() - started) * 1000, 3),
            )

    def _reject(
        self, scope: Scope, headers: list[tuple[bytes, str]], origins: list[str], meta: Meta
    ) -> JSONResponse | None:
        hosts = [value for key, value in headers if key == _HOST]
        if len(hosts) != 1 or not _trusted_host(hosts[0]):
            return error_response(meta, status=403, code="FORBIDDEN", message="The request host is not permitted.")
        if origins and (len(origins) != 1 or origins[0] not in self.settings.allowed_origins):
            return error_response(meta, status=403, code="FORBIDDEN", message="The request origin is not permitted.")
        if scope.get("query_string"):
            return error_response(
                meta, status=400, code="INVALID_REQUEST", message="Query parameters are not supported."
            )
        if scope["method"] == "GET":
            lengths = [value for key, value in headers if key == _CONTENT_LENGTH]
            transfer_encoded = any(key == _TRANSFER_ENCODING for key, _value in headers)
            if (
                transfer_encoded
                or lengths
                and (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or lengths[0].strip("0"))
            ):
                return error_response(
                    meta, status=400, code="INVALID_REQUEST", message="Request bodies are not supported."
                )
        if scope["method"] == "OPTIONS" and origins:
            requested = dict(headers)
            method = requested.get(b"access-control-request-method", "")
            names = requested.get(b"access-control-request-headers", "")
            if method != "GET" or any(
                name.strip().lower() not in {"accept", "content-type"} for name in names.split(",") if name.strip()
            ):
                return error_response(
                    meta, status=403, code="FORBIDDEN", message="The preflight request is not permitted."
                )
        return None
