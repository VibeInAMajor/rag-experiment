"""Neutral storage double shared by API readiness and lifecycle tests."""

from typing import Any

import pytest

from apps.workbench.api.contracts import ExecutionProfile
from apps.workbench.api.persistence import (
    CorpusSnapshot,
    PersistenceError,
    PersistencePort,
    PersistenceReady,
    WorkspaceContext,
)
from apps.workbench.api.services import LexicalServicePort, ReadinessSnapshot


class _DatabaseProbe(PersistencePort):
    def __init__(self) -> None:
        self.started = 0
        self.closed = 0
        self.failure: PersistenceError | None = None

    async def start(self) -> None:
        self.started += 1

    async def close(self) -> None:
        self.closed += 1

    async def readiness(self, context: WorkspaceContext) -> PersistenceReady:
        assert context.workspace_id == "development"
        if self.failure:
            raise self.failure
        return PersistenceReady(schema_revision="0001", workspace_id="development", source_count=8, chunk_count=8)

    async def _unexpected(self, *_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Discovery must not invoke corpus data operations")

    async def corpus_snapshot(self, _context: WorkspaceContext) -> CorpusSnapshot:
        return CorpusSnapshot(corpus_revision="empty-test-corpus", documents=[], chunk_count=0, content_bytes=0)

    create_workspace = _unexpected
    list_workspaces = _unexpected
    list_sources = _unexpected
    get_chunk = _unexpected
    publish_source = _unexpected
    lexical_search = _unexpected
    lexical_search_snapshot = _unexpected
    vector_search = _unexpected


class _QualifiedLexical(LexicalServicePort):
    async def snapshot(self, _context: WorkspaceContext) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            profiles=[
                ExecutionProfile(
                    profile_id="postgres-fts-baseline",
                    profile_revision="qualified-test-revision",
                    workspace_ids=["development"],
                    corpus_id="test-corpus",
                    score_type="postgres_ts_rank_cd",
                )
            ]
        )

    async def _unexpected(self, *_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Discovery must not execute the qualified service test double")

    workspaces = _unexpected
    documents = _unexpected
    search = _unexpected
