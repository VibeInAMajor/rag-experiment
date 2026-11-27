import asyncio
import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_runtime.configuration import SEMANTIC_REVIEW_PROFILE, load_profiles
from agent_runtime.runtime import AgentApplication, AgentRuntime
from calibration.controls import DEVELOPMENT_CASES
from calibration.run import _run_live

_APP = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("OPENAI_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "calibration", *args],
        cwd=_APP,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_frozen_controls_fit_runtime_with_no_credentials() -> None:
    process = _run("--check")
    assert process.returncode == 0, process.stderr
    manifest = json.loads(process.stdout)
    assert manifest["status"] == "FROZEN_OFFLINE"
    assert manifest["distinct_cases"] >= 24
    assert manifest["repeat_count"] >= 3
    assert manifest["case_count"] == manifest["request_limit"]
    assert set(manifest["modes"]) == {"derive_reference", "judge_evidence", "judge_context", "judge_answer"}
    assert manifest["configured_model"] == "gpt-6.1-sol"
    assert manifest["concurrency"] == 1
    assert manifest["retries"] == 0
    assert manifest["case_count"] == 32
    assert manifest["control_manifest_sha256"] == "caa72c9408c4ab4a2066671524be825824addebbc5491b94fead1597c4b606cf"
    assert manifest["limits"]["cli_request_bytes"] == 16_384
    assert manifest["limits"]["judge_context_fragments"] == 12
    assert manifest["limits"]["estimated_input_tokens"] == 16_384
    assert manifest["limits"]["output_tokens"] == 32_000
    assert manifest["estimated_max_cost_usd"] == "12.705792"
    assert manifest["budget_ceiling_usd"] == "15.00"
    assert len(manifest["calibration_sha256"]) == 64


def test_only_the_review_profile_increases_its_reserve() -> None:
    profiles = load_profiles({})
    assert profiles[SEMANTIC_REVIEW_PROFILE].max_output_tokens == 32_000
    assert str(profiles[SEMANTIC_REVIEW_PROFILE].estimated_max_cost_usd) == "0.397056"
    assert profiles["semantic-review-6.2"].max_output_tokens == 2_048
    assert str(profiles["semantic-review-6.2"].estimated_max_cost_usd) == "0.045056"


def test_calibration_requires_explicit_mode() -> None:
    process = _run()
    assert process.returncode == 2
    assert process.stdout == ""


def test_missing_key_checkpoints_blocker_without_calling_provider(tmp_path: Path) -> None:
    report = tmp_path / "live-report.jsonl"
    process = _run("--allow-external", "--report", str(report))

    assert process.returncode == 1, process.stderr
    manifest, case, summary = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()]
    assert manifest["event"] == "manifest"
    assert case["event"] == "case"
    assert case["result"]["error"]["code"] == "MISSING_CREDENTIALS"
    assert summary["status"] == "BLOCKED_REAL_API"
    assert summary["provider_requests"] == 0
    assert summary["unexecuted"] == manifest["case_count"] - 1
    assert summary["estimated_cost_usd_with_complete_usage"] is None


def test_existing_report_is_preserved(tmp_path: Path) -> None:
    report = tmp_path / "live-report.jsonl"
    report.write_text("saved results", encoding="utf-8")
    process = _run("--allow-external", "--report", str(report))

    assert process.returncode == 1, process.stderr
    assert json.loads(process.stdout) == {"status": "REPORT_EXISTS"}
    assert report.read_text(encoding="utf-8") == "saved results"


@pytest.mark.parametrize(
    ("unexpected_field", "stage", "reason"),
    [(False, "evidence_validation", "quote_not_found"), (True, "output_schema", "schema_extra_forbidden")],
)
def test_rejected_verdict_checkpoint_records_rule_without_response_text(
    monkeypatch: pytest.MonkeyPatch, unexpected_field: bool, stage: str, reason: str
) -> None:
    case = next(case for case in DEVELOPMENT_CASES if case.case_id == "dev-reference-sensor-model")
    rejected_text = "injected rejected content"
    port = AsyncMock(spec=AgentRuntime)
    reply = {
        "mode": "derive_reference",
        "rationale": rejected_text,
        "answerability": "answerable",
        "reference_answer": "P-37",
        "constraints": [],
        "facts": [
            {
                "id": "model",
                "statement": "Model P-37",
                "required": True,
                "quotes": [{"source_id": "equipment-card", "start": None, "end": None, "text": rejected_text}],
            }
        ],
        "coverage_gaps": [],
    }
    if unexpected_field:
        reply[rejected_text] = "extra value"
    port.invoke.return_value = json.dumps(reply)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    application = AgentApplication(lambda: port, load_profiles({}))
    stream = StringIO()

    asyncio.run(_run_live([case], application=application, report=stream, development=True))

    row = json.loads(stream.getvalue().splitlines()[0])
    assert row["failure_stage"] == stage
    assert row["failure_reason"] == reason
    assert row["failure_field"] is None
    assert row["result"]["error"]["code"] == "INVALID_OUTPUT"
    assert row["result"]["output"] is None
    assert rejected_text not in stream.getvalue()
