"""Translate a bounded Workbench graph to actual Haystack pipeline construction."""

from typing import Any
from uuid import uuid4

from apps.workbench.validator.registry import CAPABILITY_VERSION, REGISTRY, create_component, parameter_error
from apps.workbench.validator.schemas import ValidationRequest
from haystack import Pipeline
from haystack.core.errors import PipelineConnectError
from haystack.document_stores.in_memory import InMemoryDocumentStore


def _issue(code: str, message: str, **location: str) -> dict[str, str]:
    return {"code": code, "message": message, **location}


def validate_graph(request: ValidationRequest) -> dict[str, Any]:
    """Validate construction; explicit runtime inputs are never executed."""
    issues: list[dict[str, str]] = []
    unsupported = False
    for node in request.graph.nodes:
        mapping = REGISTRY.get(node.data.kind)
        if mapping is None:
            unsupported = True
            issues.append(_issue("UNKNOWN_COMPONENT_KIND", "Unknown component kind.", nodeId=node.id))
            continue
        problem = parameter_error(node.data.kind, node.data.parameters, complete=request.mode == "complete")
        if problem:
            field, message = problem
            issues.append(_issue("INVALID_PARAMETER", message, nodeId=node.id, field=field))
        if mapping.component is None:
            unsupported = True
            issues.append(_issue("UNSUPPORTED_COMPONENT", mapping.reason or "Unsupported component.", nodeId=node.id))
    if not request.graph.nodes:
        issues.append(_issue("EMPTY_GRAPH", "Add a component before validating."))
    if issues:
        return _response(request, "unsupported" if unsupported else "invalid", issues)

    pipeline = Pipeline()
    stores: list[InMemoryDocumentStore] = []
    names = {node.id: f"n_{index}" for index, node in enumerate(request.graph.nodes)}
    by_id = {node.id: node for node in request.graph.nodes}
    try:
        for node in request.graph.nodes:
            try:
                instance = create_component(node.data.kind, node.data.parameters, stores)
                pipeline.add_component(name=names[node.id], instance=instance)
            except ImportError:
                issues.append(
                    _issue(
                        "UNSUPPORTED_COMPONENT",
                        "An approved optional constructor dependency is unavailable.",
                        nodeId=node.id,
                    )
                )
                return _response(request, "unsupported", issues)
            except (ValueError, TypeError):
                issues.append(
                    _issue("INVALID_PARAMETER", "Haystack rejected the component configuration.", nodeId=node.id)
                )
        if issues:
            return _response(request, "invalid", issues)
        for edge in request.graph.edges:
            source = REGISTRY[by_id[edge.source].data.kind]
            target = REGISTRY[by_id[edge.target].data.kind]
            output_socket = source.outputs.get(edge.sourceHandle)
            input_socket = target.inputs.get(edge.targetHandle)
            if not output_socket or not input_socket:
                issues.append(
                    _issue(
                        "INVALID_PORT",
                        "This handle has no approved Haystack socket mapping.",
                        edgeId=edge.id,
                        nodeId=edge.target,
                    )
                )
                continue
            try:
                pipeline.connect(
                    sender=f"{names[edge.source]}.{output_socket}", receiver=f"{names[edge.target]}.{input_socket}"
                )
            except (PipelineConnectError, ValueError, TypeError):
                issues.append(
                    _issue(
                        "INCOMPATIBLE_SOCKET",
                        "Haystack rejected this connection's sockets or multiplicity.",
                        edgeId=edge.id,
                        nodeId=edge.target,
                    )
                )
        if issues:
            return _response(request, "invalid", issues)
        issues.extend(_validate_inputs(pipeline, request, names))
        return _response(request, "invalid" if issues else "valid", issues)
    finally:
        for store in stores:
            store.shutdown()


def _response(request: ValidationRequest, status: str, issues: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "status": status,
        "issues": issues,
        "requestId": request.requestId or str(uuid4()),
        "validator": "haystack",
        "capabilityVersion": CAPABILITY_VERSION,
        "mode": request.mode,
    }


def _validate_inputs(pipeline: Pipeline, request: ValidationRequest, names: dict[str, str]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    actual_inputs: dict[str, Any] = {}
    if request.inputs is not None:
        for node_id, values in request.inputs.items():
            if node_id not in names:
                issues.append(_issue("INVALID_RUNTIME_INPUT", "Runtime input references an unknown node."))
            else:
                actual_inputs[names[node_id]] = values
        if not issues:
            try:
                pipeline.validate_input(data=actual_inputs)
            except ValueError:
                issues.append(_issue("INVALID_RUNTIME_INPUT", "Haystack rejected the supplied execution input data."))
    if request.mode == "complete":
        reverse_names = {name: node_id for node_id, name in names.items()}
        for name, sockets in pipeline.inputs().items():
            for socket, description in sockets.items():
                if description["is_mandatory"] and socket not in actual_inputs.get(name, {}):
                    issues.append(
                        _issue(
                            "MISSING_REQUIRED_INPUT",
                            "A mandatory Haystack execution input was not supplied or connected.",
                            nodeId=reverse_names[name],
                            field=socket,
                        )
                    )
    return issues
