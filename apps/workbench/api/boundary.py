"""HTTP transport policy and sanitized operational correlation."""

import json
import logging
import re
from asyncio import CancelledError
from time import monotonic
from urllib.parse import parse_qsl
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
_CONTENT_TYPE = b"content-type"


class _ClientDisconnected(CancelledError):
    """The application observed a closed transport while awaiting owned work."""


def request_meta(request: Request) -> Meta:
    """Read server-generated correlation metadata for a response."""
    return Meta(request_id=request.state.request_id, trace_id=request.state.trace_id)


def error_response(
    meta: Meta, *, status: int, code: str, message: str, retryable: bool = False, run_id: str | None = None
) -> JSONResponse:
    """Serialize the common error contract without exception details."""
    payload = ErrorResponse(
        **meta.model_dump(),
        error=ApiError(code=code, message=message, retryable=retryable, http_status=status, run_id=run_id),
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


def _search_path(scope: Scope) -> bool:
    return re.fullmatch(r"/api/v1/workspaces/[^/]+/search", scope["path"]) is not None


def _reveal_path(scope: Scope) -> bool:
    return (
        re.fullmatch(r"/api/v1/workspaces/[^/]+/sources/[^/]+/versions/[^/]+/local-file/reveal", scope["path"])
        is not None
    )


def _list_path(scope: Scope) -> bool:
    return (
        scope["path"] == "/api/v1/workspaces"
        or re.fullmatch(r"/api/v1/workspaces/[^/]+/documents", scope["path"]) is not None
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Repeated JSON member")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError("Invalid JSON numeric constant")


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
        transport_disconnected = False

        async def tracked_receive() -> Message:
            nonlocal transport_disconnected
            message = await receive()
            if message["type"] == "http.disconnect":
                transport_disconnected = True
            return message

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
                await rejection(scope, tracked_receive, correlated_send)
            elif scope["method"] == "OPTIONS" and origin is not None:
                response = JSONResponse(content=meta.model_dump())
                response.headers["Access-Control-Allow-Methods"] = (
                    "POST" if _search_path(scope) or _reveal_path(scope) else "GET"
                )
                response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
                await response(scope, tracked_receive, correlated_send)
            elif scope["method"] == "POST" and (_search_path(scope) or _reveal_path(scope)):
                await self._search_request(scope, tracked_receive, correlated_send, headers, meta)
            else:
                await self.app(scope, tracked_receive, correlated_send)
        except _ClientDisconnected:
            if not transport_disconnected:
                raise
            # A closed transport has no response recipient; normal disconnect is not an ASGI error.
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
            if transport_disconnected and not response_started:
                response_status = 499
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
        if scope["method"] == "POST" and _reveal_path(scope) and not origins:
            return error_response(
                meta, status=403, code="FORBIDDEN", message="An explicit local browser origin is required."
            )
        if scope.get("query_string") and not self._valid_pagination(scope):
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
            permitted_method = "POST" if _search_path(scope) or _reveal_path(scope) else "GET"
            if method != permitted_method or any(
                name.strip().lower() not in {"accept", "content-type"} for name in names.split(",") if name.strip()
            ):
                return error_response(
                    meta, status=403, code="FORBIDDEN", message="The preflight request is not permitted."
                )
        return None

    def _valid_pagination(self, scope: Scope) -> bool:
        if scope["method"] != "GET" or not _list_path(scope) or len(scope["query_string"]) > 2048:
            return False
        try:
            pairs = parse_qsl(
                scope["query_string"].decode("utf-8"), keep_blank_values=True, strict_parsing=True, max_num_fields=2
            )
        except (ValueError, UnicodeError):
            return False
        return len({key for key, _value in pairs}) == len(pairs) and all(
            key in {"limit", "cursor"} for key, _value in pairs
        )

    async def _search_request(
        self, scope: Scope, receive: Receive, send: Send, headers: list[tuple[bytes, str]], meta: Meta
    ) -> None:
        content_types = [value for key, value in headers if key == _CONTENT_TYPE]
        if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
            response = error_response(
                meta, status=415, code="UNSUPPORTED_MEDIA_TYPE", message="This operation requires JSON."
            )
            await response(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            incoming = message.get("body", b"")
            if len(body) + len(incoming) > (1024 if _reveal_path(scope) else 32768):
                response = error_response(
                    meta, status=413, code="PAYLOAD_TOO_LARGE", message="Request body exceeds the byte limit."
                )
                await response(scope, receive, send)
                return
            body.extend(incoming)
            if not message.get("more_body", False):
                break
        try:
            json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            response = error_response(meta, status=400, code="INVALID_JSON", message="The JSON request is invalid.")
            await response(scope, receive, send)
            return

        consumed = False

        async def bounded_receive() -> Message:
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, send)
