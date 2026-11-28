"""Project the local caller's metadata without invoking or importing an agent runtime."""

import hashlib
import hmac
import json
from base64 import b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from secrets import token_bytes
from uuid import uuid4

from apps.workbench.agents.journal import AgentJournal, AgentOperationsFailure, SelectionFile
from apps.workbench.contracts.schemas import (
    AgentCall,
    AgentCoverage,
    AgentDefinition,
    AgentEvent,
    AgentItem,
    AgentProfileDefinition,
    AgentProfileItem,
    AgentRunIdentity,
    AgentRunItem,
    AgentRunStatus,
    AgentSelection,
    AgentSelectionRequest,
    AgentStage,
    AgentTariff,
    AgentUsage,
)

_HEARTBEAT_GRACE = timedelta(minutes=5)
_HISTORY_AGE = timedelta(days=30)
_HISTORY_TERMINAL_LIMIT = 100
_USAGE_KEYS = (
    "input_tokens",
    "ordinary_input_tokens",
    "cached_read_tokens",
    "cached_write_tokens",
    "output_tokens",
    "reasoning_tokens",
    "total_tokens",
)
_CASE_RESULTS = {"completed", "failed", "cancelled", "interrupted", "blocked"}
_MAX_SAFE_COUNT = 2**53 - 1


def _unavailable_run() -> AgentOperationsFailure:
    return AgentOperationsFailure("AGENT_RUN_UNAVAILABLE")


def _price_verified(tariff: AgentTariff, now: datetime) -> bool:
    return (
        tariff.status == "verified"
        and tariff.source_url is not None
        and tariff.effective_at is not None
        and tariff.verified_at is not None
        and datetime.fromisoformat(tariff.effective_at) <= datetime.fromisoformat(tariff.verified_at) <= now
        and tariff.ordinary_input is not None
        and tariff.output is not None
    )


def _tariff_matches(tariff: AgentTariff, *, provider: str, model: str) -> bool:
    return tariff.provider == provider and tariff.model == model


def _capacity(profile: AgentProfileDefinition) -> tuple[object, ...]:
    return (
        profile.max_estimated_input_tokens,
        profile.max_output_tokens,
        profile.max_request_bytes,
        profile.max_response_bytes,
        profile.timeout_seconds,
        profile.reasoning_effort,
        profile.cache_mode,
        profile.cache_ttl_seconds,
    )


def _selectable(agent: AgentDefinition, profile: AgentProfileDefinition, now: datetime) -> bool:
    qualification = profile.qualification
    tariff = profile.tariff
    baseline = next(item for item in agent.profiles if item.profile_id == agent.default_profile_id)
    return (
        qualification.state == "qualified"
        and qualification.reason in {"historical_pass", "joint_pass"}
        and qualification.revision is not None
        and qualification.verified_at is not None
        and datetime.fromisoformat(qualification.verified_at) <= now
        and (
            profile.profile_id == agent.default_profile_id
            or qualification.reason == "joint_pass"
            and qualification.revision == baseline.qualification.revision
        )
        and set(agent.modes).issubset(profile.modes)
        and _capacity(profile) == _capacity(baseline)
        and tariff is not None
        and _tariff_matches(tariff, provider=profile.provider, model=profile.model)
        and _price_verified(tariff, now)
        and (
            profile.cache_mode != "explicit"
            or tariff.cache_ttl_seconds == profile.cache_ttl_seconds
            and tariff.cached_read is not None
            and tariff.cached_write is not None
        )
    )


def _selection(agent: AgentDefinition, current: SelectionFile) -> AgentSelection:
    existing = current.selections.get(agent.agent_id)
    if existing is not None:
        return existing
    identity = json.dumps(agent.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    revision = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return AgentSelection(profile_id=agent.default_profile_id, revision=f"catalog-{revision}")


def _valid_usage(usage: AgentUsage | None) -> AgentUsage | None:
    if usage is None:
        return None
    ordinary, cached_read, cached_write = (
        usage.ordinary_input_tokens,
        usage.cached_read_tokens,
        usage.cached_write_tokens,
    )
    counted = sum(count for count in (ordinary, cached_read, cached_write) if count is not None)
    if usage.input_tokens is not None and (
        counted > usage.input_tokens
        or None not in (ordinary, cached_read, cached_write)
        and counted != usage.input_tokens
    ):
        ordinary, cached_read, cached_write = None, None, None
    reasoning = usage.reasoning_tokens
    if usage.output_tokens is None or reasoning is not None and reasoning > usage.output_tokens:
        reasoning = None
    total = (
        usage.input_tokens + usage.output_tokens
        if (usage.input_tokens is not None and usage.output_tokens is not None)
        else None
    )
    return AgentUsage(
        input_tokens=usage.input_tokens,
        ordinary_input_tokens=ordinary,
        cached_read_tokens=cached_read,
        cached_write_tokens=cached_write,
        output_tokens=usage.output_tokens,
        reasoning_tokens=reasoning,
        total_tokens=total if total is not None and total <= _MAX_SAFE_COUNT else None,
    )


def _amount(values: list[str | None], *, complete: bool = False) -> str | None:
    amounts = [Decimal(value) for value in values if value is not None]
    if not amounts or complete and len(amounts) != len(values):
        return None
    with localcontext() as context:
        context.prec = 48
        total = sum(amounts, start=Decimal(0))
    return format(total, "f") if total.adjusted() < 18 else None


def _call_evidence(event: AgentEvent, run: AgentRunIdentity) -> AgentEvent:
    call = event.call
    if call is None or event.kind != "call_completed":
        return event
    match = call.actual_model in {run.model, None}
    chargeable = call.requests == 1 and call.actual_model == run.model
    safe = call.model_copy(
        update={
            "usage": _valid_usage(call.usage) if call.requests == 1 else None,
            "estimated_cost_usd": call.estimated_cost_usd if chargeable else None,
        }
    )
    return event.model_copy(update={"call": safe, "reason": event.reason or (None if match else "MODEL_MISMATCH")})


@dataclass
class _RunState:
    identity: AgentRunIdentity
    pending: dict[str, AgentCall]
    terminal_calls: dict[str, AgentEvent]
    cases: dict[str, str]
    reused: set[str]
    status: AgentRunStatus = "queued"
    stage: AgentStage = "queued"
    started_at: str | None = None
    finished_at: str | None = None

    def _call(self, event: AgentEvent) -> None:
        call = event.call
        if call is None:
            raise _unavailable_run()
        terminal = self.terminal_calls.get(call.call_id)
        waiting = self.pending.get(call.call_id)
        if terminal is not None:
            if event.kind == "call_completed" and (terminal.call, terminal.status, terminal.reason) == (
                call,
                event.status,
                event.reason,
            ):
                return
            raise _unavailable_run()
        if waiting is not None and (waiting.case_id, waiting.mode) != (call.case_id, call.mode):
            raise _unavailable_run()
        if event.kind == "call_pending":
            if waiting is not None and call != waiting:
                raise _unavailable_run()
            self.pending[call.call_id] = call
            return
        self.terminal_calls[call.call_id] = event
        self.pending.pop(call.call_id, None)

    def _case(self, event: AgentEvent) -> None:
        key = event.case_id or f"{event.sequence}"
        status = event.status or "completed"
        if status not in _CASE_RESULTS or key in self.cases and self.cases[key] != status:
            raise _unavailable_run()
        self.cases[key] = status
        if event.kind == "checkpoint_reused":
            self.reused.add(key)

    def apply(self, event: AgentEvent) -> AgentEvent:
        """Apply a validated event in sequence, preserving terminal identities."""
        if self.finished_at is not None or event.kind == "run_queued":
            raise _unavailable_run()
        if event.kind == "run_started":
            if self.started_at is not None:
                raise _unavailable_run()
            self.started_at = event.timestamp
            self.status = "running"
        elif event.kind == "run_finished" and event.status is not None:
            self.finished_at = event.timestamp
            self.status = event.status
        elif event.kind in {"case_completed", "checkpoint_reused"}:
            self._case(event)
        elif event.kind in {"call_pending", "call_completed"}:
            event = _call_evidence(event, self.identity)
            self._call(event)
        if event.stage is not None:
            self.stage = event.stage
        return event


@dataclass(frozen=True)
class _RunProjection:
    item: AgentRunItem
    events: tuple[AgentEvent, ...]


def _run_usage(calls: list[AgentCall]) -> AgentUsage:
    totals = dict.fromkeys(_USAGE_KEYS, 0)
    observed: set[str] = set()
    for call in calls:
        if call.usage is None:
            continue
        for key, value in call.usage.model_dump().items():
            if value is not None:
                totals[key] += value
                observed.add(key)
    return AgentUsage.model_validate({key: totals[key] for key in observed if totals[key] <= _MAX_SAFE_COUNT})


def _cache_metrics(calls: list[AgentCall]) -> tuple[int, int, float | None, float | None]:
    reads = [call.usage for call in calls if call.usage is not None and call.usage.cached_read_tokens is not None]
    observed = len(reads)
    hits = sum((usage.cached_read_tokens or 0) > 0 for usage in reads)
    hit_share = round(100 * hits / observed, 2) if observed else None
    paired = [usage for usage in reads if usage.input_tokens is not None]
    input_total = sum(usage.input_tokens or 0 for usage in paired)
    read_total = sum(usage.cached_read_tokens or 0 for usage in paired)
    read_share = round(100 * read_total / input_total, 2) if input_total and len(paired) == len(calls) else None
    return observed, hits, hit_share, read_share


def _snapshot(state: _RunState, events: tuple[AgentEvent, ...]) -> AgentRunItem:
    first, last = events[0], events[-1]
    calls = [event.call for event in state.terminal_calls.values() if event.call is not None]
    physical = [call for call in calls if call.requests == 1]
    cache_observed, cache_hits, cache_hit_share, cache_read_share = _cache_metrics(physical)
    costs = [call.estimated_cost_usd for call in physical]
    pending = list(state.pending.values()) if state.finished_at is None else []
    observed = sum(
        call.usage is not None and call.usage.input_tokens is not None and call.usage.output_tokens is not None
        for call in physical
    )
    return AgentRunItem(
        **state.identity.model_dump(),
        run_id=first.run_id,
        status=state.status,
        stage=state.stage,
        queued_at=first.timestamp,
        started_at=state.started_at,
        finished_at=state.finished_at,
        last_sequence=last.sequence,
        completed_cases=len(state.cases),
        failed_cases=sum(status == "failed" for status in state.cases.values()),
        blocked_cases=sum(status == "blocked" for status in state.cases.values()),
        reused_cases=len(state.reused),
        physical_requests=len(physical),
        pending_calls=len(pending),
        cache_observed_requests=cache_observed,
        cache_hit_requests=cache_hits,
        cache_hit_percent=cache_hit_share,
        cache_read_percent=cache_read_share,
        actual_models=sorted({call.actual_model for call in physical if call.actual_model is not None}),
        usage=_run_usage(physical),
        usage_coverage=AgentCoverage(known_calls=observed, total_calls=len(physical)),
        estimated_cost_usd=_amount(costs),
        cost_coverage=AgentCoverage(known_calls=sum(cost is not None for cost in costs), total_calls=len(physical)),
        pending_reserve_usd=_amount([call.reserve_usd for call in pending], complete=True),
    )


def _project(events: tuple[AgentEvent, ...]) -> _RunProjection:
    if not events:
        raise AgentOperationsFailure("AGENT_RUN_NOT_FOUND", 404)
    first = events[0]
    identity = first.run
    if (
        identity is None
        or identity.tariff is not None
        and not _tariff_matches(identity.tariff, provider=identity.provider, model=identity.model)
    ):
        raise _unavailable_run()
    state = _RunState(
        identity=identity, pending={}, terminal_calls={}, cases={}, reused=set(), stage=first.stage or "queued"
    )
    projected = (first, *(state.apply(event) for event in events[1:]))
    return _RunProjection(item=_snapshot(state, projected), events=projected)


def _run_order(item: AgentRunItem) -> tuple[datetime, str]:
    return datetime.fromisoformat(item.queued_at), item.run_id


class _Cursor:
    def __init__(self) -> None:
        self._key = token_bytes(32)

    def encode(self, *parts: str) -> str:
        raw = json.dumps(parts, separators=(",", ":")).encode("ascii")
        digest = hmac.digest(self._key, raw, "sha256")
        return urlsafe_b64encode(digest + raw).decode("ascii").rstrip("=")

    def decode(self, token: str, *prefix: str, fields: int) -> list[str]:
        failure = AgentOperationsFailure("INVALID_AGENT_CURSOR", 400)
        try:
            raw = b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        except ValueError:
            raise failure from None
        digest, body = raw[:32], raw[32:]
        if not hmac.compare_digest(digest, hmac.digest(self._key, body, "sha256")):
            raise failure
        parts = json.loads(body)
        if parts[: len(prefix)] != list(prefix) or len(parts) != len(prefix) + fields:
            raise failure
        return [str(part) for part in parts[len(prefix) :]]


class AgentOperations:
    """Expose catalog, selection and journal projections to the local authorized operator."""

    def __init__(self, root: str | None) -> None:
        self._journal = AgentJournal(root)
        self._cursor = _Cursor()

    def _agent(self, agent_id: str) -> AgentDefinition:
        for agent in self._journal.catalog().agents:
            if agent.agent_id == agent_id:
                return agent
        raise AgentOperationsFailure("AGENT_NOT_FOUND", 404)

    def catalog(self) -> tuple[list[AgentItem], bool]:
        """Read independent agent metadata and applicable persisted selections."""
        catalog = self._journal.catalog()
        current = self._journal.selection()
        now = datetime.now(UTC)
        items = [
            AgentItem(
                **agent.model_dump(exclude={"profiles"}),
                profiles=[
                    AgentProfileItem(**profile.model_dump(), selectable=_selectable(agent, profile, now))
                    for profile in agent.profiles
                ],
                selection=_selection(agent, current),
            )
            for agent in catalog.agents
        ]
        return items, self._journal.history_available()

    def select(self, agent_id: str, change: AgentSelectionRequest) -> AgentSelection:
        """Persist only a currently eligible configured profile and matching observed revision."""

        def update(current: SelectionFile) -> SelectionFile:
            agent = self._agent(agent_id)
            selection = _selection(agent, current)
            if selection.revision != change.expected_revision:
                raise AgentOperationsFailure("AGENT_SELECTION_CONFLICT", 409)
            profile = next((item for item in agent.profiles if item.profile_id == change.profile_id), None)
            if profile is None or not _selectable(agent, profile, datetime.now(UTC)):
                raise AgentOperationsFailure("AGENT_PROFILE_INELIGIBLE", 409)
            if selection.profile_id == change.profile_id:
                return current
            saved = AgentSelection(profile_id=change.profile_id, revision=f"selection-{uuid4().hex}")
            return current.model_copy(update={"selections": {**current.selections, agent_id: saved}})

        saved = self._journal.update_selection(update)
        return saved.selections[agent_id] if agent_id in saved.selections else _selection(self._agent(agent_id), saved)

    def _run(self, run_id: str) -> _RunProjection:
        events = self._journal.events(run_id)
        projection = _project(events)
        item = projection.item
        since = datetime.now(UTC) - datetime.fromisoformat(projection.events[-1].timestamp)
        if item.status in {"queued", "running"} and since > _HEARTBEAT_GRACE:
            return _RunProjection(item=item.model_copy(update={"status": "interrupted"}), events=projection.events)
        return projection

    def _retained(self) -> list[AgentRunItem]:
        cutoff = datetime.now(UTC) - _HISTORY_AGE
        active: list[AgentRunItem] = []
        terminal: list[tuple[datetime, AgentRunItem]] = []
        for run_id in self._journal.run_ids():
            try:
                item = self._run(run_id).item
            except AgentOperationsFailure:
                continue
            if item.finished_at is None:
                active.append(item)
            elif (finished_at := datetime.fromisoformat(item.finished_at)) >= cutoff:
                terminal.append((finished_at, item))
        terminal.sort(key=lambda pair: (pair[0], pair[1].run_id), reverse=True)
        return sorted(
            [*active, *(item for _, item in terminal[:_HISTORY_TERMINAL_LIMIT])], key=_run_order, reverse=True
        )

    def runs(
        self, *, limit: int, cursor: str | None, agent_id: str | None, status: AgentRunStatus | None, model: str | None
    ) -> tuple[list[AgentRunItem], str | None]:
        """List projected runs newest first, binding the cursor to all server-side filters."""
        prefix = ("runs", "local-operator", agent_id or "", status or "", model or "")
        after = self._cursor.decode(cursor, *prefix, fields=2) if cursor is not None else None
        key = (datetime.fromisoformat(after[0]), after[1]) if after is not None else None
        items = [
            item
            for item in self._retained()
            if (agent_id is None or agent_id == item.agent_id)
            and (status is None or status == item.status)
            and (model is None or model in [item.model, *item.actual_models])
            and (key is None or _run_order(item) < key)
        ]
        page = items[:limit]
        next_cursor = self._cursor.encode(*prefix, page[-1].queued_at, page[-1].run_id) if len(items) > limit else None
        return page, next_cursor

    def run(self, run_id: str, *, limit: int, cursor: str | None) -> tuple[AgentRunItem, list[AgentEvent], str, bool]:
        """Read a run and a bounded forward page, retaining the head cursor when idle."""
        projection = self._run(run_id)
        if projection.item.finished_at is not None and not any(item.run_id == run_id for item in self._retained()):
            raise AgentOperationsFailure("AGENT_RUN_NOT_FOUND", 404)
        prefix = ("events", "local-operator", run_id, projection.item.queued_at)
        after = int(self._cursor.decode(cursor, *prefix, fields=1)[0]) if cursor is not None else 0
        if after > projection.item.last_sequence:
            raise AgentOperationsFailure("INVALID_AGENT_CURSOR", 400)
        page = list(projection.events[after : after + limit])
        next_cursor = self._cursor.encode(*prefix, str(after + len(page)))
        return projection.item, page, next_cursor, after + len(page) < len(projection.events)
