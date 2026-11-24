"""Provider-neutral persistence validation without a database or inference service."""

from typing import Any

import pytest
from pydantic import ValidationError

from apps.workbench.contracts.schemas import ExecutionProfile
from apps.workbench.persistence.models import Chunk, WorkspaceNotFound, resolve_development_workspace


def _chunk(**overrides: Any) -> Chunk:
    return Chunk.model_validate(
        {
            "workspace_id": "development",
            "source_id": "source-a",
            "version_id": "version-a",
            "chunk_id": "chunk-a",
            "title": "Safe source",
            "content": "A persisted passage.",
            "content_hash": "known-hash",
            **overrides,
        }
    )


def test_lexical_chunk_requires_no_embedding() -> None:
    """Missing dense data is a valid lexical-only record, not a provider failure."""
    chunk = _chunk()
    assert chunk.embedding is None
    assert chunk.dimensions is None
    assert chunk.embedding_profile_id is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"embedding": []},
        {"embedding": [float("nan")], "dimensions": 1, "embedding_profile_id": "synthetic"},
        {"embedding": [float("inf")], "dimensions": 1, "embedding_profile_id": "synthetic"},
        {"embedding": [1.0], "dimensions": 2, "embedding_profile_id": "synthetic"},
        {"embedding": [1.0], "dimensions": 1},
        {"embedding_profile_id": "synthetic"},
        {"dimensions": 2560},
        {"dimensions": True},
        {"workspace_id": "../another-workspace"},
        {"page": 0},
    ],
)
def test_malformed_embeddings_and_identities_are_rejected(overrides: dict[str, Any]) -> None:
    """Storage records cannot silently truncate vectors or invent ownership/profile metadata."""
    with pytest.raises(ValidationError):
        _chunk(**overrides)


def test_explicit_synthetic_vector_preserves_its_entire_dimension() -> None:
    """A synthetic vector proves record shape only and makes no inference claim."""
    embedding = [1.0] + [0.0] * 2559
    chunk = _chunk(embedding=embedding, dimensions=2560, embedding_profile_id="synthetic-test-only")
    assert chunk.embedding == embedding
    assert chunk.dimensions == 2560


def test_development_workspace_resolution_refuses_caller_selected_scope() -> None:
    """The local resolver cannot grant access to a foreign workspace identifier."""
    context = resolve_development_workspace()
    assert context.workspace_id == "development"
    with pytest.raises(WorkspaceNotFound):
        resolve_development_workspace("other-owner")
    with pytest.raises(ValidationError):
        context.workspace_id = "other-owner"


@pytest.mark.parametrize(
    ("profile_id", "score_type"), [("bm25-v1", "bm25_raw"), ("postgres-keyword-v1", "postgres_ts_rank_cd")]
)
def test_execution_profile_preserves_truthful_lexical_score_semantics(profile_id: str, score_type: str) -> None:
    """Native PostgreSQL ranking and genuine BM25 remain distinct qualified profiles."""
    profile = ExecutionProfile.model_validate(
        {
            "profile_id": profile_id,
            "score_type": score_type,
            "profile_revision": "test-revision",
            "workspace_ids": ["development"],
            "corpus_id": "development",
        }
    )
    assert profile.profile_id == profile_id
    assert profile.score_type == score_type


@pytest.mark.parametrize(
    ("profile_id", "score_type"), [("bm25-v1", "postgres_ts_rank_cd"), ("postgres-keyword-v1", "bm25_raw")]
)
def test_execution_profile_rejects_relabeling_postgres_rank_as_bm25(profile_id: str, score_type: str) -> None:
    """Matching DTO shapes cannot silently change a ranking algorithm's meaning."""
    with pytest.raises(ValidationError):
        ExecutionProfile.model_validate(
            {
                "profile_id": profile_id,
                "score_type": score_type,
                "profile_revision": "test-revision",
                "workspace_ids": ["development"],
                "corpus_id": "development",
            }
        )
