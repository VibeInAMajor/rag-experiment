"""Neutral readiness seam; no backend is enabled by the bootstrap."""

from typing import Protocol

from pydantic import Field

from apps.workbench.contracts.schemas import ContractModel, ExecutionProfile
from apps.workbench.persistence.models import CorpusSnapshot, LexicalSearchSnapshot, Workspace, WorkspaceContext


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
    ) -> LexicalSearchSnapshot:
        """Execute the approved pipeline and propagate cancellation to owned SQL work."""
        ...
