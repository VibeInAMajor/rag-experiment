"""Record real lexical HTTP quality and durability without retaining passage bodies."""

import argparse
import json
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from jsonschema import Draft202012Validator

_EVIDENCE = Path("tasks/evidence/postgres-lexical-http-2026-11-21.json")
_CASES = Path("apps/workbench/retrieval/fixtures/lexical-evaluation.json")
_SCHEMA = Path("apps/workbench/api/openapi.json")
_CURSOR = Path(tempfile.gettempdir()) / "workbench-lexical-cursor-2026-11-21.txt"
_SEARCH = "/api/v1/workspaces/development/search"
_DOCUMENTS = "/api/v1/workspaces/development/documents"


def _payload(response: httpx.Response, *, schema: dict[str, Any], component: str) -> dict[str, Any]:
    payload = response.json()
    assert payload["contract_revision"] == "rag-api-v1.0"
    assert payload["request_id"] == response.headers["X-Request-ID"]
    assert payload["trace_id"]
    Draft202012Validator({"$ref": f"#/components/schemas/{component}", "components": schema["components"]}).validate(
        payload
    )
    return payload


def _search(client: httpx.Client, *, profile: dict[str, Any], query: str) -> dict[str, Any]:
    started = monotonic()
    response = client.post(
        _SEARCH,
        json={
            "query": query,
            "top_k": 5,
            "profile_id": profile["profile_id"],
            "expected_profile_revision": profile["profile_revision"],
        },
    )
    assert response.status_code == 200
    payload = _payload(response, schema=json.loads(_SCHEMA.read_text(encoding="utf-8")), component="SearchResponse")
    assert payload["mode"] == "live" and payload["status"] == "success"
    assert sum(stage["duration_ms"] for stage in payload["stages"]) <= payload["duration_ms"]
    compact = []
    for rank, result in enumerate(payload["results"], 1):
        assert result["rank"] == rank and result["score_type"] == "postgres_ts_rank_cd"
        assert "page" not in result or result["page"] > 0
        compact.append(
            {
                **{key: value for key, value in result.items() if key != "content"},
                "content_sha256": sha256(result["content"].encode("utf-8")).hexdigest(),
            }
        )
    return {
        **{key: value for key, value in payload.items() if key != "results"},
        "results": compact,
        "client_elapsed_ms": (monotonic() - started) * 1000,
    }


def _evaluate(client: httpx.Client, profile: dict[str, Any], documents: dict[str, Any]) -> dict[str, Any]:
    cases = json.loads(_CASES.read_text(encoding="utf-8"))
    results = []
    for number, case in enumerate(cases["gated_exact_queries"], 1):
        search = _search(client, profile=profile, query=case["query"])
        assert search["corpus_revision"] == documents["corpus_revision"]
        found = case["expected_source_id"] in [hit["source_id"] for hit in search["results"]]
        results.append(
            {
                "case": number,
                "expected_source_id": case["expected_source_id"],
                "matched_top5": found,
                "response": search,
            }
        )
    matched = sum(case["matched_top5"] for case in results)
    assert matched >= 9
    assert results[0]["response"]["results"] != results[1]["response"]["results"]
    paraphrases = []
    for number, case in enumerate(cases["diagnostic_paraphrases"], 1):
        search = _search(client, profile=profile, query=case["query"])
        paraphrases.append(
            {
                "case": number,
                "expected_source_id": case["expected_source_id"],
                "matched_top5": case["expected_source_id"] in [hit["source_id"] for hit in search["results"]],
                "response": search,
            }
        )
    no_hits = _search(client, profile=profile, query="zzzzlexicalnomatch2026")
    assert no_hits["results"] == []
    return {
        "gated_exact": results,
        "matched_top5": matched,
        "total": len(results),
        "diagnostic_paraphrases": paraphrases,
        "no_match": no_hits,
    }


def _negatives(client: httpx.Client, profile: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    valid = {
        "query": "retention",
        "top_k": 5,
        "profile_id": profile["profile_id"],
        "expected_profile_revision": profile["profile_revision"],
    }
    cases = [
        ("/api/v1/workspaces/foreign/search", valid, 404, "WORKSPACE_NOT_FOUND"),
        (_SEARCH, {**valid, "profile_id": "postgres-keyword-v1"}, 409, "PROFILE_NOT_AVAILABLE"),
        (_SEARCH, {**valid, "expected_profile_revision": "unknown"}, 409, "PROFILE_NOT_AVAILABLE"),
        (_SEARCH, {**valid, "query": "   "}, 400, "INVALID_REQUEST"),
        (_SEARCH, {**valid, "top_k": True}, 400, "INVALID_REQUEST"),
        (_SEARCH, {**valid, "filters": {"workspace_id": "foreign"}}, 400, "INVALID_REQUEST"),
    ]
    outcomes = []
    for path, body, status, code in cases:
        response = client.post(path, json=body)
        assert response.status_code == status
        payload = _payload(response, schema=schema, component="ErrorResponse")
        assert payload["error"]["code"] == code and "run_id" not in payload["error"]
        outcomes.append({"http_status": status, "code": code, "trace_id": payload["trace_id"]})
    return outcomes


def _record_outage() -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    report = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    profile = report["baseline"]["capabilities"]["profiles"][0]
    with httpx.Client(base_url="http://127.0.0.1:8011", timeout=15) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        ready = client.get("/api/v1/health/ready")
        assert ready.status_code == 503
        capabilities = _payload(client.get("/api/v1/capabilities"), schema=schema, component="CapabilitiesResponse")
        assert capabilities["profiles"] == [] and capabilities["dependencies"]["database"]["status"] == "unavailable"
        search = client.post(
            _SEARCH,
            json={
                "query": "retention",
                "top_k": 5,
                "profile_id": profile["profile_id"],
                "expected_profile_revision": profile["profile_revision"],
            },
        )
        documents = client.get(_DOCUMENTS)
        assert search.status_code == documents.status_code == 503
        search_error = _payload(search, schema=schema, component="ErrorResponse")
        assert search_error["error"]["run_id"] and "results" not in search_error
        report["database-unavailable"] = {
            "live_http": 200,
            "ready_http": 503,
            "search_http": 503,
            "documents_http": 503,
            "capabilities": capabilities,
            "search_error": search_error,
            "documents_error": _payload(documents, schema=schema, component="ErrorResponse"),
        }
    _EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Database outage: live 200, ready/search/documents 503, no profile or fallback results.")


def main() -> None:
    """Compare actual HTTP identities, scores and content hashes across restarts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("baseline", "after-api", "after-database", "database-unavailable"))
    phase = parser.parse_args().phase
    if phase == "database-unavailable":
        _record_outage()
        return
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    with httpx.Client(base_url="http://127.0.0.1:8011", timeout=15) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        assert client.get("/api/v1/health/ready").status_code == 200
        capabilities = _payload(client.get("/api/v1/capabilities"), schema=schema, component="CapabilitiesResponse")
        assert capabilities["features"] == {"documents": True, "search": True}
        assert capabilities["dependencies"]["database"]["status"] == "ready"
        (profile,) = capabilities["profiles"]
        assert profile["profile_id"] == "postgres-fts-baseline"
        workspaces = _payload(client.get("/api/v1/workspaces"), schema=schema, component="WorkspacePage")
        assert [workspace["workspace_id"] for workspace in workspaces["items"]] == ["development"]
        documents = _payload(client.get(_DOCUMENTS), schema=schema, component="DocumentPage")
        assert len(documents["items"]) == 8
        first_page = client.get(_DOCUMENTS, params={"limit": 3}).json()
        if phase == "baseline":
            _CURSOR.write_text(first_page["next_cursor"], encoding="ascii")
        elif phase == "after-api":
            assert client.get(_DOCUMENTS, params={"cursor": _CURSOR.read_text(encoding="ascii")}).status_code == 400
        evaluation = _evaluate(client, profile, documents)
        negatives = _negatives(client, profile, schema)
    signature = sha256(
        json.dumps([case["response"]["results"] for case in evaluation["gated_exact"]], sort_keys=True).encode()
    ).hexdigest()
    observation = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "ready_http": 200,
        "capabilities": capabilities,
        "documents": documents,
        "search_fingerprint": signature,
        "evaluation": evaluation,
        "negative_cases": negatives,
    }
    report = {} if phase == "baseline" else json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    if phase != "baseline":
        assert report["baseline"]["search_fingerprint"] == signature
        assert report["baseline"]["documents"]["corpus_revision"] == documents["corpus_revision"]
        assert report["baseline"]["documents"]["items"] == documents["items"]
    report[phase] = observation
    _EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    _EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "exact_top5": f"{evaluation['matched_top5']}/10",
                "documents": 8,
                "corpus_revision": documents["corpus_revision"],
                "search_fingerprint": signature,
                "status": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
