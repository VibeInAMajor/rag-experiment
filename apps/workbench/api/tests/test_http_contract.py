"""HTTP discovery remains truthful, bounded to loopback and independent of providers."""

import ast
import asyncio
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict
from starlette.types import Message, Scope

from apps.workbench.api import application as application_module
from apps.workbench.api.application import create_app
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.contracts import ExecutionProfile, ServiceState
from apps.workbench.api.services import ReadinessSnapshot
from apps.workbench.api.tests._persistence import _DatabaseProbe, _QualifiedLexical

_BASE_URL = "http://127.0.0.1:8011"
_LIVE = "/api/v1/health/live"
_READY = "/api/v1/health/ready"
_CAPABILITIES = "/api/v1/capabilities"


class _MutableReadiness:
    def __init__(self, *, ready: bool = False) -> None:
        self.calls = 0
        self.ready = ready
        self.failure: Exception | None = None

    async def snapshot(self) -> ReadinessSnapshot:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        profiles = (
            [ExecutionProfile(profile_revision="qualified-test-revision", workspace_ids=["workspace-a"], corpus_id="a")]
            if self.ready
            else []
        )
        return ReadinessSnapshot(profiles=profiles)


class _ValidationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    count: int


class _Response(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    def json(self) -> Any: ...


def _assert_metadata(response: _Response) -> dict[str, Any]:
    payload = response.json()
    assert payload["contract_revision"] == "rag-api-v1.0"
    assert payload["request_id"] == response.headers["x-request-id"]
    assert payload["request_id"]
    assert payload["trace_id"]
    return payload


def _assert_error(response: _Response, *, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    payload = _assert_metadata(response)
    assert payload["error"]["code"] == code
    assert payload["error"]["http_status"] == status
    assert isinstance(payload["error"]["retryable"], bool)
    assert payload["error"]["message"]
    assert "detail" not in payload
    return payload


def _assert_openapi_response(app: FastAPI, response: _Response, *, path: str, method: str = "get") -> None:
    specification = app.openapi()
    schema = specification["paths"][path][method]["responses"][str(response.status_code)]["content"][
        "application/json"
    ]["schema"]
    Draft202012Validator({**schema, "components": specification["components"]}).validate(response.json())


def _assert_error_schema(app: FastAPI, response: _Response) -> None:
    Draft202012Validator(
        {"$ref": "#/components/schemas/ErrorResponse", "components": app.openapi()["components"]}
    ).validate(response.json())


def test_default_discovery_does_not_claim_an_execution_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """An environment flag cannot enable unavailable retrieval or document features."""
    monkeypatch.setenv("WORKBENCH_API_READY", "true")
    app = create_app(settings=ApiSettings.from_env({}))
    with TestClient(app, base_url=_BASE_URL) as client:
        live = client.get(_LIVE)
        assert live.status_code == 200
        assert _assert_metadata(live)["status"] == "alive"
        ready = client.get(_READY)
        _assert_error(ready, status=503, code="NOT_READY")
        capabilities = client.get(_CAPABILITIES)
        assert capabilities.status_code == 200
        payload = _assert_metadata(capabilities)
        assert payload["service_state"] == "running"
        assert payload["deployment_mode"] == "single_workspace_dev"
        assert payload["profiles"] == []
        assert payload["features"] == {
            "documents": False,
            "search": False,
            "upload": False,
            "document_details": False,
            "jobs": False,
        }
        for path, response in [(_LIVE, live), (_READY, ready), (_CAPABILITIES, capabilities)]:
            _assert_openapi_response(app, response, path=path)
        _assert_error(
            client.post(
                "/api/v1/workspaces/development/search",
                json={
                    "query": "hello",
                    "top_k": 5,
                    "profile_id": "postgres-fts-baseline",
                    "expected_profile_revision": "postgres-fts-baseline-r1",
                },
            ),
            status=503,
            code="NOT_READY",
        )


def test_published_openapi_matches_the_application_contract() -> None:
    """The reviewed schema artifact must not drift from the actual typed routes."""
    published = json.loads((Path(__file__).resolve().parents[1] / "openapi.json").read_text(encoding="utf-8"))
    assert published == create_app(settings=ApiSettings()).openapi()


def test_upload_schema_describes_qualified_formats_and_runtime_pdf_gate() -> None:
    """Multipart documentation must reflect format bounds without promising unavailable OCR."""
    operation = create_app(settings=ApiSettings()).openapi()["paths"]["/api/v1/workspaces/{workspace_id}/documents"][
        "post"
    ]
    schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    description = schema["properties"]["file"]["description"]
    for term in ("TXT", "Markdown", "Python", "1 MiB", "PDF", "8 MiB", "32 pages", "pdf_ingestion.available"):
        assert term in description
    assert "No OCR or visual understanding" in description
    assert schema["required"] == ["file"]


@pytest.mark.asyncio
async def test_slow_readiness_is_cancelled_without_disabling_liveness(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung cooperative probe cannot keep discovery requests waiting indefinitely."""
    cancelled: list[bool] = []

    class SlowReadiness:
        async def snapshot(self) -> ReadinessSnapshot:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
            return ReadinessSnapshot()

    monkeypatch.setattr(application_module, "_READINESS_TIMEOUT_SECONDS", 0.01)
    app = create_app(
        settings=ApiSettings(), readiness=SlowReadiness(), persistence=_DatabaseProbe(), lexical=_QualifiedLexical()
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=_BASE_URL) as client,
    ):
        ready = await client.get(_READY)
        _assert_error(ready, status=503, code="NOT_READY")
        capabilities = await client.get(_CAPABILITIES)
        assert capabilities.status_code == 200
        assert capabilities.json()["profiles"] == []
        assert (await client.get(_LIVE)).status_code == 200
    assert cancelled == [True, True]


@pytest.mark.asyncio
async def test_late_dependency_success_cannot_publish_readiness_after_shutdown() -> None:
    """An in-flight probe is rechecked against lifecycle when its snapshot arrives."""
    started = asyncio.Event()
    release = asyncio.Event()

    class ControlledReadiness(_MutableReadiness):
        async def snapshot(self) -> ReadinessSnapshot:
            started.set()
            await release.wait()
            return await super().snapshot()

    app = create_app(
        settings=ApiSettings(),
        readiness=ControlledReadiness(ready=True),
        persistence=_DatabaseProbe(),
        lexical=_QualifiedLexical(),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=_BASE_URL) as client:
        async with app.router.lifespan_context(app):
            pending = asyncio.create_task(client.get(_READY))
            await asyncio.wait_for(started.wait(), timeout=1)
        assert app.state.lifecycle == ServiceState.STOPPED
        release.set()
        response = await pending
        _assert_error(response, status=503, code="NOT_READY")
        _assert_openapi_response(app, response, path=_READY)


@pytest.mark.asyncio
async def test_real_asgi_disconnect_waits_for_cleanup_without_response_or_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A verified transport disconnect records 499 while holding its slot through cleanup."""
    entered = asyncio.Event()
    two_entered = asyncio.Event()
    cancellation_entered = asyncio.Event()
    finish_cleanup = asyncio.Event()
    incoming: asyncio.Queue[Message] = asyncio.Queue()
    sent: list[Message] = []
    calls = 0

    class DisconnectedSearch(_QualifiedLexical):
        async def search(self, *_args: Any, **_kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            entered.set()
            if calls == 2:
                two_entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancellation_entered.set()
                await finish_cleanup.wait()

    body = json.dumps(
        {
            "query": "PostgreSQL",
            "top_k": 5,
            "profile_id": "postgres-fts-baseline",
            "expected_profile_revision": "postgres-fts-baseline-r1",
        }
    ).encode()
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/workspaces/development/search",
        "raw_path": b"/api/v1/workspaces/development/search",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"127.0.0.1:8011"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "server": ("127.0.0.1", 8011),
        "client": ("127.0.0.1", 10000),
    }
    await incoming.put({"type": "http.request", "body": body, "more_body": False})

    async def receive() -> Message:
        return await incoming.get()

    async def send(message: Message) -> None:
        sent.append(message)

    app = create_app(settings=ApiSettings(), persistence=_DatabaseProbe(), lexical=DisconnectedSearch())
    caplog.set_level(logging.INFO, logger="workbench.api")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=_BASE_URL) as client,
    ):
        raw_request = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(entered.wait(), timeout=2)
        second = asyncio.create_task(
            client.post(scope["path"], content=body, headers={"Content-Type": "application/json"})
        )
        try:
            await asyncio.wait_for(two_entered.wait(), timeout=2)
            await incoming.put({"type": "http.disconnect"})
            await asyncio.wait_for(cancellation_entered.wait(), timeout=2)
            assert not raw_request.done()
            busy = await client.post(scope["path"], content=body, headers={"Content-Type": "application/json"})
            _assert_error(busy, status=429, code="SEARCH_BUSY")
            finish_cleanup.set()
            await asyncio.wait_for(raw_request, timeout=2)
            assert not raw_request.cancelled()
            second.cancel()
            with pytest.raises(asyncio.CancelledError):
                await second
        finally:
            finish_cleanup.set()
            for task in (raw_request, second):
                if not task.done():
                    task.cancel()
            await asyncio.gather(raw_request, second, return_exceptions=True)
    assert sent == []
    events = [json.loads(record.getMessage()) for record in caplog.records if record.name == "workbench.api"]
    logged = next(
        event
        for event in events
        if event.get("event") == "http_request" and event.get("request_id") == scope["state"]["request_id"]
    )
    assert logged["http_status"] == 499
    assert all(record.exc_info is None for record in caplog.records if record.name == "workbench.api")


def test_readiness_tracks_the_injected_dependency_snapshot() -> None:
    """Readiness can change without restarting or pretending that configuration is health."""
    probe = _MutableReadiness()
    app = create_app(settings=ApiSettings(), readiness=probe, persistence=_DatabaseProbe(), lexical=_QualifiedLexical())
    with TestClient(app, base_url=_BASE_URL) as client:
        _assert_error(client.get(_READY), status=503, code="NOT_READY")
        probe.ready = True
        ready = client.get(_READY)
        assert ready.status_code == 200
        assert _assert_metadata(ready)["ready_profile_ids"] == ["postgres-fts-baseline"]
        _assert_openapi_response(app, ready, path=_READY)
        capabilities = client.get(_CAPABILITIES)
        assert capabilities.json()["profiles"][0]["profile_revision"] == "qualified-test-revision"
        _assert_openapi_response(app, capabilities, path=_CAPABILITIES)
        probe.ready = False
        _assert_error(client.get(_READY), status=503, code="NOT_READY")
        assert client.get(_CAPABILITIES).json()["profiles"] == []
        assert client.get(_LIVE).status_code == 200
    assert probe.calls >= 5


def test_qualified_executor_cannot_bypass_unconfigured_postgresql() -> None:
    """A ready execution probe cannot grant readiness without the required durable corpus."""
    probe = _MutableReadiness(ready=True)
    app = create_app(settings=ApiSettings(), readiness=probe, lexical=_QualifiedLexical())
    with TestClient(app, base_url=_BASE_URL) as client:
        assert client.get(_LIVE).status_code == 200
        response = client.get(_READY)
        _assert_error(response, status=503, code="NOT_READY")
        capabilities = client.get(_CAPABILITIES)
        payload = _assert_metadata(capabilities)
        assert payload["dependencies"]["database"]["status"] == "unconfigured"
        assert payload["profiles"] == []
        assert payload["features"] == {
            "search": False,
            "documents": False,
            "upload": False,
            "document_details": False,
            "jobs": False,
        }
        _assert_openapi_response(app, capabilities, path=_CAPABILITIES)


def test_lifecycle_never_probes_dependencies_outside_the_running_process() -> None:
    """Stopping the app invalidates readiness even if the dependency was previously ready."""
    probe = _MutableReadiness(ready=True)
    app = create_app(settings=ApiSettings(), readiness=probe, persistence=_DatabaseProbe(), lexical=_QualifiedLexical())
    assert app.state.lifecycle == ServiceState.STARTING
    client = TestClient(app, base_url=_BASE_URL)
    _assert_error(client.get(_READY), status=503, code="NOT_READY")
    assert probe.calls == 0
    with client:
        assert app.state.lifecycle == ServiceState.RUNNING
        assert client.get(_READY).status_code == 200
    assert app.state.lifecycle == ServiceState.STOPPED
    calls = probe.calls
    _assert_error(client.get(_READY), status=503, code="NOT_READY")
    assert probe.calls == calls


def test_dependency_failures_are_unready_without_credential_leaks(caplog: pytest.LogCaptureFixture) -> None:
    """Failure of the readiness seam neither kills liveness nor leaks raw diagnostics."""
    secret = "postgresql://owner:credential-sentinel@private-db/internal"
    probe = _MutableReadiness()
    probe.failure = RuntimeError(secret)
    caplog.set_level(logging.INFO)
    with TestClient(create_app(settings=ApiSettings(), readiness=probe), base_url=_BASE_URL) as client:
        ready = client.get(_READY)
        assert ready.status_code == 503
        _assert_metadata(ready)
        assert client.get(_LIVE).status_code == 200
        capabilities = client.get(_CAPABILITIES)
        assert capabilities.status_code == 200
        assert capabilities.json()["profiles"] == []
    server_logs = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("workbench.api"))
    assert secret not in ready.text + capabilities.text + server_logs


@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "http://localhost:51730"])
def test_disallowed_origin_is_denied_before_dependency_access(origin: str) -> None:
    """CORS denial blocks actual requests, not merely their browser response headers."""
    probe = _MutableReadiness(ready=True)
    with TestClient(create_app(settings=ApiSettings(), readiness=probe), base_url=_BASE_URL) as client:
        response = client.get(_READY, headers={"Origin": origin})
        assert response.status_code == 403
        _assert_metadata(response)
        assert "access-control-allow-origin" not in response.headers
        assert probe.calls == 0


def test_allowed_origin_and_preflight_use_exact_allowlist() -> None:
    """Local browser access has a matching origin without credential-enabled wildcard CORS."""
    with TestClient(create_app(settings=ApiSettings()), base_url=_BASE_URL) as client:
        origin = "http://localhost:5173"
        response = client.get(_LIVE, headers={"Origin": origin})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers.get("access-control-allow-credentials") != "true"
        preflight = client.options(_LIVE, headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        assert preflight.status_code in {200, 204}
        assert preflight.headers["access-control-allow-origin"] == origin
        denied = client.options(
            _LIVE, headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "GET"}
        )
        assert denied.status_code == 403
        _assert_metadata(denied)


@pytest.mark.parametrize("host", ["attacker.example", "localhost.attacker.example", "127.0.0.1.attacker.example"])
def test_host_rebinding_attempts_cannot_reach_readiness(host: str) -> None:
    """A hostile Host header cannot exploit the loopback development listener."""
    probe = _MutableReadiness(ready=True)
    with TestClient(create_app(settings=ApiSettings(), readiness=probe), base_url=_BASE_URL) as client:
        response = client.get(_READY, headers={"Host": host})
        assert response.status_code in {400, 403}
        _assert_metadata(response)
        assert probe.calls == 0


def test_ids_are_server_generated_and_consistent_across_success_and_errors() -> None:
    """Caller-selected correlation values never become trusted server IDs."""
    with TestClient(create_app(settings=ApiSettings()), base_url=_BASE_URL) as client:
        identifiers: list[str] = []
        for path in [_LIVE, _READY, _CAPABILITIES, "/missing"]:
            response = client.get(path, headers={"X-Request-ID": "untrusted-request", "X-Trace-ID": "untrusted-trace"})
            payload = _assert_metadata(response)
            assert payload["request_id"] != "untrusted-request"
            assert payload["trace_id"] != "untrusted-trace"
            identifiers.extend([payload["request_id"], payload["trace_id"]])
        assert len(set(identifiers)) == len(identifiers)


def test_errors_share_safe_envelopes_and_do_not_log_caller_secrets(caplog: pytest.LogCaptureFixture) -> None:
    """Routing, validation and unexpected errors all preserve the public error contract."""
    secret = "credential-secret-sentinel"
    app = create_app(settings=ApiSettings())

    @app.post("/_contract/validate")
    async def validate(body: _ValidationBody) -> dict[str, int]:
        return {"count": body.count}

    @app.get("/_contract/failure")
    async def fail() -> None:
        raise RuntimeError(secret)

    caplog.set_level(logging.INFO)
    with TestClient(app, base_url=_BASE_URL, raise_server_exceptions=False) as client:
        response = client.get("/not-present", headers={"Authorization": f"Bearer {secret}", "X-Api-Key": secret})
        _assert_error(response, status=404, code="ENDPOINT_NOT_FOUND")
        method = client.post(_LIVE, json={"password": secret})
        _assert_error(method, status=405, code="METHOD_NOT_ALLOWED")
        assert "GET" in method.headers.get("allow", "")
        invalid = client.post("/_contract/validate", json={"count": secret, "password": secret})
        _assert_error(invalid, status=400, code="INVALID_REQUEST")
        malformed = client.post(
            "/_contract/validate", content=f'{{"secret":"{secret}"', headers={"Content-Type": "application/json"}
        )
        assert malformed.status_code == 400
        _assert_metadata(malformed)
        query = client.get(_LIVE, params={"token": secret})
        _assert_error(query, status=400, code="INVALID_REQUEST")
        failure = client.get("/_contract/failure")
        _assert_error(failure, status=500, code="INTERNAL_ERROR")
    assert secret not in "".join(item.text for item in [response, method, invalid, malformed, query, failure])
    for error in [response, method, invalid, malformed, query, failure]:
        _assert_error_schema(app, error)
    server_logs = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("workbench.api"))
    assert secret not in server_logs
    operational_records = [record for record in caplog.records if record.name == "workbench.api"]
    assert operational_records
    for record in operational_records:
        assert record.exc_info is None
        metadata = json.loads(record.getMessage())
        assert set(metadata) <= {"event", "state", "request_id", "trace_id", "http_status", "duration_ms", "code"}


@pytest.mark.parametrize(
    "headers",
    [
        [("Origin", "http://localhost:5173"), ("Origin", "https://attacker.example")],
        [("Host", "127.0.0.1:8011"), ("Host", "attacker.example")],
    ],
)
def test_duplicate_security_headers_do_not_bypass_request_policy(headers: list[tuple[str, str]]) -> None:
    """Ambiguous proxy/header combinations are refused before dependency access."""
    probe = _MutableReadiness(ready=True)
    app = create_app(settings=ApiSettings(), readiness=probe)
    with TestClient(app, base_url=_BASE_URL) as client:
        response = client.get(_READY, headers=headers)
        _assert_error(response, status=403, code="FORBIDDEN")
        _assert_error_schema(app, response)
        assert probe.calls == 0


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Length", "1")],
        [("Content-Length", "invalid")],
        [("Content-Length", "0"), ("Content-Length", "0")],
        [("Transfer-Encoding", "chunked")],
    ],
)
def test_discovery_rejects_request_body_framing_before_dependency_access(headers: list[tuple[str, str]]) -> None:
    """Discovery routes do not accept bodies or ambiguous HTTP body framing."""
    probe = _MutableReadiness(ready=True)
    app = create_app(settings=ApiSettings(), readiness=probe)
    with TestClient(app, base_url=_BASE_URL) as client:
        response = client.request("GET", _READY, headers=headers)
        _assert_error(response, status=400, code="INVALID_REQUEST")
        _assert_openapi_response(app, response, path=_READY)
        assert probe.calls == 0


def test_framework_and_provider_imports_stay_inside_explicit_adapters() -> None:
    """Application policy cannot acquire provider SDKs through an accidental direct import."""
    forbidden = {
        "haystack",
        "openai",
        "ollama",
        "torch",
        "transformers",
        "sentence_transformers",
        "tokenizers",
        "psycopg",
        "pgvector",
        "httpx",
    }
    package = Path(__file__).resolve().parents[1]
    for source in package.glob("*.py"):
        if source.name in {
            "postgres.py",
            "postgres_ingestion.py",
            "postgres_indexes.py",
            "postgres_profiles.py",
            "db_migrations.py",
            "db_admin.py",
        }:
            continue
        restricted = (
            forbidden - {"haystack"}
            if source.name in {"lexical.py", "parsing_adapters.py", "chunking_adapters.py", "python_code.py"}
            else forbidden
        )
        if source.name == "model_token_counter.py":
            restricted = restricted - {"tokenizers"}
        if source.name == "embedding_adapters.py":
            restricted = restricted - {"httpx"}
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            assert not restricted.intersection(module.split(".")[0] for module in modules), source.name
