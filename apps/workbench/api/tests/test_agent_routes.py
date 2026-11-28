"""The optional operations surface only reads local metadata and selects future defaults."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.workbench.agents.journal import AgentJournal, AgentOperationsFailure
from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings

_BASE = "http://127.0.0.1:8011"
_ROOT = "/api/v1/agents"
_SCOPE = "local-operator"
_SELECTION = f"{_ROOT}/semantic-judge/selection"
_INTENT = {"Origin": "http://127.0.0.1:5173", "X-Workbench-Request": "agent-operations"}


def _time(*, days_ago: int = 0, minutes_ago: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago, minutes=minutes_ago)).isoformat()


def _tariff(model: str, revision: str = "tariff-reviewed-r1") -> dict[str, Any]:
    return {
        "provider": "openai",
        "model": model,
        "service_tier": "standard",
        "version": revision,
        "currency": "USD",
        "unit": "per_million_tokens",
        "ordinary_input": "3",
        "cached_read": "0.3",
        "cached_write": None,
        "output": "18",
        "source_url": "https://platform.openai.com/docs/pricing",
        "effective_at": "2026-10-01T00:00:00Z",
        "verified_at": "2026-10-01T00:00:00Z",
        "cache_ttl_seconds": None,
        "status": "verified",
    }


def _profile(profile_id: str, model: str, *, qualified: bool) -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "provider": "openai",
        "model": model,
        "modes": ["answer_grounding", "answerability"],
        "reasoning_effort": "low",
        "max_estimated_input_tokens": 16_384,
        "max_output_tokens": 32_000,
        "max_request_bytes": 16_384,
        "max_response_bytes": 131_072,
        "timeout_seconds": 45,
        "reserve_usd": None,
        "cache_mode": "provider_default",
        "cache_ttl_seconds": None,
        "tariff": _tariff(model),
        "qualification": {
            "state": "qualified" if qualified else "unqualified",
            "reason": "joint_pass" if qualified else "offline_only",
            "revision": "sol-qualification-v8" if qualified else None,
            "verified_at": "2026-10-01T00:00:00Z" if qualified else None,
        },
    }


def _write_catalog(directory: Path, *, alternate_qualified: bool = False) -> dict[str, Any]:
    agent = {
        "agent_id": "semantic-judge",
        "display_name": "Semantic Judge",
        "runtime_revision": "0.3.2",
        "modes": ["answer_grounding", "answerability"],
        "default_profile_id": "semantic-review",
        "profiles": [
            _profile("semantic-review", "gpt-6.1-sol", qualified=True),
            _profile("semantic-review-6.2", "gpt-6.2-sol", qualified=alternate_qualified),
        ],
    }
    (directory / "catalog.json").write_text(
        json.dumps({"schema_version": 1, "scope": _SCOPE, "agents": [agent]}), encoding="utf-8"
    )
    return agent


def _event(run_id: str, sequence: int, kind: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "scope": _SCOPE,
        "run_id": run_id,
        "sequence": sequence,
        "timestamp": _time(),
        "kind": kind,
        **fields,
    }


def _queued(run_id: str, **fields: Any) -> dict[str, Any]:
    return _event(
        run_id,
        1,
        "run_queued",
        stage="queued",
        **fields,
        run={
            "agent_id": "semantic-judge",
            "mode": "batch",
            "origin": "evaluation",
            "profile_id": "semantic-review",
            "model": "gpt-6.1-sol",
            "provider": "openai",
            "runtime_revision": "0.3.1",
            "prompt_revision": "derive_reference/2",
            "schema_revision": "derive_reference/1",
            "cache_mode": "provider_default",
            "tariff": _tariff("gpt-6.1-sol"),
            "planned_cases": 5,
            "budget_usd": "0.5",
        },
    )


def _write_events(directory: Path, run_id: str, *events: dict[str, Any], tail: str = "") -> None:
    (directory / "runs").mkdir(exist_ok=True)
    (directory / "runs" / f"{run_id}.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events) + tail, encoding="utf-8"
    )


def _api(ops: Path | None = None) -> TestClient:
    settings = ApiSettings(agent_operations_directory=str(ops) if ops is not None else None)
    return TestClient(create_app(settings=settings), base_url=_BASE)


def test_agent_operations_are_optional_and_independent_of_retrieval(tmp_path: Path) -> None:
    """Ordinary capabilities are independent from the opt-in local files."""
    with _api() as client:
        assert "agent_operations" not in client.get("/api/v1/capabilities").json()["features"]
        unavailable = client.get(_ROOT)
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "AGENT_OPERATIONS_UNAVAILABLE"
    _write_catalog(tmp_path)
    with _api(tmp_path) as client:
        assert client.get("/api/v1/capabilities").json()["features"]["agent_operations"] is True
        catalog = client.get(_ROOT)
        assert catalog.status_code == 200
        assert catalog.headers["cache-control"] == "no-store"
        assert catalog.json()["history_available"] is False
        assert client.get(_ROOT + "/runs").json()["error"]["code"] == "AGENT_HISTORY_UNAVAILABLE"
        assert client.get("/api/v1/health/live").is_success


def test_agent_selection_rechecks_scope_revision_qualification_and_tariff(tmp_path: Path) -> None:
    """Only matching revisions and independently qualified models persist to the caller's selection file."""
    agent = _write_catalog(tmp_path)
    canonical = json.dumps(agent, sort_keys=True, separators=(",", ":")).encode("utf-8")
    default_revision = f"catalog-{hashlib.sha256(canonical).hexdigest()}"
    change = {"profile_id": "semantic-review-6.2", "expected_revision": default_revision}
    with _api(tmp_path) as client:
        row = client.get(_ROOT).json()["agents"][0]
        assert row["selection"] == {"profile_id": "semantic-review", "revision": default_revision}
        default, alternate = row["profiles"]
        assert default["selectable"] and not alternate["selectable"]
        assert alternate["profile_id"] == "semantic-review-6.2"
        assert [item["max_output_tokens"] for item in (default, alternate)] == [32_000, 32_000]
        for headers in (
            {"Origin": _INTENT["Origin"]},
            {"X-Workbench-Request": "agent-operations"},
            {**_INTENT, "Origin": "https://example.com"},
        ):
            assert client.put(_SELECTION, json=change, headers=headers).status_code == 403
        assert client.put(_SELECTION, json={**change, "model": "invented"}, headers=_INTENT).status_code == 400
        response = client.put(_SELECTION, json=change, headers=_INTENT)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "AGENT_PROFILE_INELIGIBLE"
        assert not (tmp_path / "selection.json").exists()

        _write_catalog(tmp_path, alternate_qualified=True)
        stale = client.put(_SELECTION, json=change, headers=_INTENT)
        assert stale.json()["error"]["code"] == "AGENT_SELECTION_CONFLICT"
        revision = client.get(_ROOT).json()["agents"][0]["selection"]["revision"]
        response = client.put(_SELECTION, json={**change, "expected_revision": revision}, headers=_INTENT)
        assert response.status_code == 200
        saved = response.json()["selection"]
        assert saved["profile_id"] == "semantic-review-6.2"
        assert saved["revision"] != revision
    stored = json.loads((tmp_path / "selection.json").read_text(encoding="utf-8"))
    assert stored["selections"]["semantic-judge"] == saved
    with _api(tmp_path) as client:
        assert client.get(_ROOT).json()["agents"][0]["selection"] == saved


def test_pending_per_call_progress_and_completed_counts_survive_reload(tmp_path: Path) -> None:
    """Only physical and terminal call metadata contribute usage; costs sum as exact decimals."""
    _write_catalog(tmp_path)
    run_id = "local-run"
    queued = _queued(run_id)
    started = _event(run_id, 2, "run_started", stage="admission")
    pending = _event(
        run_id,
        3,
        "call_pending",
        stage="provider",
        call={"call_id": "call-1", "case_id": "case-1", "reserve_usd": "0.05"},
    )
    _write_events(tmp_path, run_id, queued, pending, started, tail='{"incomplete":')
    path = f"{_ROOT}/runs/{run_id}"
    with _api(tmp_path) as client:
        limited = client.get(path, params={"limit": 2}).json()
        assert limited["has_more"]
        assert [event["sequence"] for event in limited["events"]] == [1, 2]
        waiting = client.get(path, params={"cursor": limited["next_cursor"]}).json()
        assert [event["sequence"] for event in waiting["events"]] == [3]
        assert waiting["run"]["pending_calls"] == 1
        assert waiting["run"]["pending_reserve_usd"] == "0.05"
        assert waiting["run"]["physical_requests"] == 0
        assert waiting["run"]["usage"]["input_tokens"] is None

        used = {
            "input_tokens": 19,
            "ordinary_input_tokens": 10,
            "cached_read_tokens": 5,
            "cached_write_tokens": 4,
            "output_tokens": 7,
            "reasoning_tokens": 2,
        }
        charged_failure = _event(
            run_id,
            4,
            "call_completed",
            status="failed",
            reason="INVALID_OUTPUT",
            stage="output_validation",
            call={
                "call_id": "call-1",
                "case_id": "case-1",
                "requests": 1,
                "actual_model": "gpt-6.1-sol",
                "usage": used,
                "estimated_cost_usd": "0.0001425",
            },
        )
        followup = _event(
            run_id,
            5,
            "call_completed",
            status="completed",
            call={
                "call_id": "call-2",
                "case_id": "case-2",
                "requests": 1,
                "actual_model": "gpt-6.1-sol",
                "usage": {"input_tokens": 11, "output_tokens": 3, "reasoning_tokens": 5},
                "estimated_cost_usd": "0.0000575",
            },
        )
        blocked = _event(
            run_id,
            6,
            "call_completed",
            status="blocked",
            reason="EGRESS_DISABLED",
            call={"call_id": "call-3", "case_id": "case-3", "requests": 0},
        )
        reused = _event(run_id, 7, "checkpoint_reused", case_id="case-4")
        finished = _event(run_id, 8, "run_finished", status="completed", stage="finalizing")
        _write_events(
            tmp_path,
            run_id,
            queued,
            started,
            pending,
            charged_failure,
            charged_failure,
            followup,
            blocked,
            reused,
            finished,
        )
        body = client.get(path, params={"cursor": waiting["next_cursor"]}).json()
        assert [event["sequence"] for event in body["events"]] == [4, 5, 6, 7, 8]
        assert body["run"]["status"] == "completed"
        assert body["run"]["prompt_revision"] == "derive_reference/2"
        assert body["run"]["actual_models"] == ["gpt-6.1-sol"]
        assert body["run"]["physical_requests"] == 2
        assert body["run"]["reused_cases"] == 1
        assert body["run"]["usage"] == {
            "input_tokens": 30,
            "ordinary_input_tokens": 10,
            "cached_read_tokens": 5,
            "cached_write_tokens": 4,
            "output_tokens": 10,
            "reasoning_tokens": 2,
            "total_tokens": 40,
        }
        assert body["run"]["estimated_cost_usd"] == "0.0002000"
        assert body["run"]["cost_coverage"] == {"known_calls": 2, "total_calls": 2}
        assert body["run"]["cache_observed_requests"] == body["run"]["cache_hit_requests"] == 1
        assert body["run"]["cache_hit_percent"] == 100
        assert body["run"]["cache_read_percent"] is None
        assert body["run"]["pending_reserve_usd"] is None
        unchanged = client.get(path, params={"cursor": body["next_cursor"]}).json()
        assert unchanged["events"] == [] and unchanged["next_cursor"] == body["next_cursor"]
    with _api(tmp_path) as client:
        assert client.get(path).json()["run"] == body["run"]


def test_history_retention_filtering_and_cursor_scope(tmp_path: Path) -> None:
    """A cursor from another run or filter cannot be applied and aged terminal items are hidden."""
    _write_catalog(tmp_path)
    _write_events(
        tmp_path,
        "retired",
        _queued("retired", timestamp=_time(days_ago=31)),
        _event("retired", 2, "run_finished", timestamp=_time(days_ago=31), status="completed"),
    )
    _write_events(tmp_path, "current-a", _queued("current-a"))
    _write_events(tmp_path, "current-b", _queued("current-b", timestamp=_time(minutes_ago=6)))
    with _api(tmp_path) as client:
        prefix = _ROOT + "/runs"
        first = client.get(prefix, params={"limit": 1, "model": "gpt-6.1-sol"}).json()
        assert [item["run_id"] for item in first["runs"]] == ["current-a"]
        cursor = first["next_cursor"]
        assert client.get(prefix, params={"cursor": cursor}).json()["error"]["code"] == "INVALID_AGENT_CURSOR"
        next_page = client.get(prefix, params={"cursor": cursor, "model": "gpt-6.1-sol"}).json()
        assert next_page["runs"][0]["status"] == "interrupted"
        assert next_page["runs"][0]["finished_at"] is None
        filtered = client.get(prefix, params={"status": "queued"}).json()
        assert [item["run_id"] for item in filtered["runs"]] == ["current-a"]
        event_cursor = client.get(prefix + "/current-a").json()["next_cursor"]
        assert client.get(prefix + "/current-b", params={"cursor": event_cursor}).status_code == 400
        assert client.get(prefix + "/retired").status_code == 404
        assert client.get(prefix, params={"scope": "other"}).status_code == 400
        assert client.get(prefix + "/unknown").status_code == 404


def test_unsafe_records_and_conflicting_sequences_are_unavailable(tmp_path: Path) -> None:
    """Reject source-like event fields, forged scope, and conflicting replays."""
    _write_catalog(tmp_path)
    _write_events(tmp_path, "raw-data", _queued("raw-data", raw_prompt="DO NOT SHOW THIS"))
    _write_events(tmp_path, "wrong-scope", _queued("wrong-scope", scope="other-operator"))
    run_id = "conflicting"
    _write_events(
        tmp_path,
        run_id,
        _queued(run_id),
        _event(run_id, 2, "run_started"),
        _event(run_id, 2, "run_finished", status="completed"),
    )
    with _api(tmp_path) as client:
        prefix = _ROOT + "/runs"
        assert client.get(prefix).json()["runs"] == []
        for unsafe in ["raw-data", "wrong-scope", "conflicting"]:
            response = client.get(f"{prefix}/{unsafe}")
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "AGENT_RUN_UNAVAILABLE"
            assert "DO NOT SHOW THIS" not in response.text
        assert client.get(_ROOT, headers={"Origin": "https://example.com"}).status_code == 403
        assert client.get(_ROOT, headers={"Host": "example.com"}).status_code == 403


def test_journal_rejects_linked_metadata_file(tmp_path: Path) -> None:
    """A link is unsafe even when its target belongs to the designated directory."""
    _write_events(tmp_path, "target", _queued("target"))
    directory = tmp_path / "runs"
    try:
        (directory / "linked.jsonl").symlink_to(directory / "target.jsonl")
    except OSError:
        pytest.skip("Creating file links requires a local filesystem permission")
    with pytest.raises(AgentOperationsFailure, match="AGENT_RUN_UNAVAILABLE"):
        AgentJournal(str(tmp_path)).events("linked")
