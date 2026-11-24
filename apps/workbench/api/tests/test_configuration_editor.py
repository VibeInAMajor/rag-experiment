"""Direct local configuration access, canonical validation and atomic persistence."""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.configuration.configuration import ConfigurationFailure, ConfigurationStore

_URL = "/api/v1/configuration"
_ORIGIN = {"Origin": "http://127.0.0.1:4173", "X-Workbench-Request": "configuration"}
_YAML = "# preserve this comment\ndocument_processing:\n  default_language: en\n"
pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture
def editor_settings(tmp_path: Path) -> ApiSettings:
    """Use only a temporary selected YAML, without credentials or login setup."""
    source = tmp_path / "processing.yaml"
    source.write_text(_YAML, encoding="utf-8", newline="\n")
    return ApiSettings.from_env({"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": str(source)})


@pytest_asyncio.fixture(loop_scope="function")
async def editor_client(editor_settings: ApiSettings) -> AsyncIterator[httpx.AsyncClient]:
    """Run the actual HTTP boundary with local application request intent."""
    app = create_app(settings=editor_settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011", headers=_ORIGIN
        ) as client,
    ):
        yield client


async def test_configuration_opens_directly_without_keys_or_sessions(editor_client: httpx.AsyncClient) -> None:
    """The user-selected local access model requires no operator form or credential endpoints."""
    response = await editor_client.get(_URL)
    assert response.status_code == 200 and response.json()["yaml"] == _YAML
    assert "set-cookie" not in response.headers
    assert (await editor_client.get(_URL + "/session")).status_code == 404
    assert response.headers["cache-control"] == "no-store"


async def test_exact_roundtrip_restart_and_conflict(
    editor_client: httpx.AsyncClient, editor_settings: ApiSettings
) -> None:
    """Preserve comments/order and reject a stale revision; a fresh application consumes the same source."""
    first = (await editor_client.get(_URL)).json()
    content = _YAML + "  recursive_splitter:\n    split_length: 120\n    split_overlap: 12\n"
    assert (await editor_client.post(_URL + "/validate", json={"yaml": content})).json()["valid"]
    saved = await editor_client.put(_URL, json={"yaml": content, "expected_revision": first["revision"]})
    assert saved.status_code == 200 and saved.json()["activation"] == "requires_restart"
    assert saved.json()["yaml"] == content
    assert (
        await editor_client.put(_URL, json={"yaml": _YAML, "expected_revision": first["revision"]})
    ).status_code == 409
    restarted = create_app(
        settings=ApiSettings.from_env(
            {"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": editor_settings.configuration_file or ""}
        )
    )
    async with (
        restarted.router.lifespan_context(restarted),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted), base_url="http://127.0.0.1:8011", headers=_ORIGIN
        ) as client,
    ):
        final = (await client.get(_URL)).json()
        assert (
            final["yaml"] == content
            and final["revision"] == saved.json()["revision"]
            and final["activation"] == "active"
        )


@pytest.mark.parametrize(
    "content",
    [
        "document_processing: [",
        "document_processing: {}\ndocument_processing: {}",
        "document_processing: &base {}\nother: *base",
        "document_processing: !!python/object:os.system {}",
        "document_processing:\n  default_language: uk",
        "document_processing:\n  recursive_splitter:\n    split_length: 50\n    split_overlap: 50",
        "document_processing:\n  recursive_splitter:\n    split_unit: word",
        "document_processing:\n  unknown: value",
        "document_processing:\n  native_model_guard:\n    enabled: false\n    local_asset_directory: C:/arbitrary",
        'document_processing:\n  native_model_guard:\n    prefix: "\\uD800"',
        'document_processing:\n  "\\uD800": 1',
    ],
)
async def test_invalid_configuration_never_replaces_saved_version(
    editor_client: httpx.AsyncClient, content: str
) -> None:
    """Dangerous YAML and schema violations use the canonical diagnostics and retain the prior document."""
    first = (await editor_client.get(_URL)).json()
    result = await editor_client.post(_URL + "/validate", json={"yaml": content})
    assert result.status_code == 200 and result.json()["valid"] is False and result.json()["errors"]
    assert (
        await editor_client.put(_URL, json={"yaml": content, "expected_revision": first["revision"]})
    ).status_code == 400
    assert (await editor_client.get(_URL)).json()["revision"] == first["revision"]


async def test_origin_request_intent_and_size_remain_enforced(editor_client: httpx.AsyncClient) -> None:
    """Removing login does not allow cross-site browser writes or oversized documents."""
    editor_client.headers.pop("X-Workbench-Request")
    assert (await editor_client.get(_URL)).status_code == 403
    editor_client.headers["X-Workbench-Request"] = "configuration"
    assert (
        await editor_client.post(
            _URL + "/validate", json={"yaml": _YAML}, headers={"Origin": "https://foreign.invalid"}
        )
    ).status_code == 403
    editor_client.headers.pop("Origin")
    assert (await editor_client.post(_URL + "/validate", json={"yaml": _YAML})).status_code == 403
    editor_client.headers.update(_ORIGIN)
    assert (await editor_client.post(_URL + "/validate", json={"yaml": "#" + "a" * 65536})).status_code == 413


async def test_secret_values_and_logs_are_content_free(
    editor_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Reject credential URIs and never log ordinary YAML canaries."""
    assert (
        await editor_client.post(
            _URL + "/validate", json={"yaml": "# postgresql://user:password@localhost/db\n" + _YAML}
        )
    ).status_code == 400
    first = (await editor_client.get(_URL)).json()
    with caplog.at_level(logging.INFO):
        response = await editor_client.put(
            _URL, json={"yaml": "# yaml-body-canary\n" + _YAML, "expected_revision": first["revision"]}
        )
    assert (
        response.status_code == 200 and "configuration_saved" in caplog.text and "yaml-body-canary" not in caplog.text
    )


async def test_simultaneous_writers_and_atomic_failure(
    editor_settings: ApiSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One CAS winner publishes; a failed final replace leaves the preimage intact."""
    import apps.workbench.configuration.configuration as module

    stores = [ConfigurationStore(editor_settings, state_directory=tmp_path / "history") for _ in range(2)]
    first = await asyncio.to_thread(stores[0].read)
    results = await asyncio.gather(
        *(
            asyncio.to_thread(store.save, f"# writer {index}\n" + _YAML, expected_revision=first.revision)
            for index, store in enumerate(stores)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ConfigurationFailure) and result.status == 409 for result in results) == 1
    before = await asyncio.to_thread(stores[0].read)
    replace = module.os.replace

    def failed(source: str, destination: Path) -> None:
        if destination == Path(editor_settings.configuration_file or ""):
            raise OSError("private-error-canary")
        replace(source, destination)

    monkeypatch.setattr(module.os, "replace", failed)
    with pytest.raises(ConfigurationFailure):
        await asyncio.to_thread(stores[0].save, "# refused\n" + _YAML, expected_revision=before.revision)
    assert await asyncio.to_thread(stores[0].read) == before
