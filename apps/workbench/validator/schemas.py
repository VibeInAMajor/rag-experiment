"""Bounded editor graph input; executable serialization is never accepted."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, StrictStr, model_validator

_Text = Annotated[StrictStr, Field(min_length=1, max_length=200)]
_Coordinate = Annotated[float, Field(ge=-100000, le=100000, allow_inf_nan=False)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Position(_StrictModel):
    x: _Coordinate
    y: _Coordinate


class Viewport(Position):
    zoom: Annotated[float, Field(ge=0.1, le=4, allow_inf_nan=False)]


class NodeData(_StrictModel):
    kind: _Text
    label: _Text
    parameters: dict[str, StrictStr | StrictInt]
    status: Literal["idle", "running", "success", "error"] = "idle"


class Node(_StrictModel):
    id: _Text
    type: Literal["workbench"] = "workbench"
    position: Position
    data: NodeData


class Edge(_StrictModel):
    id: _Text
    source: _Text
    target: _Text
    sourceHandle: _Text
    targetHandle: _Text
    type: Literal["smoothstep"] = "smoothstep"


class Graph(_StrictModel):
    nodes: Annotated[list[Node], Field(max_length=100)]
    edges: Annotated[list[Edge], Field(max_length=300)]
    viewport: Viewport | None = None

    @model_validator(mode="after")
    def unique_identifiers(self) -> "Graph":
        """Reject ambiguous identities before any component is constructed."""
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes) or len({edge.id for edge in self.edges}) != len(self.edges):
            raise ValueError("Graph identifiers must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges):
            raise ValueError("Connections must reference existing nodes")
        return self


class ValidationRequest(_StrictModel):
    schemaVersion: Literal[1]
    graph: Graph
    requestId: _Text | None = None
    mode: Literal["draft", "complete"] = "complete"
    inputs: dict[str, dict[str, JsonValue]] | None = None

    @model_validator(mode="before")
    @classmethod
    def deny_executable_keys(cls, value: object) -> object:
        """Block executable/object-prototype fields throughout untrusted JSON."""
        if isinstance(value, dict) and type(value.get("schemaVersion")) is not int:
            raise ValueError("schemaVersion must be an integer")
        stack = [value]
        visited = 0
        while stack:
            item = stack.pop()
            visited += 1
            if visited > 50000:
                raise ValueError("Payload is too complex")
            if isinstance(item, dict):
                if any(
                    key in {"__proto__", "prototype", "constructor", "module", "class_path", "callable"} for key in item
                ):
                    raise ValueError("Executable fields are not supported")
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        return value
