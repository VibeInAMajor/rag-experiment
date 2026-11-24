"""Compose storage lifecycle and safe dependency status without enabling search."""

from asyncio import timeout
from typing import Literal

from pydantic import SecretStr

from apps.workbench.contracts.schemas import DatabaseDependencyStatus
from apps.workbench.observability.events import log_event
from apps.workbench.persistence.models import (
    DatabaseUnavailable,
    PersistenceError,
    PersistencePort,
    SchemaIncompatible,
    WorkspaceContext,
    WorkspaceNotFound,
    resolve_development_workspace,
)


class DatabaseDependency:
    def __init__(self, persistence: PersistencePort | None) -> None:
        self.persistence = persistence
        self._active = False

    async def start(self) -> None:
        """Start the optional pool without confusing database failure with liveness."""
        self._active = True
        if self.persistence is not None:
            try:
                await self.persistence.start()
            except PersistenceError:
                log_event("database_unavailable", code="DEPENDENCY_UNAVAILABLE")

    async def close(self) -> None:
        """Release application-owned database connections."""
        self._active = False
        if self.persistence is not None:
            await self.persistence.close()

    async def snapshot(self, *, trace_id: str | None = None) -> DatabaseDependencyStatus:
        """Report certified schema and committed corpus state, without query payloads."""
        if self.persistence is None:
            return DatabaseDependencyStatus(status="unconfigured")
        if not self._active:
            return DatabaseDependencyStatus(status="unavailable")
        failure: Literal["incompatible", "empty", "unavailable"] = "unavailable"
        try:
            async with timeout(1):
                authorized = resolve_development_workspace()
                context = WorkspaceContext(workspace_id=authorized.workspace_id, trace_id=trace_id)
                current = await self.persistence.readiness(context)
            if not self._active:
                return DatabaseDependencyStatus(status="unavailable")
            return DatabaseDependencyStatus(status="ready", **current.model_dump())
        except SchemaIncompatible:
            failure = "incompatible"
        except WorkspaceNotFound:
            failure = "empty"
        except (DatabaseUnavailable, TimeoutError):
            failure = "unavailable"
        except PersistenceError:
            failure = "unavailable"
        return DatabaseDependencyStatus(status=failure)


def create_database_dependency(
    dsn: SecretStr | None,
    *,
    persistence: PersistencePort | None = None,
    snapshot_mode: Literal["persisted", "legacy"] = "persisted",
) -> DatabaseDependency:
    """Bind only the configured local infrastructure adapter at the composition edge."""
    if persistence is None and dsn is not None:
        from apps.workbench.postgres.postgres import PostgresPersistence

        persistence = PostgresPersistence(dsn.get_secret_value(), snapshot_mode=snapshot_mode)
    return DatabaseDependency(persistence)
