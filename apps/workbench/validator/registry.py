"""Reviewed constructor and handle bindings, independent of UI display labels."""

from dataclasses import dataclass
from typing import Any

from haystack.components.embedders import OpenAIDocumentEmbedder, OpenAITextEmbedder
from haystack.components.joiners import DocumentJoiner
from haystack.components.preprocessors import DocumentSplitter
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.document_stores.in_memory import InMemoryDocumentStore

CAPABILITY_VERSION = "workbench-components-v1"


@dataclass(frozen=True)
class ComponentMapping:
    """A fixed supported component binding or an explicit unsupported reason."""

    component: str | None
    inputs: dict[str, str]
    outputs: dict[str, str]
    required_parameters: tuple[str, ...]
    parameter_names: tuple[str, ...]
    reason: str | None = None


REGISTRY: dict[str, ComponentMapping] = {
    "files": ComponentMapping(None, {}, {}, ("source",), ("source",), "Workspace file source is UI-only."),
    "query": ComponentMapping(None, {}, {}, ("query",), ("query",), "Pipeline input is a UI-only source node."),
    "results": ComponentMapping(None, {}, {}, ("limit",), ("limit",), "Results projection is UI-only."),
    "keyword-search": ComponentMapping(
        None,
        {},
        {},
        ("topK",),
        ("topK",),
        "Keyword search uses the approved Live API profile; constructor validation is unsupported.",
    ),
    "parser": ComponentMapping(
        None, {}, {}, (), ("format",), "Docling integration is not an approved installed validation dependency."
    ),
    "writer": ComponentMapping(
        None, {}, {}, ("collection",), ("collection",), "Persistent knowledge-base binding is not implemented."
    ),
    "vector": ComponentMapping(
        None,
        {},
        {},
        ("collection", "topK"),
        ("collection", "topK"),
        "Pgvector integration and store binding are not approved for constructor-only validation.",
    ),
    "chunker": ComponentMapping(
        "DocumentSplitter",
        {"documents": "documents"},
        {"documents": "documents"},
        ("size", "overlap"),
        ("size", "overlap"),
    ),
    "bm25": ComponentMapping(
        "InMemoryBM25Retriever",
        {"query": "query"},
        {"documents": "documents"},
        ("collection", "topK"),
        ("collection", "topK"),
    ),
    "joiner": ComponentMapping(
        "DocumentJoiner", {"documents": "documents"}, {"documents": "documents"}, ("topK",), ("topK",)
    ),
    "text-embedder": ComponentMapping(
        "OpenAITextEmbedder", {"text": "text"}, {"embedding": "embedding"}, (), ("model",)
    ),
    "document-embedder": ComponentMapping(
        "OpenAIDocumentEmbedder",
        {"documents": "documents"},
        {"documents": "documents"},
        ("batchSize",),
        ("model", "batchSize"),
    ),
}


def parameter_error(kind: str, parameters: dict[str, str | int], *, complete: bool) -> tuple[str, str] | None:
    """Validate the supported constructor projection, never socket compatibility."""
    mapping = REGISTRY[kind]
    for key in parameters:
        if key not in mapping.parameter_names:
            return key, "Unsupported constructor parameter."
    if complete:
        for key in mapping.required_parameters:
            value = parameters.get(key)
            if value is None or isinstance(value, str) and not value.strip():
                return key, "A required component parameter is missing."
    for key, value in parameters.items():
        problem = _parameter_value_error(key, value)
        if problem:
            return key, problem
    return None


def _parameter_value_error(key: str, value: str | int) -> str | None:
    if key in {"size", "overlap", "batchSize", "topK", "limit"}:
        if not isinstance(value, int) or isinstance(value, bool) or value < (0 if key == "overlap" else 1):
            return "Expected an integer in the supported range."
        if key == "batchSize" and value > 16:
            return "Batch size must be at most 16."
    elif not isinstance(value, str) or len(value) > 20000:
        return "Expected a bounded text parameter."
    if key == "model" and value != "Qwen3-Embedding-4B":
        return "Unknown embedding profile."
    if key == "format" and value not in {"Markdown", "Structured chunks"}:
        return "Unknown parser output format."
    return None


def create_component(kind: str, parameters: dict[str, str | int], stores: list[InMemoryDocumentStore]) -> Any:
    """Construct an approved real component without warming or executing it."""
    if kind == "chunker":
        return DocumentSplitter(
            split_by="token",
            split_length=int(parameters.get("size", 500)),
            split_overlap=int(parameters.get("overlap", 50)),
        )
    if kind == "bm25":
        store = InMemoryDocumentStore(shared=False)
        stores.append(store)
        return InMemoryBM25Retriever(document_store=store, top_k=int(parameters.get("topK", 20)))
    if kind == "joiner":
        return DocumentJoiner(join_mode="reciprocal_rank_fusion", top_k=int(parameters.get("topK", 8)))
    if kind == "text-embedder":
        return OpenAITextEmbedder(model="Qwen3-Embedding-4B")
    if kind == "document-embedder":
        return OpenAIDocumentEmbedder(
            model="Qwen3-Embedding-4B",
            batch_size=int(parameters.get("batchSize", 16)),
            progress_bar=False,
            raise_on_failure=True,
        )
    raise ValueError("Unsupported component")
