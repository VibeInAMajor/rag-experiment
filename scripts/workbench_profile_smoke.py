"""Exercise profile rollout and API restart in an explicitly owned disposable PostgreSQL database."""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
import psutil
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from apps.workbench.api.db_migrations import migrate
from apps.workbench.api.db_seed import seed_development
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.postgres_profiles import promote_profile, sync_registry, transition_profile
from apps.workbench.api.profile_registry import ProfileDefinition, ProfileRegistry, default_profile_registry

_ROOT = Path(__file__).resolve().parents[1]
_DIRECTORY = _ROOT / ".cache" / "workbench-profile-smoke"
_STATE = _DIRECTORY / "state.json"
_EVIDENCE = _ROOT / "tasks" / "evidence" / "profile-2026-11-23" / "http-rollout.json"
_DATABASE_NAME = re.compile(r"rag_test_profile_smoke_[a-f0-9]{32}")
_PROFILE_ID = "postgres-fts-focused"
_PROFILE_REVISION = "focused-r1"
_PORT = 8021


def _registry() -> ProfileRegistry:
    baseline = default_profile_registry().profiles[0]
    focused = ProfileDefinition.model_validate(
        {
            **baseline.model_dump(),
            "profile_id": _PROFILE_ID,
            "profile_revision": _PROFILE_REVISION,
            "label": "Focused keyword search",
            "max_top_k": 3,
            "candidate_k": 5,
        }
    )
    return ProfileRegistry(profiles=(baseline, focused))


def _state() -> dict[str, Any]:
    state = json.loads(_STATE.read_text(encoding="utf-8"))
    if _DATABASE_NAME.fullmatch(state.get("database_name", "")) is None or state.get("port") != _PORT:
        raise RuntimeError("Refusing state outside the owned profile smoke database.")
    return state


def _save_state(state: dict[str, Any]) -> None:
    _DIRECTORY.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _connections(state: dict[str, Any]) -> tuple[str, str]:
    return (
        make_conninfo(os.environ["WORKBENCH_TEST_ADMIN_DSN"], dbname=state["database_name"]),
        make_conninfo(os.environ["WORKBENCH_TEST_APP_DSN"], dbname=state["database_name"]),
    )


def _application_uri(dsn: str) -> str:
    fields = conninfo_to_dict(dsn)
    host, user, password, database = (fields.get(key) for key in ("host", "user", "password", "dbname"))
    if (
        not isinstance(host, str)
        or not isinstance(user, str)
        or not isinstance(password, str)
        or not isinstance(database, str)
    ):
        raise TypeError("The smoke environment requires explicit local application connection fields.")
    host = f"[{host}]" if ":" in host else host
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@"
        f"{host}:{fields.get('port') or '5432'}/{quote(database, safe='')}"
    )


def _record(label: str, value: Any) -> None:
    report = json.loads(_EVIDENCE.read_text(encoding="utf-8")) if _EVIDENCE.exists() else {}
    report.update(
        scope="owned disposable PostgreSQL; synthetic lexical corpus", recorded_at=datetime.now(UTC).isoformat()
    )
    report[label] = value
    report.setdefault("events", []).append({"action": label, "recorded_at": report["recorded_at"], "data": value})
    _EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    _EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


async def _seed(application_dsn: str) -> None:
    repository = PostgresPersistence(application_dsn)
    await repository.start()
    try:
        await seed_development(repository)
    finally:
        await repository.close()


def _run_async(coroutine: Any) -> Any:
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coroutine)


def _prepare() -> None:
    if _STATE.exists():
        raise RuntimeError("An owned smoke state already exists; inspect or clean it up first.")
    state: dict[str, Any] = {"database_name": f"rag_test_profile_smoke_{uuid4().hex}", "port": _PORT}
    administrator, application = _connections(state)
    control = make_conninfo(os.environ["WORKBENCH_TEST_ADMIN_DSN"], dbname="postgres")
    with psycopg.connect(control, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(state["database_name"])))
    _save_state(state)
    migration = migrate(administrator)
    _run_async(_seed(application))
    registry = _registry()
    sync_registry(administrator, registry)
    _DIRECTORY.joinpath("registry.yaml").write_text(registry.model_dump_json(indent=2) + "\n", encoding="utf-8")
    _transition(state, "activate")
    _record(
        "preparation",
        {"schema_revision": migration.revision, "profiles": [item.profile_id for item in registry.profiles]},
    )


def _start(state: dict[str, Any]) -> None:
    if state.get("api_pid"):
        raise RuntimeError("An API process is already recorded; verify or restart it explicitly.")
    _, application = _connections(state)
    environment = {
        **os.environ,
        "WORKBENCH_DB_DSN": _application_uri(application),
        "WORKBENCH_API_PORT": str(_PORT),
        "WORKBENCH_PROFILE_REGISTRY_CONFIG": str(_DIRECTORY / "registry.yaml"),
        "WORKBENCH_CORPUS_SNAPSHOT_MODE": "persisted",
        "HAYSTACK_TELEMETRY_ENABLED": "false",
    }
    for key in (
        "WORKBENCH_TEST_ADMIN_DSN",
        "WORKBENCH_TEST_APP_DSN",
        "WORKBENCH_DB_ADMIN_DSN",
        "WORKBENCH_DB_ADMIN_PASSWORD",
        "WORKBENCH_DB_APP_PASSWORD",
    ):
        environment.pop(key, None)
    process = subprocess.Popen(
        [sys.executable, "-m", "apps.workbench.api"],
        cwd=_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    state.update(api_pid=process.pid, api_created_at=psutil.Process(process.pid).create_time())
    _save_state(state)
    deadline = monotonic() + 45
    with httpx.Client(base_url=f"http://127.0.0.1:{_PORT}", timeout=3) as client:
        while monotonic() < deadline:
            try:
                if client.get("/api/v1/health/ready").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                raise RuntimeError("The isolated API exited before readiness.")
            sleep(0.25)
    raise RuntimeError("The isolated API did not become ready.")


def _stop(state: dict[str, Any]) -> None:
    if not state.get("api_pid"):
        return
    try:
        process = psutil.Process(state["api_pid"])
        if process.create_time() != state["api_created_at"] or process.cmdline()[-2:] != ["-m", "apps.workbench.api"]:
            raise RuntimeError("Refusing to stop an unowned process.")
        process.terminate()
        try:
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    except psutil.NoSuchProcess:
        pass
    state.pop("api_pid", None)
    state.pop("api_created_at", None)
    _save_state(state)


def _transition(state: dict[str, Any], command: str) -> None:
    administrator, _ = _connections(state)
    if command == "activate":
        rollout = promote_profile(
            administrator, workspace_id="development", profile_id=_PROFILE_ID, profile_revision=_PROFILE_REVISION
        )
    else:
        rollout = transition_profile(
            administrator,
            workspace_id="development",
            profile_id=_PROFILE_ID,
            profile_revision=_PROFILE_REVISION,
            state="retired",
        )
    _record(command, rollout.model_dump(mode="json"))
    if command == "retire" and state.get("api_pid"):
        with httpx.Client(base_url=f"http://127.0.0.1:{_PORT}", timeout=10) as client:
            response = client.post(
                "/api/v1/workspaces/development/search",
                json={
                    "query": "PostgreSQL",
                    "top_k": 3,
                    "profile_id": _PROFILE_ID,
                    "expected_profile_revision": _PROFILE_REVISION,
                },
            )
        payload = response.json()
        if response.status_code != 409 or "results" in payload:
            raise RuntimeError("A retired profile did not refuse execution safely.")
        _record(
            "retired_request",
            {"http_status": response.status_code, "code": payload["error"]["code"], "trace_id": payload["trace_id"]},
        )


def _verify(state: dict[str, Any]) -> dict[str, Any]:
    _, application = _connections(state)
    with httpx.Client(base_url=f"http://127.0.0.1:{_PORT}", timeout=10) as client:
        ready = client.get("/api/v1/health/ready")
        ready.raise_for_status()
        capabilities = client.get("/api/v1/capabilities").json()
        searches = []
        for profile in capabilities["profiles"]:
            request = {
                "query": "PostgreSQL",
                "top_k": min(3, profile["parameters"]["top_k"]["maximum"]),
                "profile_id": profile["profile_id"],
                "expected_profile_revision": profile["profile_revision"],
            }
            response = client.post("/api/v1/workspaces/development/search", json=request)
            response.raise_for_status()
            payload = response.json()
            projected = [
                {key: hit[key] for key in ("chunk_id", "source_id", "source_version_id", "score")}
                for hit in payload["results"]
            ]
            with psycopg.connect(application, row_factory=dict_row) as connection:
                connection.execute("SELECT set_config('workbench.workspace_id','development',true)")
                rows = connection.execute(
                    "SELECT c.chunk_id,c.source_id,c.version_id AS source_version_id,"
                    "ts_rank_cd(c.search_vector,q.query)::double precision AS score FROM workbench.chunks c "
                    "JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
                    "CROSS JOIN plainto_tsquery('simple',%s) AS q(query) WHERE c.workspace_id='development' "
                    "AND v.status='active' AND c.search_vector @@ q.query "
                    'ORDER BY score DESC,c.chunk_id COLLATE "C" LIMIT %s',
                    (request["query"], request["top_k"]),
                ).fetchall()
            if projected != rows:
                raise RuntimeError("The HTTP profile results differ from the independent SQL oracle.")
            searches.append(
                {
                    "profile_id": payload["profile_id"],
                    "profile_revision": payload["profile_revision"],
                    "corpus_revision": payload["corpus_revision"],
                    "trace_id": payload["trace_id"],
                    "score_type": "postgres_ts_rank_cd",
                    "results": projected,
                    "sql_parity": True,
                }
            )
    return {"readiness": ready.status_code, "capabilities": capabilities, "searches": searches}


def _cleanup(state: dict[str, Any]) -> None:
    _stop(state)
    control = make_conninfo(os.environ["WORKBENCH_TEST_ADMIN_DSN"], dbname="postgres")
    with psycopg.connect(control, autocommit=True) as connection:
        connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(state["database_name"])))
    _STATE.unlink()
    _record("cleanup", {"database_removed": True, "api_stopped": True})


def main() -> None:
    """Run bounded explicit phases; never mutate or restart the shared development database/API."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "start", "verify", "retire", "activate", "restart", "cleanup"))
    arguments = parser.parse_args()
    if arguments.command == "prepare":
        _prepare()
    else:
        state = _state()
        if arguments.command == "start":
            _start(state)
        elif arguments.command == "verify":
            _record("http_verification", _verify(state))
        elif arguments.command in {"retire", "activate"}:
            _transition(state, arguments.command)
        elif arguments.command == "restart":
            before = _verify(state)
            _stop(state)
            _start(state)
            after = _verify(state)
            before_searches = [
                {key: value for key, value in item.items() if key != "trace_id"} for item in before["searches"]
            ]
            after_searches = [
                {key: value for key, value in item.items() if key != "trace_id"} for item in after["searches"]
            ]
            if before_searches != after_searches:
                raise RuntimeError("Profile provenance or results changed across API restart.")
            _record("api_restart", {"before": before, "after": after, "passed": True})
        else:
            _cleanup(state)
    print(json.dumps({"command": arguments.command, "status": "completed", "api_port": _PORT}))


if __name__ == "__main__":
    main()
