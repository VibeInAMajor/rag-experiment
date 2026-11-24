"""Neutral storage double shared by API readiness and lifecycle tests."""

from typing import Any

import pytest

from apps.workbench.contracts.schemas import ExecutionProfile
from apps.workbench.persistence.models import (
    CorpusSnapshot,
    PersistenceError,
    PersistencePort,
    PersistenceReady,
    WorkspaceContext,
)
from apps.workbench.retrieval.profile_registry import ProfileRollout
from apps.workbench.retrieval.services import LexicalServicePort, ReadinessSnapshot


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

    async def ingestion_ready(self, _context: WorkspaceContext) -> bool:
        return False

    async def recover_ingestions(self, _context: WorkspaceContext) -> int:
        return 0

    async def _unexpected(self, *_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Discovery must not invoke corpus data operations")

    def _unexpected_reservation(self, *_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Discovery must not reserve an ingestion job")

    async def corpus_snapshot(self, _context: WorkspaceContext) -> CorpusSnapshot:
        return CorpusSnapshot(corpus_revision="empty-test-corpus", documents=[], chunk_count=0, content_bytes=0)

    async def corpus_summary(self, context: WorkspaceContext) -> CorpusSnapshot:
        return await self.corpus_snapshot(context)

    async def get_profile_rollouts(self, _context: WorkspaceContext) -> tuple[ProfileRollout, ...]:
        return ()

    create_workspace = _unexpected
    current_index_generation = _unexpected
    list_workspaces = _unexpected
    list_sources = _unexpected
    get_chunk = _unexpected
    get_local_original = _unexpected
    register_local_original = _unexpected
    publish_source = _unexpected
    lexical_search = _unexpected
    lexical_search_snapshot = _unexpected
    vector_search = _unexpected
    vector_search_snapshot = _unexpected
    reserve_ingestion = _unexpected_reservation
    transition_ingestion = _unexpected
    complete_ingestion_with_publication = _unexpected
    fail_ingestion = _unexpected
    get_ingestion_job = _unexpected
    get_source_detail = _unexpected
    list_active_chunks = _unexpected


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
