"""Read-only runtime profile governance and explicit administrator lifecycle commands."""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC
from typing import Any, Literal

import psycopg
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from apps.workbench.api.db_migrations import HEAD_REVISION, migration_status
from apps.workbench.api.persistence import (
    CorpusNotReady,
    IndexGeneration,
    RecordConflict,
    SchemaIncompatible,
    WorkspaceContext,
)
from apps.workbench.api.profile_registry import (
    ProfileDefinition,
    ProfileNotAvailable,
    ProfileRegistry,
    ProfileRollout,
    load_profile_registry,
)

_ROLLOUT_COLUMNS = tuple(ProfileRollout.model_fields)
_MAX_WORKSPACE_PROFILES = 64
_PROTECTION_QUERY = (
    "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
    "WHERE n.nspname='workbench' AND c.relname IN ('retrieval_profile_rollouts','profile_rollout_events') "
    "AND c.relrowsecurity AND c.relforcerowsecurity AND pg_get_userbyid(c.relowner)<>'workbench_app')=2 "
    "AND (SELECT count(*) FROM pg_trigger WHERE tgenabled IN ('O','A') AND (tgrelid,tgname) IN "
    "(('workbench.retrieval_profile_revisions'::regclass,'immutable_profile_revision'),"
    "('workbench.retrieval_profile_rollouts'::regclass,'record_profile_rollout'),"
    "('workbench.profile_rollout_events'::regclass,'immutable_profile_rollout_event'),"
    "('workbench.workspaces'::regclass,'initialize_profile_rollout')))=4 AS protected"
)
_ROLLOUT_QUERY = (
    "SELECT r.*,d.definition,e.profile_revision AS event_revision,e.policy_hash AS event_hash,"
    "e.state AS event_state,e.qualified_generation_id AS event_generation,"
    "NOT EXISTS(SELECT 1 FROM workbench.profile_rollout_events newer "
    "WHERE newer.workspace_id=r.workspace_id AND newer.profile_id=r.profile_id "
    "AND newer.rollout_version>r.rollout_version) AS latest "
    "FROM workbench.retrieval_profile_rollouts r JOIN workbench.retrieval_profile_revisions d "
    "USING(profile_id,profile_revision,policy_hash) LEFT JOIN workbench.profile_rollout_events e "
    "USING(workspace_id,profile_id,rollout_version) WHERE r.workspace_id=%s "
    f"ORDER BY r.profile_id LIMIT {_MAX_WORKSPACE_PROFILES + 1}"
)


def _rollout(row: dict[str, Any]) -> ProfileRollout:
    try:
        definition = ProfileDefinition.model_validate(row["definition"])
        if (
            definition.policy_hash != row["policy_hash"]
            or not row["latest"]
            or (row["profile_revision"], row["policy_hash"], row["state"], row["qualified_generation_id"])
            != (row["event_revision"], row["event_hash"], row["event_state"], row["event_generation"])
        ):
            raise SchemaIncompatible("Profile governance history is incompatible.")
        return ProfileRollout.model_validate({name: row[name] for name in _ROLLOUT_COLUMNS})
    except (ValidationError, KeyError):
        raise SchemaIncompatible("Profile governance history is incompatible.") from None


async def read_profile_rollouts(
    connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext
) -> tuple[ProfileRollout, ...]:
    """Read only durable selections from this workspace, verifying immutable definition and audit state."""
    protected = await (await connection.execute(_PROTECTION_QUERY)).fetchone()
    if protected != {"protected": True}:
        raise SchemaIncompatible("Profile governance protections are unavailable.")
    rows = await (await connection.execute(_ROLLOUT_QUERY, (context.workspace_id,))).fetchall()
    if len(rows) > _MAX_WORKSPACE_PROFILES:
        raise SchemaIncompatible("The workspace profile registry exceeds its bounds.")
    return tuple(_rollout(row) for row in rows)


def _require_administrator(connection: psycopg.Connection[dict[str, Any]]) -> None:
    role = connection.execute("SELECT current_user AS name").fetchone()
    if role is None or role["name"] == "workbench_app":
        raise ValueError("Profile administration requires the separate migration administrator.")


def _administrator(dsn: str) -> psycopg.Connection[dict[str, Any]]:
    schema = migration_status(dsn)
    if not schema.compatible or schema.revision != HEAD_REVISION:
        raise SchemaIncompatible("Profile administration requires the current compatible migration.")
    connection = psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5)
    try:
        _require_administrator(connection)
        connection.execute("SELECT set_config('statement_timeout','10000',true)")
        connection.execute("SELECT set_config('lock_timeout','5000',true)")
    except Exception:
        connection.close()
        raise
    return connection


def sync_registry(dsn: str, registry: ProfileRegistry) -> dict[str, int]:
    """Insert new immutable revisions; a changed existing identity refuses the entire transaction."""
    inserted = 0
    with _administrator(dsn) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(719342176214)")
        for definition in registry.profiles:
            existing = connection.execute(
                "SELECT definition,policy_hash FROM workbench.retrieval_profile_revisions "
                "WHERE profile_id=%s AND profile_revision=%s",
                (definition.profile_id, definition.profile_revision),
            ).fetchone()
            if existing is not None:
                if existing["policy_hash"] != definition.policy_hash or existing["definition"] != definition.model_dump(
                    mode="json"
                ):
                    raise RecordConflict("A profile revision already belongs to a different immutable policy.")
                continue
            connection.execute(
                "INSERT INTO workbench.retrieval_profile_revisions(profile_id,profile_revision,definition,policy_hash) "
                "VALUES(%s,%s,%s,%s)",
                (
                    definition.profile_id,
                    definition.profile_revision,
                    Jsonb(definition.model_dump(mode="json")),
                    definition.policy_hash,
                ),
            )
            inserted += 1
    return {"inserted": inserted, "configured_revisions": len(registry.profiles)}


def _qualify_lexical(
    connection: psycopg.Connection[dict[str, Any]], context: WorkspaceContext, definition: ProfileDefinition
) -> int:
    if context.workspace_id not in definition.workspace_ids:
        raise ProfileNotAvailable
    from apps.workbench.api.postgres import _LEXICAL_INDEX_QUERY
    from apps.workbench.api.postgres_indexes import _INDEX_STATE_QUERY, _PUBLIC_COLUMNS
    from apps.workbench.api.profiles import qualify_profile

    generation = connection.execute(_INDEX_STATE_QUERY, (context.workspace_id,)).fetchone()
    index = connection.execute(_LEXICAL_INDEX_QUERY).fetchone()
    if generation is None or index != {"usable": True}:
        raise CorpusNotReady("The requested profile dependencies are not ready.")
    fields = {name: generation[name] for name in _PUBLIC_COLUMNS}
    fields["committed_at"] = generation["committed_at"].astimezone(UTC).isoformat().replace("+00:00", "Z")
    qualify_profile(definition, IndexGeneration.model_validate(fields))
    return int(generation["generation_id"])


def transition_profile(
    dsn: str,
    *,
    workspace_id: str,
    profile_id: str,
    profile_revision: str,
    state: Literal["draft", "qualified", "active", "retired"],
    expected_rollout_version: int | None = None,
) -> ProfileRollout:
    """Commit an explicit audited lifecycle selection with compare-and-set fencing."""
    with _administrator(dsn) as connection:
        return _transition_profile(
            connection,
            workspace_id=workspace_id,
            profile_id=profile_id,
            profile_revision=profile_revision,
            state=state,
            expected_rollout_version=expected_rollout_version,
        )


def _transition_profile(
    connection: psycopg.Connection[dict[str, Any]],
    *,
    workspace_id: str,
    profile_id: str,
    profile_revision: str,
    state: Literal["draft", "qualified", "active", "retired"],
    expected_rollout_version: int | None,
) -> ProfileRollout:
    context = WorkspaceContext(workspace_id=workspace_id)
    connection.execute("SELECT set_config('workbench.workspace_id',%s,true)", (workspace_id,))
    workspace = connection.execute(
        "SELECT workspace_id FROM workbench.workspaces WHERE workspace_id=%s FOR UPDATE", (workspace_id,)
    ).fetchone()
    if workspace is None:
        raise ProfileNotAvailable
    stored = connection.execute(
        "SELECT definition,policy_hash FROM workbench.retrieval_profile_revisions "
        "WHERE profile_id=%s AND profile_revision=%s",
        (profile_id, profile_revision),
    ).fetchone()
    if stored is None:
        raise ProfileNotAvailable
    definition = ProfileDefinition.model_validate(stored["definition"])
    if definition.policy_hash != stored["policy_hash"] or workspace_id not in definition.workspace_ids:
        raise ProfileNotAvailable
    existing = connection.execute(
        "SELECT * FROM workbench.retrieval_profile_rollouts WHERE workspace_id=%s AND profile_id=%s FOR UPDATE",
        (workspace_id, profile_id),
    ).fetchone()
    if existing is None:
        count = connection.execute(
            "SELECT count(*) AS count FROM workbench.retrieval_profile_rollouts WHERE workspace_id=%s", (workspace_id,)
        ).fetchone()
        if count is None or count["count"] >= _MAX_WORKSPACE_PROFILES:
            raise RecordConflict("The workspace profile registry has reached its approved bound.")
    current_version = 0 if existing is None else existing["rollout_version"]
    if expected_rollout_version is not None and expected_rollout_version != current_version:
        raise RecordConflict("The workspace profile rollout changed; refresh its current version.")
    qualified_generation_id = None
    if state in {"qualified", "active"}:
        qualified_generation_id = _qualify_lexical(connection, context, definition)
    if state == "active" and (
        existing is None
        or existing["profile_revision"] != profile_revision
        or existing["state"] not in {"qualified", "active"}
    ):
        raise RecordConflict("Qualify this exact revision before activation.")
    if existing is not None and (
        existing["profile_revision"],
        existing["state"],
        existing["policy_hash"],
        existing["qualified_generation_id"],
    ) == (profile_revision, state, definition.policy_hash, qualified_generation_id):
        return ProfileRollout.model_validate({name: existing[name] for name in _ROLLOUT_COLUMNS})
    connection.execute(
        "INSERT INTO workbench.retrieval_profile_rollouts(workspace_id,profile_id,profile_revision,policy_hash,"
        "state,rollout_version,qualified_generation_id) VALUES(%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT(workspace_id,profile_id) DO UPDATE SET profile_revision=EXCLUDED.profile_revision,"
        "policy_hash=EXCLUDED.policy_hash,state=EXCLUDED.state,rollout_version=EXCLUDED.rollout_version,"
        "qualified_generation_id=EXCLUDED.qualified_generation_id,updated_at=clock_timestamp()",
        (
            workspace_id,
            profile_id,
            profile_revision,
            definition.policy_hash,
            state,
            current_version + 1,
            qualified_generation_id,
        ),
    )
    return ProfileRollout(
        workspace_id=workspace_id,
        profile_id=profile_id,
        profile_revision=profile_revision,
        policy_hash=definition.policy_hash,
        state=state,
        rollout_version=current_version + 1,
        qualified_generation_id=qualified_generation_id,
    )


def promote_profile(
    dsn: str, *, workspace_id: str, profile_id: str, profile_revision: str, expected_rollout_version: int | None = None
) -> ProfileRollout:
    """Qualify and activate a new or historical revision atomically, retaining the old selection on failure."""
    with _administrator(dsn) as connection:
        qualified = _transition_profile(
            connection,
            workspace_id=workspace_id,
            profile_id=profile_id,
            profile_revision=profile_revision,
            state="qualified",
            expected_rollout_version=expected_rollout_version,
        )
        return _transition_profile(
            connection,
            workspace_id=workspace_id,
            profile_id=profile_id,
            profile_revision=profile_revision,
            state="active",
            expected_rollout_version=qualified.rollout_version,
        )


def main() -> None:
    """Run explicit local administration without a browser admin endpoint or credential output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("sync", "qualify", "activate", "retire", "promote", "rollback", "status"))
    parser.add_argument("--workspace-id", default="development")
    parser.add_argument("--profile-id", default="postgres-fts-baseline")
    parser.add_argument("--profile-revision", default="postgres-fts-baseline-r1")
    parser.add_argument("--expected-rollout-version", type=int)
    arguments = parser.parse_args()
    dsn = os.environ.get("WORKBENCH_DB_ADMIN_DSN")
    if not dsn:
        parser.error("WORKBENCH_DB_ADMIN_DSN is required")
    try:
        if arguments.command == "sync":
            result: Any = sync_registry(dsn, load_profile_registry(os.environ))
        elif arguments.command == "status":
            result = _status(dsn, workspace_id=arguments.workspace_id)
        elif arguments.command in {"promote", "rollback"}:
            result = promote_profile(
                dsn,
                workspace_id=arguments.workspace_id,
                profile_id=arguments.profile_id,
                profile_revision=arguments.profile_revision,
                expected_rollout_version=arguments.expected_rollout_version,
            ).model_dump(mode="json")
        else:
            states: dict[str, Literal["draft", "qualified", "active", "retired"]] = {
                "qualify": "qualified",
                "activate": "active",
                "retire": "retired",
            }
            result = transition_profile(
                dsn,
                workspace_id=arguments.workspace_id,
                profile_id=arguments.profile_id,
                profile_revision=arguments.profile_revision,
                state=states[arguments.command],
                expected_rollout_version=arguments.expected_rollout_version,
            ).model_dump(mode="json")
    except Exception:
        parser.exit(1, "Profile administration failed.\n")
    print(json.dumps(result, separators=(",", ":")))


def _status(dsn: str, *, workspace_id: str) -> list[dict[str, Any]]:
    async def read() -> list[dict[str, Any]]:
        async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as connection:
            await connection.execute("SELECT set_config('workbench.workspace_id',%s,true)", (workspace_id,))
            return [
                item.model_dump(mode="json")
                for item in await read_profile_rollouts(connection, WorkspaceContext(workspace_id=workspace_id))
            ]

    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(read())


if __name__ == "__main__":
    main()
