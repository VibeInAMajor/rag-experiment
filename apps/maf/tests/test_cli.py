import json
import os
import subprocess
import sys
from io import BytesIO, TextIOWrapper
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_runtime import cli
from agent_runtime.contracts import ErrorCode, InvocationResult
from agent_runtime.runtime import AgentRuntime

_ENVELOPE = {
    "schema_version": 1,
    "request_id": "synthetic-request",
    "agent_id": "structured-smoke",
    "profile_id": "semantic-review",
    "input": {"text": "The synthetic marker is cobalt."},
}
_PAYLOAD = json.dumps(_ENVELOPE).encode()
_OPT_IN = ("--allow-external", "--data-classification", "synthetic")


def _run(tmp_path: Path, payload: bytes, *args: str) -> InvocationResult:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("MAF_OPENAI_REASONING_EFFORT", None)
    completed = subprocess.run(
        [sys.executable, "-I", "-m", "agent_runtime", *args],
        input=payload,
        env=env,
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 1, (completed.stdout, completed.stderr)
    assert completed.stderr == b""
    assert len(completed.stdout.splitlines()) == 1
    result = InvocationResult.model_validate_json(completed.stdout)
    assert result.outcome == "error"
    assert result.output is None
    return result


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ((), ErrorCode.EGRESS_DISABLED),
        (("--allow-external",), ErrorCode.EGRESS_DISABLED),
        (_OPT_IN, ErrorCode.MISSING_CREDENTIALS),
    ],
)
def test_cli_requires_opt_in_classification_and_key(
    tmp_path: Path, flags: tuple[str, ...], expected: ErrorCode
) -> None:
    result = _run(tmp_path, _PAYLOAD, *flags)

    assert result.schema_version == 1
    assert result.request_id == "synthetic-request"
    assert result.agent_id == "structured-smoke"
    assert result.profile_id == "semantic-review"
    assert result.error is not None and result.error.code == expected
    assert result.metadata.requests == 0


def test_builtin_smoke_is_offline_by_default(tmp_path: Path) -> None:
    result = _run(tmp_path, b"", "--smoke")

    assert result.error is not None and result.error.code == ErrorCode.EGRESS_DISABLED
    assert result.metadata.requests == 0


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{",
        b"\xff",
        json.dumps({**_ENVELOPE, "schema_version": 2}).encode(),
        json.dumps({**_ENVELOPE, "schema_version": True}).encode(),
        json.dumps({**_ENVELOPE, "instructions": "untrusted-instruction-sentinel"}).encode(),
        json.dumps({**_ENVELOPE, "request_id": "bad id"}).encode(),
        json.dumps({**_ENVELOPE, "input": {"text": 4}}).encode(),
        _PAYLOAD.replace(b'"schema_version": 1', b'"schema_version": 2, "schema_version": 1'),
        _PAYLOAD.replace(b'"The synthetic marker is cobalt."', b"NaN"),
        _PAYLOAD + b"\n" + _PAYLOAD,
    ],
)
def test_cli_returns_one_sanitized_error_envelope_for_invalid_payload(tmp_path: Path, payload: bytes) -> None:
    result = _run(tmp_path, payload, *_OPT_IN)

    assert result.error is not None and result.error.code == ErrorCode.INVALID_INPUT
    assert "untrusted-instruction-sentinel" not in result.model_dump_json()
    assert result.metadata.requests == 0


def test_cli_enforces_stdin_byte_limit(tmp_path: Path) -> None:
    at_limit = _PAYLOAD.ljust(8192)

    admitted_payload = _run(tmp_path, at_limit)
    rejected_payload = _run(tmp_path, at_limit + b" ")

    assert admitted_payload.error is not None and admitted_payload.error.code == ErrorCode.EGRESS_DISABLED
    assert rejected_payload.error is not None and rejected_payload.error.code == ErrorCode.INVALID_INPUT


@pytest.mark.parametrize(
    ("flags", "marker", "expected_exit"),
    [
        (_OPT_IN, "cobalt", 0),
        (("--smoke", "--allow-external"), "cobalt", 0),
        (("--smoke", "--allow-external"), "other", 1),
    ],
)
def test_cli_serializes_valid_output_and_checks_builtin_smoke_marker(
    monkeypatch: pytest.MonkeyPatch,
    capfdbinary: pytest.CaptureFixture[bytes],
    flags: tuple[str, ...],
    marker: str,
    expected_exit: int,
) -> None:
    port = AsyncMock(spec=AgentRuntime)
    port.invoke.return_value = json.dumps({"marker": marker})
    monkeypatch.setattr(cli, "create_runtime", lambda: port)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-provider-key-sentinel")
    monkeypatch.delenv("MAF_OPENAI_REASONING_EFFORT", raising=False)
    with TextIOWrapper(BytesIO(_PAYLOAD), encoding="utf-8") as stdin:
        monkeypatch.setattr(sys, "stdin", stdin)

        assert cli.main(flags) == expected_exit

    captured = capfdbinary.readouterr()
    assert captured.err == b""
    assert len(captured.out.splitlines()) == 1
    assert b"offline-provider-key-sentinel" not in captured.out
    result = InvocationResult.model_validate_json(captured.out)
    if expected_exit == 0:
        assert result.outcome == "ok"
        assert result.output == {"marker": "cobalt"}
        assert result.error is None
    else:
        assert result.outcome == "error"
        assert result.output is None
        assert result.error is not None and result.error.code == ErrorCode.INVALID_OUTPUT
    port.invoke.assert_awaited_once()
