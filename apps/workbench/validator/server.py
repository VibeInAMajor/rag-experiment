"""Small loopback HTTP boundary with bounded input and no execution endpoints."""

import json
import logging
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import ValidationError

from apps.workbench.validator.registry import CAPABILITY_VERSION, REGISTRY
from apps.workbench.validator.schemas import ValidationRequest
from apps.workbench.validator.validator import validate_graph

_LOGGER = logging.getLogger(__name__)
_MAX_BODY = 1000000
_ALLOWED_ORIGINS = {f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 4173, 8010)}


class ValidationServer(ThreadingHTTPServer):
    """Dedicated local tool: two simultaneous validations, sixty admissions/minute."""

    daemon_threads = True

    def __init__(self, port: int) -> None:
        self.validation_slots = threading.BoundedSemaphore(2)
        self.admissions: deque[float] = deque()
        self.admission_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), ValidationHandler)

    def admit(self) -> bool:
        """Bound admitted request rate across threads."""
        now = time.monotonic()
        with self.admission_lock:
            while self.admissions and self.admissions[0] < now - 60:
                self.admissions.popleft()
            if len(self.admissions) >= 60:
                return False
            self.admissions.append(now)
            return True


class ValidationHandler(BaseHTTPRequestHandler):
    """Translate HTTP input to a strict schema and sanitized diagnostics."""

    server: ValidationServer

    def setup(self) -> None:
        """Bound slow reads before admitting a validation."""
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, _format: str, *_args: object) -> None:
        """Suppress unstructured request logging; outcomes are logged separately."""
        return

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in _ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            _LOGGER.info(json.dumps({"event": "validation_disconnected"}))

    def _local_request(self) -> bool:
        try:
            host = urlsplit("http://" + self.headers.get("Host", "")).hostname
        except ValueError:
            host = None
        origin = self.headers.get("Origin")
        if host not in {"localhost", "127.0.0.1"} or origin is not None and origin not in _ALLOWED_ORIGINS:
            self._reply(403, {"error": "LOCAL_REQUEST_REQUIRED"})
            return False
        return True

    def do_OPTIONS(self) -> None:
        """Allow only reviewed local browser origins."""
        if self._local_request():
            self._reply(200, {})

    def do_GET(self) -> None:
        """Expose service health and the reviewed component mapping revision."""
        if not self._local_request():
            return
        if self.path == "/health":
            self._reply(200, {"status": "ok", "validator": "haystack", "capabilityVersion": CAPABILITY_VERSION})
        elif self.path == "/api/pipelines/capabilities":
            self._reply(
                200,
                {
                    "capabilityVersion": CAPABILITY_VERSION,
                    "nodes": {
                        kind: {
                            "supported": value.component is not None,
                            "component": value.component,
                            "inputs": value.inputs,
                            "outputs": value.outputs,
                            "reason": value.reason,
                        }
                        for kind, value in REGISTRY.items()
                    },
                },
            )
        else:
            self._reply(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        """Validate one bounded graph without accepting executable objects."""
        if not self._local_request():
            return
        if self.path != "/api/pipelines/validate":
            self._reply(404, {"error": "NOT_FOUND"})
            return
        if self.headers.get("Transfer-Encoding"):
            self._reply(400, {"error": "INVALID_CONTENT_LENGTH"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > _MAX_BODY:
            self._reply(413, {"error": "PAYLOAD_TOO_LARGE"})
            return
        if length <= 0 or self.headers.get_content_type() != "application/json":
            self._reply(400, {"error": "INVALID_GRAPH"})
            return
        if not self.server.admit() or not self.server.validation_slots.acquire(blocking=False):
            self._reply(429, {"error": "VALIDATION_BUSY"})
            return
        started = time.monotonic()
        request_id = str(uuid4())
        try:
            payload = self.rfile.read(length)
            request = ValidationRequest.model_validate_json(payload)
            request_id = request.requestId or request_id
            response = validate_graph(request)
            self._reply(200, response)
            _LOGGER.info(
                json.dumps(
                    {
                        "event": "pipeline_validated",
                        "requestId": response["requestId"],
                        "status": response["status"],
                        "durationMs": round((time.monotonic() - started) * 1000),
                        "issueCodes": [issue["code"] for issue in response["issues"]],
                        "supportedNodes": sum(
                            1
                            for node in request.graph.nodes
                            if node.data.kind in REGISTRY and REGISTRY[node.data.kind].component is not None
                        ),
                        "unsupportedNodes": sum(
                            1
                            for node in request.graph.nodes
                            if node.data.kind not in REGISTRY or REGISTRY[node.data.kind].component is None
                        ),
                    }
                )
            )
        except (ValidationError, ValueError, RecursionError):
            _LOGGER.info(
                json.dumps({"event": "validation_rejected", "requestId": request_id, "issueCodes": ["INVALID_GRAPH"]})
            )
            self._reply(400, {"error": "INVALID_GRAPH", "requestId": request_id})
        except (TimeoutError, OSError):
            self._reply(408, {"error": "VALIDATION_TIMEOUT", "requestId": request_id})
        except Exception:
            _LOGGER.log(logging.ERROR, json.dumps({"event": "validation_failed", "requestId": request_id}))
            self._reply(500, {"error": "VALIDATION_ERROR", "requestId": request_id})
        finally:
            self.server.validation_slots.release()


def create_server(port: int = 8010) -> ValidationServer:
    """Create a loopback-only server; port zero is available for isolated tests."""
    return ValidationServer(port=port)
