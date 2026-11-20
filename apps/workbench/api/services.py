"""Neutral readiness seam; no backend is enabled by the bootstrap."""

from typing import Protocol

from pydantic import Field

from apps.workbench.api.contracts import ContractModel, ExecutionProfile


class ReadinessSnapshot(ContractModel):
    profiles: list[ExecutionProfile] = Field(default_factory=list, max_length=1)


class ReadinessProbe(Protocol):
    async def snapshot(self) -> ReadinessSnapshot:
        """Return only currently approved and executable profiles."""
        ...


class UnconfiguredReadiness:
    async def snapshot(self) -> ReadinessSnapshot:
        """Keep execution unavailable until a real provider is composed."""
        return ReadinessSnapshot()
