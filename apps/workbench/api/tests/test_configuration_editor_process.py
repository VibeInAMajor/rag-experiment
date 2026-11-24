"""Direct configuration save persists across an actual owned API subprocess restart."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from apps.workbench.api.tests.test_configuration_editor import _ORIGIN, _URL
from apps.workbench.api.tests.test_configuration_editor import editor_settings as editor_settings
from apps.workbench.api.tests.test_ingestion_process import _unused_port
from apps.workbench.configuration.config import ApiSettings

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]


def _spawn(settings: ApiSettings, port: int) -> subprocess.Popen[bytes]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(("WORKBENCH_DB_", "WORKBENCH_TEST_"))
    }
    environment.pop("WORKBENCH_DEFAULT_LANGUAGE", None)
    environment.update(
        WORKBENCH_API_HOST="127.0.0.1",
        WORKBENCH_API_PORT=str(port),
        WORKBENCH_DOCUMENT_PROCESSING_CONFIG=settings.configuration_file or "",
    )
    return subprocess.Popen(
        [sys.executable, "-m", "apps.workbench.api"],
        cwd=Path(__file__).resolve().parents[4],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


async def _live(client: httpx.AsyncClient, process: subprocess.Popen[bytes]) -> None:
    async with asyncio.timeout(15):
        while True:
            if process.poll() is not None:
                pytest.fail("The owned configuration API exited before liveness.")
            try:
                if (await client.get("/api/v1/health/live")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)


async def test_direct_save_survives_actual_process_restart(editor_settings: ApiSettings) -> None:
    """No key or session is needed before or after restart, and saved YAML becomes active."""
    port = _unused_port()
    process = await asyncio.to_thread(_spawn, editor_settings, port)
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", headers=_ORIGIN, trust_env=False, timeout=3
        ) as client:
            await _live(client, process)
            first = (await client.get(_URL)).json()
            text = "# persisted through process restart\ndocument_processing:\n  default_language: ru\n"
            saved = await client.put(_URL, json={"yaml": text, "expected_revision": first["revision"]})
            assert saved.status_code == 200 and saved.json()["activation"] == "requires_restart"
            await asyncio.to_thread(_stop, process)
            process = await asyncio.to_thread(_spawn, editor_settings, port)
            await _live(client, process)
            final = (await client.get(_URL)).json()
            assert final["yaml"] == text and final["revision"] == saved.json()["revision"]
            assert final["activation"] == "active" and final["effective_default_language"] == "ru"
    finally:
        await asyncio.to_thread(_stop, process)
