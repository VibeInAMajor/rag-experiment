import json
import os
import subprocess
import sys
from pathlib import Path

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
    assert len(manifest["calibration_sha256"]) == 64


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
