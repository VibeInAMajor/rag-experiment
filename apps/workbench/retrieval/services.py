"""Neutral readiness seam; no backend is enabled by the bootstrap."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from pydantic import Field

from apps.workbench.contracts.schemas import ContractModel, ExecutionProfile
from apps.workbench.persistence.models import CorpusSnapshot, LexicalSearchSnapshot, Workspace, WorkspaceContext
from apps.workbench.retrieval.profile_registry import ProfileRegistry
from apps.workbench.retrieval.profiles import resolve_profile

if TYPE_CHECKING:
    from apps.workbench.retrieval.dense import DenseSearchResult, DenseService


class ReadinessSnapshot(ContractModel):
    profiles: list[ExecutionProfile] = Field(default_factory=list, max_length=32)


class ReadinessProbe(Protocol):
    async def snapshot(self) -> ReadinessSnapshot:
        """Return only currently approved and executable profiles."""
        ...


class UnconfiguredReadiness:
    async def snapshot(self) -> ReadinessSnapshot:
        """Keep execution unavailable until a real provider is composed."""
        return ReadinessSnapshot()


class LexicalServicePort(Protocol):
    async def snapshot(self, context: WorkspaceContext) -> ReadinessSnapshot:
        """Advertise only the qualified, currently executable PostgreSQL profile."""
        ...

    async def documents(self, context: WorkspaceContext) -> CorpusSnapshot:
        """Read authoritative document metadata and its consistent corpus revision."""
        ...

    async def workspaces(self, context: WorkspaceContext) -> list[Workspace]:
        """List only workspaces authorized by the server-resolved context."""
        ...

    async def search(
        self, context: WorkspaceContext, *, query: str, top_k: int, profile_id: str, expected_profile_revision: str
    ) -> LexicalSearchSnapshot | DenseSearchResult:
        """Execute the approved pipeline and propagate cancellation to owned SQL work."""
        ...


class RetrievalService:
    """Dispatch only reviewed static compositions while retaining lexical document ownership."""

    def __init__(self, lexical: LexicalServicePort, *, dense: DenseService, registry: ProfileRegistry) -> None:
        self._lexical, self._dense = lexical, dense
        self._registry = registry

    async def snapshot(self, context: WorkspaceContext) -> ReadinessSnapshot:
        """Keep lexical discovery available when dense dependencies refuse qualification."""
        lexical, dense = await asyncio.gather(self._lexical.snapshot(context), self._dense_snapshot(context))
        return ReadinessSnapshot(profiles=[*lexical.profiles, *dense.profiles])

    async def _dense_snapshot(self, context: WorkspaceContext) -> ReadinessSnapshot:
        try:
            # Dense checks must finish inside the API's shared one-second discovery budget.
            async with asyncio.timeout(0.5):
                return await self._dense.snapshot(context)
        except TimeoutError:
            return ReadinessSnapshot()

    async def documents(self, context: WorkspaceContext) -> CorpusSnapshot:
        """Reuse the existing source metadata projection."""
        return await self._lexical.documents(context)

    async def workspaces(self, context: WorkspaceContext) -> list[Workspace]:
        """Reuse existing authorized workspace discovery."""
        return await self._lexical.workspaces(context)

    async def search(
        self, context: WorkspaceContext, *, query: str, top_k: int, profile_id: str, expected_profile_revision: str
    ) -> LexicalSearchSnapshot | DenseSearchResult:
        """Select an allowlisted service; neither requests nor graphs instantiate components."""
        definition = resolve_profile(
            self._registry,
            profile_id=profile_id,
            profile_revision=expected_profile_revision,
            workspace_id=context.workspace_id,
        )
        service = self._dense if definition.composition == "exact_dense" else self._lexical
        return await service.search(
            context,
            query=query,
            top_k=top_k,
            profile_id=profile_id,
            expected_profile_revision=expected_profile_revision,
        )
