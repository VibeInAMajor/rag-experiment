"""Local-original hints and native reveal fail closed without exposing paths."""

import asyncio
import ctypes
import hashlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.types import Message, Scope

from apps.workbench.api import local_sources as local_module
from apps.workbench.api.application import create_app
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.local_sources import (
    FileRevealFailed,
    LocalSources,
    SourceFileUnavailable,
    WindowsExplorer,
    inspect_local_original,
)
from apps.workbench.api.persistence import LocalOriginalRecord, WorkspaceContext
from apps.workbench.api.tests._persistence import _DatabaseProbe

_FILE = "/api/v1/workspaces/development/sources/source-real/versions/version-real/local-file"
_ORIGIN = {"Origin": "http://127.0.0.1:4173"}


class _Launcher:
    def __init__(self) -> None:
        self.paths: list[Path] = []
        self.enabled = True
        self.failure = False

    def available(self) -> bool:
        return self.enabled

    def reveal(self, path: Path) -> None:
        if self.failure:
            raise OSError("private filesystem detail")
        self.paths.append(path)


class _Originals(_DatabaseProbe):
    def __init__(self, record: LocalOriginalRecord | None) -> None:
        super().__init__()
        self.record = record
        self.calls = 0

    async def get_local_original(
        self, context: WorkspaceContext, *, source_id: str, version_id: str
    ) -> LocalOriginalRecord | None:
        assert context.workspace_id == "development"
        self.calls += 1
        if self.failure:
            raise self.failure
        if self.record and self.record.source_id == source_id and self.record.version_id == version_id:
            return self.record
        return None


def _record(root: Path, path: Path, *, demo: bool = False) -> LocalOriginalRecord:
    return LocalOriginalRecord(
        source_id="source-real",
        version_id="version-real",
        is_demo=demo,
        registration=inspect_local_original(root, path),
    )


def _client(root: Path, record: LocalOriginalRecord | None, launcher: _Launcher) -> TestClient:
    return TestClient(
        create_app(
            settings=ApiSettings(local_source_root=str(root)),
            persistence=_Originals(record),
            local_file_launcher=launcher,
        ),
        base_url="http://127.0.0.1:8011",
    )


def test_local_original_inspection_records_relative_location_and_original_byte_hash(tmp_path: Path) -> None:
    """Registration records original bytes rather than an extracted-content digest."""
    original = tmp_path / "Finance & (draft).pdf"
    original.write_bytes(b"original PDF bytes")
    inspected = inspect_local_original(tmp_path, original)
    assert inspected.relative_path == original.name
    assert inspected.sha256 == hashlib.sha256(original.read_bytes()).hexdigest()
    with pytest.raises(SourceFileUnavailable):
        inspect_local_original(tmp_path, tmp_path)
    with pytest.raises(SourceFileUnavailable):
        inspect_local_original(tmp_path, tmp_path.parent / "outside.pdf")
    with pytest.raises(SourceFileUnavailable):
        inspect_local_original(tmp_path, tmp_path / "missing.pdf")


def test_local_original_rejects_parent_segments_streams_and_reparse_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No relative traversal, ADS or reparse indirection can grant file access."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original")
    for path in (tmp_path / "dir" / ".." / "source.pdf", tmp_path / "source.pdf:stream"):
        with pytest.raises(SourceFileUnavailable):
            inspect_local_original(tmp_path, path)
    real_lstat = Path.lstat

    def reparse(path: Path, *args: Any, **kwargs: Any) -> Any:
        actual = real_lstat(path, *args, **kwargs)
        return SimpleNamespace(st_mode=actual.st_mode, st_file_attributes=0x400) if path == original else actual

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(SourceFileUnavailable):
        inspect_local_original(tmp_path, original)


def test_get_hint_does_not_hash_and_post_rechecks_hash_and_returns_correlated_safe_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Availability is cheap, while an explicit reveal verifies the registered bytes."""
    original = tmp_path / "Finance & (draft).pdf"
    original.write_bytes(b"registered bytes")
    record = _record(tmp_path, original)
    launcher = _Launcher()
    real_hash = local_module._file_hash
    monkeypatch.setattr(local_module, "_file_hash", lambda _path: pytest.fail("GET must not hash original bytes"))
    with _client(tmp_path, record, launcher) as client:
        hint = client.get(_FILE)
        assert hint.status_code == 200
        assert hint.json()["name"] == original.name
        assert hint.json()["can_reveal"] is True
        assert str(tmp_path) not in hint.text
        assert hint.json()["request_id"] == hint.headers["x-request-id"]
        monkeypatch.setattr(local_module, "_file_hash", real_hash)
        selected = client.post(f"{_FILE}/reveal", json={}, headers=_ORIGIN)
        assert selected.status_code == 200
        assert selected.json()["status"] == "revealed"
        assert selected.json()["request_id"] == selected.headers["x-request-id"]
        assert str(tmp_path) not in selected.text
        assert launcher.paths == [original.resolve()]


@pytest.mark.parametrize("kind", ["demo", "unregistered", "missing", "changed", "host", "large"])
def test_unavailable_original_never_dispatches(tmp_path: Path, kind: str) -> None:
    """Missing, synthetic, changed and unsupported originals remain non-executable."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"registered bytes")
    record = _record(tmp_path, original, demo=kind == "demo")
    launcher = _Launcher()
    if kind == "unregistered":
        record = record.model_copy(update={"registration": None})
    elif kind == "missing":
        original.unlink()
    elif kind == "changed":
        original.write_bytes(b"modified bytes")
    elif kind == "host":
        launcher.enabled = False
    elif kind == "large":
        with original.open("wb") as stream:
            stream.truncate(local_module._MAX_ORIGINAL_BYTES + 1)
    with _client(tmp_path, record, launcher) as client:
        hint = client.get(_FILE)
        assert hint.status_code == 200
        assert hint.json()["can_reveal"] is (kind == "changed")
        response = client.post(f"{_FILE}/reveal", json={}, headers=_ORIGIN)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SOURCE_FILE_UNAVAILABLE"
        assert str(tmp_path) not in response.text
        assert launcher.paths == []


def test_root_absent_and_unknown_scope_are_disabled_without_guessing_paths(tmp_path: Path) -> None:
    """Server scope resolves before lookup and a root cannot be inferred from metadata."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original")
    persistence = _Originals(_record(tmp_path, original))
    launcher = _Launcher()
    app = create_app(settings=ApiSettings(), persistence=persistence, local_file_launcher=launcher)
    with TestClient(app, base_url="http://127.0.0.1:8011") as client:
        hint = client.get(_FILE).json()
        assert hint["can_reveal"] is False and hint["reason"] == "root_unconfigured"
        assert client.post(f"{_FILE}/reveal", json={}, headers=_ORIGIN).status_code == 409
        calls = persistence.calls
        foreign = client.get(_FILE.replace("/development/", "/foreign/"))
        assert foreign.status_code == 404 and foreign.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
        assert persistence.calls == calls
        unknown = client.get(_FILE.replace("source-real", "unknown-source"))
        assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "SOURCE_NOT_FOUND"
        assert launcher.paths == []


@pytest.mark.parametrize(
    ("headers", "body", "status", "code"),
    [
        ({}, "{}", 403, "FORBIDDEN"),
        ({"Origin": "https://evil.example", "Content-Type": "application/json"}, "{}", 403, "FORBIDDEN"),
        (_ORIGIN, "{}", 415, "UNSUPPORTED_MEDIA_TYPE"),
        ({**_ORIGIN, "Content-Type": "application/json"}, '{"path":"C:/private"}', 400, "INVALID_REQUEST"),
        ({**_ORIGIN, "Content-Type": "application/json"}, "[]", 400, "INVALID_REQUEST"),
        ({**_ORIGIN, "Content-Type": "application/json"}, "null", 400, "INVALID_REQUEST"),
        ({**_ORIGIN, "Content-Type": "application/json"}, '{"x":1,"x":2}', 400, "INVALID_JSON"),
        ({**_ORIGIN, "Content-Type": "application/json"}, " " * 1025 + "{}", 413, "PAYLOAD_TOO_LARGE"),
    ],
)
def test_reveal_transport_blocks_drive_by_and_arbitrary_body(
    tmp_path: Path, headers: dict[str, str], body: str, status: int, code: str
) -> None:
    """Only a deliberate permitted-origin JSON request can reach the native service."""
    launcher = _Launcher()
    with _client(tmp_path, None, launcher) as client:
        response = client.post(f"{_FILE}/reveal", content=body, headers=headers)
        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert launcher.paths == []


def test_reveal_rejects_query_wrong_method_and_external_preflight(tmp_path: Path) -> None:
    """Reveal has its own POST-only preflight and no path-bearing query parameters."""
    launcher = _Launcher()
    with _client(tmp_path, None, launcher) as client:
        assert client.post(f"{_FILE}/reveal?path=anything", json={}, headers=_ORIGIN).status_code == 400
        assert client.get(f"{_FILE}/reveal").status_code == 405
        assert (
            client.options(f"{_FILE}/reveal", headers={**_ORIGIN, "Access-Control-Request-Method": "POST"}).status_code
            == 200
        )
        denied = client.options(f"{_FILE}/reveal", headers={**_ORIGIN, "Access-Control-Request-Method": "GET"})
        assert denied.status_code == 403
        assert launcher.paths == []


def test_native_dispatch_failure_is_sanitized(tmp_path: Path) -> None:
    """Native failures retain correlation without disclosing operating-system details."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original")
    launcher = _Launcher()
    launcher.failure = True
    with _client(tmp_path, _record(tmp_path, original), launcher) as client:
        response = client.post(f"{_FILE}/reveal", json={}, headers=_ORIGIN)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "FILE_REVEAL_FAILED"
        assert "private" not in response.text and str(tmp_path) not in response.text


@pytest.mark.asyncio
async def test_metadata_is_rechecked_after_hash_and_disconnect_prevents_dispatch(tmp_path: Path) -> None:
    """A disconnected caller cannot dispatch Explorer after background hash verification."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original")
    record = _record(tmp_path, original)
    persistence = _Originals(record)
    launcher = _Launcher()
    service = LocalSources(persistence=persistence, root=str(tmp_path), launcher=launcher)

    async def disconnected() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await service.reveal(
            WorkspaceContext(workspace_id="development"),
            source_id="source-real",
            version_id="version-real",
            before_dispatch=disconnected,
        )
    assert persistence.calls == 2
    assert launcher.paths == []


@pytest.mark.asyncio
async def test_active_version_changed_after_hash_refuses_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An active-version or provenance change during verification invalidates dispatch."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original")
    record = _record(tmp_path, original)
    persistence = _Originals(record)
    launcher = _Launcher()
    service = LocalSources(persistence=persistence, root=str(tmp_path), launcher=launcher)

    real_hash = local_module._file_hash

    def hash_then_change(path: Path) -> str:
        digest = real_hash(path)
        persistence.record = record.model_copy(update={"is_demo": True})
        return digest

    monkeypatch.setattr(local_module, "_file_hash", hash_then_change)
    with pytest.raises(SourceFileUnavailable):
        await service.reveal(
            WorkspaceContext(workspace_id="development"), source_id="source-real", version_id="version-real"
        )
    assert launcher.paths == []


@pytest.mark.asyncio
async def test_file_change_after_hash_refuses_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Filesystem identity is rechecked after asynchronous metadata verification."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original")
    record = _record(tmp_path, original)
    launcher = _Launcher()
    service = LocalSources(persistence=_Originals(record), root=str(tmp_path), launcher=launcher)
    real_hash = local_module._file_hash

    def changed_after_hash(path: Path) -> str:
        digest = real_hash(path)
        path.write_bytes(b"changed after hash")
        return digest

    monkeypatch.setattr(local_module, "_file_hash", changed_after_hash)
    with pytest.raises(SourceFileUnavailable):
        await service.reveal(
            WorkspaceContext(workspace_id="development"), source_id="source-real", version_id="version-real"
        )
    assert launcher.paths == []


@pytest.mark.asyncio
async def test_hash_deadline_never_dispatches_after_worker_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verification worker can finish late but owns no native side effect."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original")
    record = _record(tmp_path, original)
    launcher = _Launcher()
    release = threading.Event()
    finished = threading.Event()

    def slow_hash(_path: Path) -> str:
        release.wait(timeout=2)
        finished.set()
        return record.registration.sha256 if record.registration else ""

    monkeypatch.setattr(local_module, "_file_hash", slow_hash)
    monkeypatch.setattr(local_module, "_HASH_TIMEOUT_SECONDS", 0.01)
    service = LocalSources(persistence=_Originals(record), root=str(tmp_path), launcher=launcher)
    try:
        with pytest.raises(SourceFileUnavailable):
            await service.reveal(
                WorkspaceContext(workspace_id="development"), source_id="source-real", version_id="version-real"
            )
    finally:
        release.set()
    await asyncio.to_thread(finished.wait, 2)
    assert launcher.paths == []


@pytest.mark.asyncio
async def test_disconnected_http_transport_never_dispatches_native_action(tmp_path: Path) -> None:
    """The actual ASGI boundary observes disconnect before native dispatch and sends no success."""
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original")
    launcher = _Launcher()
    app = create_app(
        settings=ApiSettings(local_source_root=str(tmp_path)),
        persistence=_Originals(_record(tmp_path, original)),
        local_file_launcher=launcher,
    )
    messages: list[Message] = []
    delivered = False

    async def receive() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"{}", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": "POST",
        "root_path": "",
        "path": f"{_FILE}/reveal",
        "raw_path": f"{_FILE}/reveal".encode(),
        "query_string": b"",
        "server": ("127.0.0.1", 8011),
        "client": ("127.0.0.1", 50000),
        "headers": [
            (b"host", b"127.0.0.1:8011"),
            (b"origin", b"http://127.0.0.1:4173"),
            (b"content-type", b"application/json"),
        ],
    }
    async with app.router.lifespan_context(app):
        await app(scope, receive, send)
    assert messages == []
    assert launcher.paths == []


def test_windows_native_launcher_uses_full_file_pidl_and_balances_com(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typed shell calls select a full-file PIDL and release COM resources on failure."""
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Function:
        argtypes: object = None
        restype: object = None

        def __init__(self, name: str, result: int | None) -> None:
            self.name, self.result = name, result

        def __call__(self, *args: Any) -> int | None:
            calls.append((self.name, args))
            return self.result

    functions = {
        name: Function(name, result)
        for name, result in {
            "CoInitializeEx": 0,
            "CoUninitialize": None,
            "ILCreateFromPathW": 123,
            "SHOpenFolderAndSelectItems": 0,
            "CoTaskMemFree": None,
        }.items()
    }
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(**functions))
    monkeypatch.setattr(WindowsExplorer, "available", lambda _self: True)
    WindowsExplorer().reveal(tmp_path / "Finance & (draft).pdf")
    assert ("SHOpenFolderAndSelectItems", (123, 0, None, 0)) in calls
    assert ("CoTaskMemFree", (123,)) in calls
    assert calls[-1] == ("CoUninitialize", ())
    functions["SHOpenFolderAndSelectItems"].result = -1
    with pytest.raises(FileRevealFailed):
        WindowsExplorer().reveal(tmp_path / "source.pdf")
    assert calls[-1] == ("CoUninitialize", ())


def test_new_routes_publish_schemas_without_changing_search_response() -> None:
    """Local-file discovery is additive and does not modify the lexical result contract."""
    schema = create_app(settings=ApiSettings()).openapi()
    revision = schema["components"]["schemas"]["SearchResponse"]["properties"]["profile_revision"]
    assert revision["default"] == "postgres-fts-baseline-r1"
    assert revision["pattern"] == r"^[A-Za-z0-9_-]{1,128}$"
    assert "name" in schema["components"]["schemas"]["LocalSourceFileResponse"]["required"]
    assert schema["components"]["schemas"]["RevealSourceRequest"]["additionalProperties"] is False
    assert "local_original" not in json.dumps(schema["components"]["schemas"]["SearchResponse"])
