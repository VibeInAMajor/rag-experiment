"""Optional loopback operator endpoints for catalog, run history, and future defaults."""

import asyncio
from collections.abc import Callable
from typing import Annotated, Any, ParamSpec, TypeVar

from fastapi import FastAPI, Query, Request
from starlette.responses import JSONResponse

from apps.workbench.agents.journal import AgentOperationsFailure
from apps.workbench.agents.operations import AgentOperations
from apps.workbench.api.boundary import error_response, request_meta
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.contracts.schemas import (
    AgentCatalogResponse,
    AgentKey,
    AgentRunDetail,
    AgentRunId,
    AgentRunPage,
    AgentRunStatus,
    AgentScope,
    AgentSelectionRequest,
    AgentSelectionResponse,
    ErrorResponse,
    Identifier,
)

_P = ParamSpec("_P")
_T = TypeVar("_T")
_ROOT = "/api/v1/agents"
_SCOPE: AgentScope = "local-operator"
_CURSOR = Annotated[str, Query(min_length=1, max_length=1024, pattern=r"^[A-Za-z0-9_-]+$")]
_ERRORS = {
    "AGENT_OPERATIONS_UNAVAILABLE": "The local agent catalog is unavailable.",
    "AGENT_HISTORY_UNAVAILABLE": "The local agent history is unavailable.",
    "AGENT_HISTORY_LIMIT": "The local agent history reached its retention limit.",
    "AGENT_RUN_NOT_FOUND": "The agent run is unavailable in this history.",
    "AGENT_RUN_UNAVAILABLE": "The stored agent run could not be validated.",
    "AGENT_NOT_FOUND": "The configured agent was not found.",
    "AGENT_SELECTION_BUSY": "Another local selection update is in progress.",
    "AGENT_SELECTION_UNAVAILABLE": "The local agent selection is unavailable.",
    "AGENT_SELECTION_CONFLICT": "The selected profile changed. Reload before trying again.",
    "AGENT_PROFILE_INELIGIBLE": "This profile cannot be selected for future runs.",
    "INVALID_AGENT_CURSOR": "The history cursor is invalid for this view. Reload to continue.",
    "FORBIDDEN": "Use the local Workbench application for agent selection.",
}


def _error(request: Request, failure: AgentOperationsFailure) -> JSONResponse:
    return error_response(
        request_meta(request),
        status=failure.status,
        code=failure.code,
        message=_ERRORS[failure.code],
        retryable=failure.status == 503,
    )


class _AgentRoutes:
    def __init__(self, root: str | None) -> None:
        self._operations = AgentOperations(root)
        self._workers = asyncio.Semaphore(2)

    async def _work(self, operation: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> _T:
        async with self._workers:
            work = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
            try:
                return await asyncio.shield(work)
            except asyncio.CancelledError:
                await work
                raise

    async def catalog(self, request: Request) -> AgentCatalogResponse | JSONResponse:
        try:
            agents, history_available = await self._work(self._operations.catalog)
        except AgentOperationsFailure as failure:
            return _error(request, failure)
        return AgentCatalogResponse(
            **request_meta(request).model_dump(), scope=_SCOPE, agents=agents, history_available=history_available
        )

    async def runs(
        self,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        cursor: _CURSOR | None = None,
        agent_id: Identifier | None = None,
        status: AgentRunStatus | None = None,
        model: AgentKey | None = None,
    ) -> AgentRunPage | JSONResponse:
        try:
            items, next_cursor = await self._work(
                self._operations.runs, limit=limit, cursor=cursor, agent_id=agent_id, status=status, model=model
            )
        except AgentOperationsFailure as failure:
            return _error(request, failure)
        return AgentRunPage(**request_meta(request).model_dump(), scope=_SCOPE, runs=items, next_cursor=next_cursor)

    async def run(
        self,
        request: Request,
        run_id: AgentRunId,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        cursor: _CURSOR | None = None,
    ) -> AgentRunDetail | JSONResponse:
        try:
            item, events, next_cursor, has_more = await self._work(
                self._operations.run, run_id, limit=limit, cursor=cursor
            )
        except AgentOperationsFailure as failure:
            return _error(request, failure)
        return AgentRunDetail(
            **request_meta(request).model_dump(),
            scope=_SCOPE,
            run=item,
            events=events,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def select(
        self, request: Request, agent_id: Identifier, body: AgentSelectionRequest
    ) -> AgentSelectionResponse | JSONResponse:
        if request.headers.getlist("x-workbench-request") != ["agent-operations"]:
            return _error(request, AgentOperationsFailure("FORBIDDEN", 403))
        try:
            selection = await self._work(self._operations.select, agent_id, body)
        except AgentOperationsFailure as failure:
            return _error(request, failure)
        return AgentSelectionResponse(
            **request_meta(request).model_dump(), scope=_SCOPE, agent_id=agent_id, selection=selection
        )


def register_agent_routes(app: FastAPI, *, settings: ApiSettings) -> None:
    """Register the versioned operations contract even when its optional data are unavailable."""
    routes = _AgentRoutes(settings.agent_operations_directory)
    app.add_api_route(_ROOT, routes.catalog, response_model=AgentCatalogResponse, name="agent_catalog")
    app.add_api_route(_ROOT + "/runs", routes.runs, response_model=AgentRunPage, name="agent_runs")
    app.add_api_route(_ROOT + "/runs/{run_id}", routes.run, response_model=AgentRunDetail, name="agent_run_detail")
    errors: dict[int | str, dict[str, Any]] = {status: {"model": ErrorResponse} for status in (409, 413, 415, 504)}
    app.add_api_route(
        _ROOT + "/{agent_id}/selection",
        routes.select,
        methods=["PUT"],
        response_model=AgentSelectionResponse,
        responses=errors,
        name="agent_profile_selection",
    )
