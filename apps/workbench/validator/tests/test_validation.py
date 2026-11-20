"""Contracts for the validation-only boundary; no component is executed."""

import http.client
import json
import re
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from apps.workbench.validator import validator as validation_module
from apps.workbench.validator.registry import REGISTRY, create_component
from apps.workbench.validator.schemas import ValidationRequest
from apps.workbench.validator.server import create_server
from apps.workbench.validator.validator import validate_graph
from haystack import Pipeline


def _node(kind: str, identifier: str, **parameters: Any) -> dict[str, Any]:
    defaults: dict[str, dict[str, Any]] = {
        "bm25": {"collection": "Product knowledge", "topK": 20},
        "joiner": {"topK": 8},
        "chunker": {"size": 500, "overlap": 50},
        "text-embedder": {"model": "Qwen3-Embedding-4B"},
        "document-embedder": {"model": "Qwen3-Embedding-4B", "batchSize": 16},
        "files": {"source": "Workspace documents"},
        "parser": {"format": "Markdown"},
        "writer": {"collection": "Product knowledge"},
        "query": {"query": "example"},
        "vector": {"collection": "Product knowledge", "topK": 20},
        "results": {"limit": 5},
    }
    return {
        "id": identifier,
        "type": "workbench",
        "position": {"x": 0, "y": 0},
        "data": {"kind": kind, "label": identifier, "parameters": {**defaults[kind], **parameters}},
    }


def _edge(source: str, target: str, output: str = "documents", input_name: str = "documents") -> dict[str, str]:
    return {
        "id": f"edge-{source}-{target}",
        "source": source,
        "target": target,
        "sourceHandle": output,
        "targetHandle": input_name,
        "type": "smoothstep",
    }


def _payload(nodes: list[dict[str, Any]], edges: list[dict[str, Any]] | None = None, **kwargs: Any) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "requestId": "contract-request",
        "graph": {"nodes": nodes, "edges": edges or []},
        **kwargs,
    }


def _validate(payload: dict[str, Any]) -> dict[str, Any]:
    return validate_graph(ValidationRequest.model_validate(payload))


def test_complete_graph_delegates_to_real_haystack_without_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify real component registration rather than a synthetic success response."""
    registered: list[str] = []
    connections: list[tuple[str, str]] = []
    add_component = Pipeline.add_component
    connect = Pipeline.connect

    def register(pipeline: Pipeline, name: str, instance: Any) -> Any:
        registered.append(type(instance).__name__)
        return add_component(pipeline, name=name, instance=instance)

    def wire(pipeline: Pipeline, sender: str, receiver: str) -> Any:
        connections.append((sender, receiver))
        return connect(pipeline, sender=sender, receiver=receiver)

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("Validation must not execute or warm up a component")

    monkeypatch.setattr(Pipeline, "add_component", register)
    monkeypatch.setattr(Pipeline, "connect", wire)
    monkeypatch.setattr(Pipeline, "run", forbidden)
    monkeypatch.setattr(Pipeline, "warm_up", forbidden)
    source = "ui.id / not-a-python-name"
    result = _validate(
        _payload(
            [_node("bm25", source), _node("joiner", "fusion")],
            [_edge(source, "fusion")],
            mode="complete",
            inputs={source: {"query": "example"}},
        )
    )
    assert result["status"] == "valid", result
    assert result["validator"] == "haystack"
    assert result["requestId"] == "contract-request"
    assert result["capabilityVersion"] == "workbench-components-v1"
    assert registered == ["InMemoryBM25Retriever", "DocumentJoiner"]
    assert len(connections) == 1
    assert source not in connections[0][0]


def test_draft_and_complete_have_distinct_missing_input_behavior() -> None:
    """Require execution inputs only at the documented complete-check level."""
    payload = _payload([_node("bm25", "lexical")], mode="draft")
    assert _validate(payload)["status"] == "valid"
    result = _validate({**payload, "mode": "complete"})
    assert result["status"] == "invalid"
    assert any(
        issue["code"] == "MISSING_REQUIRED_INPUT" and issue.get("nodeId") == "lexical" for issue in result["issues"]
    )


def test_explicit_runtime_inputs_are_checked_by_public_haystack_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preserve Haystack ownership when actual execution inputs are supplied."""
    calls: list[dict[str, Any]] = []
    original = Pipeline.validate_input

    def validate(pipeline: Pipeline, data: dict[str, Any]) -> None:
        calls.append(data)
        original(pipeline, data=data)

    monkeypatch.setattr(Pipeline, "validate_input", validate)
    result = _validate(_payload([_node("bm25", "search")], inputs={"search": {"query": "hello"}}))
    assert result["status"] == "valid", result
    assert len(calls) == 1
    assert list(calls[0].values()) == [{"query": "hello"}]


@pytest.mark.parametrize(
    ("output", "input_name", "expected"),
    [("documents", "text", "INCOMPATIBLE_SOCKET"), ("not-a-port", "text", "INVALID_PORT")],
)
def test_connection_errors_preserve_ui_identifiers(output: str, input_name: str, expected: str) -> None:
    """Map runtime errors back to the stable editor edge identifier."""
    edge = _edge("search", "embedding", output, input_name)
    result = _validate(_payload([_node("bm25", "search"), _node("text-embedder", "embedding")], [edge], mode="draft"))
    assert result["status"] == "invalid", result
    assert any(issue["code"] == expected and issue.get("edgeId") == edge["id"] for issue in result["issues"])


@pytest.mark.parametrize("kind", ["files", "query", "results", "parser", "writer", "vector"])
def test_unmapped_components_never_receive_a_valid_verdict(kind: str) -> None:
    """Prevent successful validation through pass-through substitutes."""
    result = _validate(_payload([_node(kind, "unsupported-node")], mode="draft"))
    assert result["status"] == "unsupported", result
    assert any(
        issue["code"] == "UNSUPPORTED_COMPONENT" and issue.get("nodeId") == "unsupported-node"
        for issue in result["issues"]
    )


def test_real_haystack_cycle_is_not_rejected_as_a_dag_rule() -> None:
    """Keep the fixture preview restriction out of authoritative semantics."""
    result = _validate(
        _payload(
            [_node("chunker", "first"), _node("chunker", "second")],
            [_edge("first", "second"), _edge("second", "first")],
            mode="draft",
        )
    )
    assert result["status"] == "valid", result


def test_embedding_components_do_not_create_clients_or_require_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard the no-provider-work boundary even for approved embedder constructors."""

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("Validation must not create provider clients")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(httpx.Client, "__init__", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", forbidden)
    result = _validate(
        _payload(
            [_node("text-embedder", "query-embedding"), _node("document-embedder", "document-embedding")], mode="draft"
        )
    )
    assert result["status"] == "valid", result


def test_registry_covers_the_frontend_catalog_and_real_component_sockets() -> None:
    """Detect catalog additions and socket drift against installed component declarations."""
    catalog_path = Path(__file__).resolve().parents[2] / "web" / "src" / "domain" / "catalog.ts"
    ui_kinds = set(re.findall(r'kind:\s*"([a-z0-9-]+)"', catalog_path.read_text(encoding="utf-8")))
    assert set(REGISTRY) == ui_kinds
    stores: list[Any] = []
    try:
        for kind, mapping in REGISTRY.items():
            if mapping.component is None:
                assert mapping.reason
                continue
            pipeline = Pipeline()
            pipeline.add_component(
                name="reviewed", instance=create_component(kind, _node(kind, kind)["data"]["parameters"], stores)
            )
            assert set(mapping.inputs.values()) <= set(pipeline.inputs()["reviewed"])
            assert set(mapping.outputs.values()) <= set(pipeline.outputs()["reviewed"])
    finally:
        for store in stores:
            store.shutdown()


@pytest.mark.parametrize("mutation", ["module", "unknown-kind", "extra-parameter", "too-many-nodes", "too-many-edges"])
def test_untrusted_shapes_are_rejected_before_component_construction(
    mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject executable fields and resource-exhaustion shapes before constructing components."""
    payload = _payload([_node("chunker", "split")])
    if mutation == "module":
        payload["graph"]["nodes"][0]["module"] = "os.system"
    elif mutation == "unknown-kind":
        payload["graph"]["nodes"][0]["data"]["kind"] = "os.system"
    elif mutation == "extra-parameter":
        payload["graph"]["nodes"][0]["data"]["parameters"]["unexpected"] = "unsupported"
    elif mutation == "too-many-nodes":
        payload["graph"]["nodes"] = [_node("chunker", str(index)) for index in range(101)]
    else:
        payload["graph"]["edges"] = [_edge("split", "split") for _ in range(301)]

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("Malformed graphs must be rejected before component registration")

    monkeypatch.setattr(Pipeline, "add_component", forbidden)
    if mutation in {"unknown-kind", "extra-parameter"}:
        result = _validate(payload)
        expected_code = "UNKNOWN_COMPONENT_KIND" if mutation == "unknown-kind" else "INVALID_PARAMETER"
        assert any(issue["code"] == expected_code for issue in result["issues"]), result
        assert result["status"] != "valid"
    else:
        with pytest.raises((ValidationError, ValueError)):
            _validate(payload)


@pytest.fixture()
def local_server() -> Iterator[ThreadingHTTPServer]:
    """Serve isolated ephemeral loopback requests without deployed infrastructure."""
    server = create_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _http(server: Any, body: bytes, **headers: str) -> tuple[int, Any]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    connection.request(
        "POST", "/api/pipelines/validate", body=body, headers={"Content-Type": "application/json", **headers}
    )
    response = connection.getresponse()
    status = response.status
    content = response.read()
    connection.close()
    return status, json.loads(content)


def test_http_contract_and_allowed_local_origin(local_server: Any) -> None:
    """Accept the local frontend origin through the real HTTP boundary."""
    body = json.dumps(_payload([_node("bm25", "search")], mode="draft")).encode()
    status, result = _http(local_server, body, Origin="http://127.0.0.1:5173")
    assert status == 200
    assert result["status"] == "valid"


@pytest.mark.parametrize("headers", [{"Origin": "https://untrusted.example"}, {"Host": "untrusted.example"}])
def test_http_rejects_cross_origin_and_nonlocal_host(local_server: Any, headers: dict[str, str]) -> None:
    """Reject browser cross-origin requests and DNS-rebinding host values."""
    status, _ = _http(local_server, b"{}", **headers)
    assert status == 403


def test_http_rejects_large_payload_before_parsing(local_server: Any) -> None:
    """Enforce the body bound before JSON decoding."""
    status, _ = _http(local_server, b" " * 1000001)
    assert status == 413


def test_http_rate_limit_applies_across_requests(local_server: Any) -> None:
    """Refuse new work once the shared sixty-admission window is exhausted."""
    assert all(local_server.admit() for _ in range(60))
    status, result = _http(local_server, b"{}")
    assert status == 429
    assert result["error"] == "VALIDATION_BUSY"


def test_http_parallelism_guard_refuses_work_when_slots_are_occupied(local_server: Any) -> None:
    """Bound simultaneous validation work independently of the request rate."""
    assert local_server.validation_slots.acquire(blocking=False)
    assert local_server.validation_slots.acquire(blocking=False)
    try:
        status, result = _http(local_server, b"{}")
        assert status == 429
        assert result["error"] == "VALIDATION_BUSY"
    finally:
        local_server.validation_slots.release()
        local_server.validation_slots.release()


def test_http_schema_errors_do_not_echo_private_payload(local_server: Any) -> None:
    """Return stable diagnostics without tracebacks or attacker-controlled text."""
    payload = _payload([_node("chunker", "split")])
    payload["graph"]["nodes"][0]["module"] = "private-payload-marker"
    status, result = _http(local_server, json.dumps(payload).encode())
    assert status == 400
    assert result["error"] == "INVALID_GRAPH"
    assert "private-payload-marker" not in json.dumps(result)
    assert "Traceback" not in json.dumps(result)


@pytest.mark.parametrize("field", ["boolean-version", "string-coordinate", "duplicate-node"])
def test_schema_rejects_coercions_and_ambiguous_ids(field: str) -> None:
    """Keep JSON acceptance strict rather than relying on Python truthiness."""
    payload = _payload([_node("chunker", "split")])
    if field == "boolean-version":
        payload["schemaVersion"] = True
    elif field == "string-coordinate":
        payload["graph"]["nodes"][0]["position"]["x"] = "0"
    else:
        payload["graph"]["nodes"].append(_node("chunker", "split"))
    with pytest.raises(ValidationError):
        ValidationRequest.model_validate(payload)


def test_missing_constructor_parameter_blocks_complete_validation() -> None:
    """Expose an absent required UI constructor projection as incomplete."""
    node = _node("chunker", "split")
    del node["data"]["parameters"]["size"]
    result = _validate(_payload([node]))
    assert result["status"] == "invalid"
    assert any(issue.get("field") == "size" and issue["code"] == "INVALID_PARAMETER" for issue in result["issues"])


def test_uninstalled_optional_constructor_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Import failures must never become a synthetic supported component."""

    def unavailable(*_args: Any, **_kwargs: Any) -> None:
        raise ImportError("private dependency path")

    monkeypatch.setattr(validation_module, "create_component", unavailable)
    result = _validate(_payload([_node("chunker", "split")], mode="draft"))
    assert result["status"] == "unsupported"
    assert result["issues"][0]["code"] == "UNSUPPORTED_COMPONENT"
    assert "private dependency path" not in json.dumps(result)


def test_connected_list_input_retains_haystack_variadic_rules() -> None:
    """Do not invent a scalar-input restriction for Haystack list fan-in."""
    result = _validate(
        _payload(
            [_node("bm25", "search"), _node("chunker", "split")],
            [_edge("search", "split")],
            inputs={"search": {"query": "example"}, "split": {"documents": []}},
        )
    )
    assert result["status"] == "valid", result


def test_unknown_execution_socket_is_rejected_by_haystack() -> None:
    """Reject supplied input names that the installed component does not declare."""
    result = _validate(_payload([_node("bm25", "search")], inputs={"search": {"query": "example", "unknown": []}}))
    assert result["status"] == "invalid", result
    assert any(issue["code"] == "INVALID_RUNTIME_INPUT" for issue in result["issues"])
