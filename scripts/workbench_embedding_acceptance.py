"""Explicit real-model acceptance in an owned disposable database; production data is never reset."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import JsonValue

from apps.workbench.api.application import create_app
from apps.workbench.api.chunking import ExactModelCounter
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.db_migrations import migrate
from apps.workbench.api.db_seed import seed_development
from apps.workbench.api.embedding import EmbeddingBatch, EmbeddingItem, EmbeddingPort, EmbeddingRequest
from apps.workbench.api.embedding_ingestion import EmbeddingIngestionService
from apps.workbench.api.persistence import Chunk, Source, SourceVersion, Workspace, WorkspaceContext
from apps.workbench.api.postgres import PostgresPersistence
from scripts.workbench_embedding_backfill import (
    BackfillRuntime,
    load_capacity_configuration,
    open_backfill_runtime,
    run_backfill,
)
from scripts.workbench_embedding_capacity_benchmark import observe_backlogged_run
from scripts.workbench_embedding_evaluate import (
    EvaluationFixture,
    evaluate_persisted_vectors,
    evaluate_query,
    load_evaluation_fixture,
    prepare_evaluation_vectors,
)
from scripts.workbench_embedding_qualify import _DEFAULT_CONTAINER, _DEFAULT_ENDPOINT, _digest

_OWNER_WORKSPACE = "acceptance-owner"
_DATABASE_PATTERN = re.compile(r"rag_test_[a-f0-9]{32}")
_PACKET_CYCLE = (8, 8, 8, 4)


class AcceptanceError(ValueError):
    """Expose a static acceptance refusal without connection strings, documents or provider output."""


@dataclass(frozen=True)
class _Database:
    name: str
    run_id: str
    admin_dsn: str = field(repr=False)
    app_dsn: str = field(repr=False)


@dataclass
class _LoadState:
    workspace: int = 0
    packet: int = 0
    last_progress: float = 0.0


class _AuditedProvider:
    def __init__(self, provider: EmbeddingPort, records: list[dict[str, Any]]) -> None:
        self._provider, self._records = provider, records

    async def warm_up_async(self) -> None:
        """Delegate setup to the existing governed provider."""
        await self._provider.warm_up_async()

    async def close_async(self) -> None:
        """Delegate closure without creating a second provider client."""
        await self._provider.close_async()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingBatch:
        """Retain real returned input fingerprints and counts without document bodies or vectors."""
        result = await self._provider.embed(request)
        self._records.append(
            {
                "workspace_id": request.workspace_id,
                "item_ids": list(result.item_ids),
                "source_hashes": list(result.source_hashes),
                "input_hashes": list(result.input_hashes),
                "token_counts": list(result.token_counts),
                "usage_tokens": result.usage_tokens,
                "usage_provenance": result.usage_provenance,
            }
        )
        return result


def _database(name: str, run_id: str) -> _Database:
    if _DATABASE_PATTERN.fullmatch(name) is None or re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
        raise AcceptanceError("INVALID_DISPOSABLE_ACCEPTANCE_IDENTITY")
    admin = os.environ.get("WORKBENCH_TEST_ADMIN_DSN", "")
    app = os.environ.get("WORKBENCH_TEST_APP_DSN", "")
    if not admin or not app:
        raise AcceptanceError("EXPLICIT_TEST_DATABASE_CREDENTIALS_REQUIRED")
    try:
        left, right = conninfo_to_dict(admin), conninfo_to_dict(app)
        if left.get("host") not in {"localhost", "127.0.0.1", "::1"} or any(
            left.get(key) != right.get(key) for key in ("host", "port")
        ):
            raise AcceptanceError("DATABASE_ENDPOINTS_MUST_MATCH_LOCAL_TEST_INSTANCE")
        return _Database(name, run_id, make_conninfo(admin, dbname=name), make_conninfo(app, dbname=name))
    except (ValueError, psycopg.Error):
        raise AcceptanceError("INVALID_DISPOSABLE_ACCEPTANCE_TARGET") from None


def _owner_metadata(database: _Database) -> dict[str, JsonValue]:
    return {"acceptance_run_id": database.run_id, "database_name": database.name}


def _create_database(database: _Database) -> None:
    with psycopg.connect(make_conninfo(database.admin_dsn, dbname="postgres"), autocommit=True) as control:
        control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database.name)))


def _assert_owner(database: _Database) -> None:
    if _DATABASE_PATTERN.fullmatch(database.name) is None:
        raise AcceptanceError("DISPOSABLE_NAME_REQUIRED")
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        row = connection.execute(
            "SELECT metadata FROM workbench.workspaces WHERE workspace_id=%s", (_OWNER_WORKSPACE,)
        ).fetchone()
    if row is None or row[0] != _owner_metadata(database):
        raise AcceptanceError("DISPOSABLE_DATABASE_OWNER_MISMATCH")


def _drop_database(database: _Database, *, created_here: bool = False) -> None:
    if (
        _DATABASE_PATTERN.fullmatch(database.name) is None
        or conninfo_to_dict(database.admin_dsn).get("dbname") != database.name
    ):
        raise AcceptanceError("REFUSING_UNOWNED_DATABASE_REMOVAL")
    if not created_here:
        _assert_owner(database)
    with psycopg.connect(make_conninfo(database.admin_dsn, dbname="postgres"), autocommit=True) as control:
        control.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database.name)))


def _write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _progress(phase: str, **counts: Any) -> None:
    print(json.dumps({"phase": phase, **counts}), flush=True)


def _public_preparation(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"endpoint", "model_directory", "capacity_config", "quality_before_file", "load_text"}
    }


async def _backfill_uploaded(runtime: BackfillRuntime, context: WorkspaceContext) -> dict[str, Any]:
    result = await run_backfill(runtime, context, idle_seconds=0.0)
    if result["status"] != "READY":
        raise AcceptanceError("REAL_UPLOAD_EMBEDDING_BACKFILL_NOT_READY")
    _progress("real-upload-backfilled", ready_embeddings=result["coverage"]["ready_embeddings"])
    return result


def _capacity_shape(path: Path) -> tuple[int, str, str]:
    profile, capacity = load_capacity_configuration(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    report = raw.get("report", {})
    if _digest(report) != capacity.calibration_digest or not report.get("denominator_frozen_before_validation"):
        raise AcceptanceError("REAL_FROZEN_CALIBRATION_EVIDENCE_REQUIRED")
    target = report["selected"]["tokens_per_item_target"]
    if type(target) is not int or not 1 <= target <= min(profile.max_tokens, 8192):
        raise AcceptanceError("INVALID_CALIBRATED_PACKET_SHAPE")
    return target, profile.fingerprint, capacity.calibration_digest


def _unique_text(counter: ExactModelCounter, target: int, workspace: str, index: int, run_id: str) -> str:
    header = f"Durable acceptance record {run_id} {workspace} {index}. Source versions preserve evidence. "
    repeats = max(0, target - counter.count_tokens(header))
    for _ in range(8):
        text = header + "a " * repeats
        difference = target - counter.count_tokens(text)
        if difference == 0:
            return text
        repeats += difference
        if repeats < 0:
            break
    raise AcceptanceError("EXACT_NATIVE_TOKEN_PACKET_COULD_NOT_BE_PREPARED")


async def _initialize_database(database: _Database) -> None:
    revision = await asyncio.to_thread(migrate, database.admin_dsn)
    if revision.revision != "0005":
        raise AcceptanceError("REQUIRED_MIGRATION_NOT_INSTALLED")
    repository = PostgresPersistence(database.app_dsn)
    await repository.start()
    try:
        context = WorkspaceContext(workspace_id=_OWNER_WORKSPACE, trace_id="acceptance-ownership")
        await repository.create_workspace(
            context,
            Workspace(
                workspace_id=_OWNER_WORKSPACE, name="Disposable acceptance owner", metadata=_owner_metadata(database)
            ),
        )
        await seed_development(repository)
    finally:
        await repository.close()


def _upload_content(*, edited: bool = False) -> bytes:
    text = "\n\n".join(
        f"Section {index}. "
        + ("Durable publication preserves the original evidence and a consistent source version. " * 16)
        for index in range(100)
    )
    return (text.replace("version", "release", 1) if edited else text).encode()


async def _upload_text(database: _Database, *, current: dict[str, Any] | None = None) -> dict[str, Any]:
    content = _upload_content(edited=current is not None)
    app = create_app(settings=ApiSettings(), persistence=PostgresPersistence(database.app_dsn))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        response = await client.post(
            "/api/v1/workspaces/development/documents",
            files={"file": ("acceptance.txt", content, "text/plain")},
            headers={"Idempotency-Key": uuid4().hex if current else database.run_id},
            data={"source_id": current["source_id"], "expected_active_version_id": current["source_version_id"]}
            if current
            else None,
        )
        if response.status_code != (200 if current else 201):
            raise AcceptanceError("ACTUAL_MULTIPART_UPLOAD_FAILED")
        payload = response.json()
        if payload.get("chunk_count", 0) < 20:
            raise AcceptanceError("UPLOAD_DID_NOT_EXERCISE_TWENTY_CHUNKS")
        return {
            "http_status": response.status_code,
            "source_id": payload["source_id"],
            "source_version_id": payload["source_version_id"],
            "chunk_count": payload["chunk_count"],
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "content_bytes": len(content),
        }


async def _real_upload_edit(runtime: BackfillRuntime, database: _Database, uploaded: dict[str, Any]) -> dict[str, Any]:
    context = WorkspaceContext(workspace_id="development", trace_id="actual-http-edit-reuse")
    before_page = await runtime.persistence.list_active_chunks(context, source_id=uploaded["source_id"], limit=100)
    if before_page is None or before_page.next_after is not None:
        raise AcceptanceError("UPLOAD_CHUNK_INVENTORY_UNAVAILABLE")
    before_hashes = {item.content_hash for item in before_page.items}
    before = runtime.worker.statistics()
    updated = await _upload_text(database, current=uploaded)
    after_page = await runtime.persistence.list_active_chunks(context, source_id=uploaded["source_id"], limit=100)
    if after_page is None or after_page.next_after is not None:
        raise AcceptanceError("UPDATED_UPLOAD_CHUNK_INVENTORY_UNAVAILABLE")
    expected_reuse = sum(item.content_hash in before_hashes for item in after_page.items)
    expected_new = len({item.content_hash for item in after_page.items} - before_hashes)
    if not 0 < expected_reuse < len(after_page.items) or not expected_new:
        raise AcceptanceError("EDIT_MUST_RETAIN_UNCHANGED_CHUNKS")
    completed = await _backfill_uploaded(runtime, context)
    delta = {key: value - before[key] for key, value in runtime.worker.statistics().items()}
    if delta["generated_inputs"] != expected_new or delta["reused_chunks"] != expected_reuse:
        raise AcceptanceError("ACTUAL_HTTP_EDIT_CACHE_REUSE_FAILED")
    report = {
        "status": "PASS",
        "http_status": updated["http_status"],
        "source_id": uploaded["source_id"],
        "previous_version_id": uploaded["source_version_id"],
        "current_version_id": updated["source_version_id"],
        "expected_new_inputs": expected_new,
        "expected_reused_chunks": expected_reuse,
        "statistics_delta": delta,
        "coverage": completed["coverage"],
    }
    _progress("real-http-edit-cache-reuse", new_inputs=expected_new, reused_chunks=expected_reuse)
    return report


async def _publish_backlog(
    runtime: BackfillRuntime, database: _Database, target: int, chunks: int
) -> tuple[list[str], list[dict[str, Any]]]:
    minimum = math.ceil(runtime.capacity.sustainable_tpm * 12 / target)
    if type(chunks) is not int or not minimum <= chunks <= 3000:
        raise AcceptanceError("BACKLOG_MUST_COVER_TWELVE_MINUTES_WITH_BOUNDED_SOURCE_BYTES")
    workspaces = [f"capacity-{database.run_id[:8]}-{suffix}" for suffix in ("a", "b", "c")]
    all_hashes: set[str] = set()
    inventory = []
    for ordinal, workspace in enumerate(workspaces):
        context = WorkspaceContext(workspace_id=workspace, trace_id="acceptance-load-publication")
        await runtime.persistence.create_workspace(
            context,
            Workspace(workspace_id=workspace, name="Controlled capacity backlog", metadata=_owner_metadata(database)),
        )
        await runtime.persistence.register_embedding_profile(context, runtime.profile)
        count = chunks // 3 + int(ordinal < chunks % 3)
        records = []
        byte_count = 0
        digest = hashlib.sha256()
        for index in range(count):
            content = _unique_text(runtime.counter, target, workspace, index, database.run_id)
            encoded = content.encode()
            content_hash = hashlib.sha256(encoded).hexdigest()
            if content_hash in all_hashes:
                raise AcceptanceError("BACKLOG_INPUTS_MUST_BE_UNIQUE")
            all_hashes.add(content_hash)
            byte_count += len(encoded)
            digest.update(encoded)
            records.append(
                Chunk(
                    workspace_id=workspace,
                    source_id="capacity-source",
                    version_id="capacity-v1",
                    chunk_id=f"capacity-{index:06d}",
                    title="Controlled durable load",
                    content=content,
                    content_hash=content_hash,
                    metadata={"ordinal": index, "native_tokens": target},
                )
            )
        if byte_count > 50 * 1024 * 1024 or len(records) > 10000:
            raise AcceptanceError("BACKLOG_EXCEEDS_SOURCE_PUBLICATION_BOUND")
        await runtime.persistence.publish_source(
            context,
            source=Source(workspace_id=workspace, source_id="capacity-source", title="Controlled durable load"),
            version=SourceVersion(
                workspace_id=workspace,
                source_id="capacity-source",
                version_id="capacity-v1",
                content_hash=digest.hexdigest(),
                metadata={"parser_id": "controlled-native-token-fixture", "parser_revision": "native4096-fixture-r1"},
            ),
            chunks=records,
        )
        await runtime.persistence.enqueue_embedding_backfill(context, runtime.profile)
        inventory.append({"workspace_id": workspace, "input_hashes": [record.content_hash for record in records]})
        _progress("backlog-workspace-published", workspace_id=workspace, chunks=count, content_bytes=byte_count)
    return workspaces, inventory


async def prepare_acceptance(arguments: argparse.Namespace) -> dict[str, Any]:
    """Create one fresh UUID database and retain its guarded manifest for the separately authorized load run."""
    if arguments.manifest.exists():
        raise AcceptanceError("ACCEPTANCE_MANIFEST_ALREADY_EXISTS")
    target, fingerprint, calibration = _capacity_shape(arguments.capacity_config)
    capacity = load_capacity_configuration(arguments.capacity_config)[1]
    if not math.ceil(capacity.sustainable_tpm * 12 / target) <= arguments.chunks <= 3000:
        raise AcceptanceError("BACKLOG_MUST_COVER_TWELVE_MINUTES_WITH_BOUNDED_SOURCE_BYTES")
    database = _database(f"rag_test_{uuid4().hex}", uuid4().hex)
    await asyncio.to_thread(_create_database, database)
    try:
        _progress("database-created", database_name=database.name)
        await _initialize_database(database)
        uploaded = await _upload_text(database)
        _progress("real-upload-completed", chunks=uploaded["chunk_count"])
        context = WorkspaceContext(workspace_id="development", trace_id="acceptance-upload-backfill")
        async with open_backfill_runtime(
            dsn=database.app_dsn,
            model_directory=arguments.model_directory,
            capacity_config=arguments.capacity_config,
            context=context,
            endpoint=arguments.endpoint,
            container=arguments.container,
        ) as runtime:
            upload_backfill = await _backfill_uploaded(runtime, context)
            upload_edit = await _real_upload_edit(runtime, database, uploaded)
            fixture = load_evaluation_fixture()
            phases = await prepare_evaluation_vectors(runtime, fixture)
            quality = await evaluate_persisted_vectors(runtime, fixture)
            await asyncio.to_thread(_write, arguments.output_dir / "acceptance-quality-before.json", quality)
            _progress("objective-quality-evaluated", queries=quality["overall"]["queries"])
            workspaces, inventory = await _publish_backlog(runtime, database, target, arguments.chunks)
        manifest = {
            "schema_version": "embedding-acceptance-v1",
            "database_name": database.name,
            "run_id": database.run_id,
            "profile_fingerprint": fingerprint,
            "calibration_digest": calibration,
            "capacity_config": str(arguments.capacity_config.resolve()),
            "model_directory": str(arguments.model_directory.resolve()),
            "endpoint": arguments.endpoint,
            "container": arguments.container,
            "target_tokens_per_item": target,
            "load_chunks": arguments.chunks,
            "load_workspaces": workspaces,
            "prepared_at_unix": time.time(),
            "upload": uploaded,
            "upload_backfill": upload_backfill,
            "actual_http_upload_edit": upload_edit,
            "quality_preparation": phases,
            "quality_before_file": str((arguments.output_dir / "acceptance-quality-before.json").resolve()),
            "quality_before_sha256": _digest(quality),
            "load_text": "unique nonce + short filler; exact native-token count; differs from calibration text",
            "packet_cycle_items": list(_PACKET_CYCLE),
            "backlog_input_inventory": inventory,
            "database_removed": False,
        }
        await asyncio.to_thread(_write, arguments.manifest, manifest)
        await asyncio.to_thread(
            _write, arguments.output_dir / "acceptance-preparation.json", _public_preparation(manifest)
        )
        return {
            "status": "PREPARED",
            "manifest": str(arguments.manifest),
            "database_name": database.name,
            "load_chunks": arguments.chunks,
            "target_tokens_per_item": target,
            "llm_judge_used": False,
        }
    except BaseException:
        await asyncio.to_thread(_drop_database, database, created_here=True)
        raise


def _load_manifest(path: Path) -> tuple[dict[str, Any], _Database]:
    if path.stat().st_size > 1048576:
        raise AcceptanceError("ACCEPTANCE_MANIFEST_TOO_LARGE")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "embedding-acceptance-v1" or manifest.get("database_removed") is not False:
        raise AcceptanceError("INVALID_ACCEPTANCE_MANIFEST")
    database = _database(manifest["database_name"], manifest["run_id"])
    _assert_owner(database)
    return manifest, database


async def _quality_query(runtime: BackfillRuntime, fixture: EvaluationFixture, index: int) -> dict[str, Any]:
    answerable = [query for query in fixture.queries if query.relevance]
    query = answerable[index % len(answerable)]
    context = WorkspaceContext(workspace_id=fixture.workspace_id, trace_id=query.query_id)
    request = EmbeddingRequest(
        profile_id=runtime.profile.profile_id,
        profile_revision=runtime.profile.profile_revision,
        task_kind="query",
        workspace_id=context.workspace_id,
        trace_id=query.query_id,
        items=(
            EmbeddingItem(
                item_id=query.query_id, text=query.text, input_hash=hashlib.sha256(query.text.encode()).hexdigest()
            ),
        ),
        deadline=time.monotonic() + runtime.profile.timeout_seconds,
    )
    output = await runtime.adapter.embed(request)
    hits = await runtime.persistence.exact_embedding_search(context, runtime.profile, output.vectors[0], limit=10)
    coverage = await runtime.persistence.embedding_coverage(context, runtime.profile)
    if coverage.index_generation is None:
        raise AcceptanceError("QUALITY_GENERATION_MISSING")
    return evaluate_query(
        fixture,
        query,
        hits,
        profile_fingerprint=runtime.profile.fingerprint,
        index_generation=coverage.index_generation,
    )


async def _run_prepared(arguments: argparse.Namespace, manifest: dict[str, Any], database: _Database) -> dict[str, Any]:
    if not math.isfinite(arguments.duration) or not 600 <= arguments.duration <= 1800:
        raise AcceptanceError("ACCEPTANCE_REQUIRES_BOUNDED_TEN_MINUTE_MINIMUM")
    target, fingerprint, calibration = _capacity_shape(Path(manifest["capacity_config"]))
    if (fingerprint, calibration, target) != (
        manifest["profile_fingerprint"],
        manifest["calibration_digest"],
        manifest["target_tokens_per_item"],
    ):
        raise AcceptanceError("FROZEN_CAPACITY_OR_PACKET_SHAPE_CHANGED")
    quiet = max(0.0, manifest["prepared_at_unix"] + 60 - time.time())
    if quiet:
        _progress("preparation-quiet-window", wait_seconds=quiet)
        await asyncio.sleep(quiet)
    context = WorkspaceContext(workspace_id="development", trace_id="acceptance-load")
    async with open_backfill_runtime(
        dsn=database.app_dsn,
        model_directory=Path(manifest["model_directory"]),
        capacity_config=Path(manifest["capacity_config"]),
        context=context,
        endpoint=manifest["endpoint"],
        container=manifest["container"],
    ) as runtime:
        contexts = [
            WorkspaceContext(workspace_id=name, trace_id="acceptance-durable-load")
            for name in manifest["load_workspaces"]
        ]
        document_audits: list[dict[str, Any]] = []
        provider = _AuditedProvider(runtime.adapter, document_audits)
        workers = [
            EmbeddingIngestionService(runtime.persistence, provider, profile=runtime.profile, counter=runtime.counter)
            for _ in contexts
        ]
        query_audits: list[dict[str, Any]] = []
        fixture = load_evaluation_fixture()
        state = _LoadState()
        started = time.monotonic()

        async def process_one() -> bool:
            index = state.workspace % len(workers)
            worker = workers[index]
            before = worker.statistics()["generated_inputs"]
            result = await worker.process_one(
                contexts[index], max_items=_PACKET_CYCLE[state.packet % len(_PACKET_CYCLE)]
            )
            if worker.statistics()["generated_inputs"] > before:
                state.packet += 1
            state.workspace += 1
            return result

        async def demand_probe() -> bool:
            coverage = await asyncio.gather(
                *(runtime.persistence.embedding_coverage(item, runtime.profile) for item in contexts)
            )
            now = time.monotonic()
            if now - state.last_progress >= 60:
                _progress(
                    "durable-load-progress",
                    elapsed_seconds=now - started,
                    covered=sum(item.ready_embeddings for item in coverage),
                    eligible=sum(item.eligible_active_chunks for item in coverage),
                    packets=state.packet,
                    query_checks=len(query_audits),
                )
                state.last_progress = now
            return all(item.eligible_active_chunks > item.ready_embeddings for item in coverage)

        async def query_probe() -> None:
            query_audits.append(await _quality_query(runtime, fixture, len(query_audits)))

        _progress(
            "ten-minute-durable-load-start",
            sustainable_tpm=runtime.capacity.sustainable_tpm,
            target_tpm=runtime.capacity.target_tpm,
            packet_cycle_items=list(_PACKET_CYCLE),
        )
        measured = await observe_backlogged_run(
            governor=runtime.governor,
            process_one=process_one,
            demand_probe=demand_probe,
            query_probe=query_probe,
            duration_seconds=arguments.duration,
            output=arguments.output_dir / "acceptance-capacity.json",
        )
        coverage = await asyncio.gather(
            *(runtime.persistence.embedding_coverage(item, runtime.profile) for item in contexts)
        )
        quality_after = await evaluate_persisted_vectors(runtime, fixture)
        before = json.loads(await asyncio.to_thread(Path(manifest["quality_before_file"]).read_text, encoding="utf-8"))
        if _digest(before) != manifest["quality_before_sha256"] or any(
            before[key] != quality_after[key] for key in ("fixture_digest", "profile_fingerprint", "index_generation")
        ):
            raise AcceptanceError("QUALITY_FIXTURE_OR_GENERATION_CHANGED")
        await asyncio.to_thread(_write, arguments.output_dir / "acceptance-quality-after.json", quality_after)
        report = {
            "status": measured["status"],
            "database_name": database.name,
            "capacity": measured,
            "workers": [worker.statistics() for worker in workers],
            "load_coverage": [item.model_dump(mode="json") for item in coverage],
            "concurrent_quality_audits": query_audits,
            "llm_judge_used": False,
            "quality_integrity_before_and_after": "PASS",
            "main_database_modified": False,
        }
        report["relevance_label_scope"] = "agent-authored synthetic fixture; no independent human validation"
        expected_hashes = {item for group in manifest["backlog_input_inventory"] for item in group["input_hashes"]}
        observed_hashes = [item for packet in document_audits for item in packet["input_hashes"]]
        if not set(observed_hashes) <= expected_hashes or len(observed_hashes) != len(set(observed_hashes)):
            raise AcceptanceError("ACTUAL_MODEL_INPUT_INVENTORY_MISMATCH")
        report["actual_document_packets"] = document_audits
        await asyncio.to_thread(_write, arguments.output_dir / "acceptance-report.json", report)
    return {
        "status": report["status"],
        "database_removed": True,
        "output": str(arguments.output_dir / "acceptance-report.json"),
    }


async def run_acceptance(arguments: argparse.Namespace) -> dict[str, Any]:
    """Run only the owned prepared database and remove it after all model and database clients close."""
    if not math.isfinite(arguments.duration) or not 600 <= arguments.duration <= 1800:
        raise AcceptanceError("ACCEPTANCE_REQUIRES_BOUNDED_TEN_MINUTE_MINIMUM")
    manifest, database = await asyncio.to_thread(_load_manifest, arguments.run_prepared)
    try:
        return await _run_prepared(arguments, manifest, database)
    finally:
        await asyncio.to_thread(_drop_database, database)
        manifest["database_removed"] = True
        await asyncio.to_thread(_write, arguments.run_prepared, manifest)


def main() -> int:
    """Preparation and the sustained GPU run are separate explicit operator actions."""
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--run-prepared", type=Path)
    actions.add_argument("--cleanup", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path(".cache/workbench-capacity/acceptance-manifest.json"))
    parser.add_argument(
        "--capacity-config", type=Path, default=Path("tasks/evidence/embedding-2026-11-24/capacity-calibration.json")
    )
    parser.add_argument("--model-directory", type=Path, default=Path("A:/AI/TEI/qwen3-4b"))
    parser.add_argument("--endpoint", default=_DEFAULT_ENDPOINT)
    parser.add_argument("--container", default=_DEFAULT_CONTAINER)
    parser.add_argument("--chunks", type=int, default=2200)
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--output-dir", type=Path, default=Path("tasks/evidence/embedding-2026-11-24"))
    arguments = parser.parse_args()
    try:
        if arguments.cleanup:
            manifest, database = _load_manifest(arguments.cleanup)
            _drop_database(database)
            manifest["database_removed"] = True
            _write(arguments.cleanup, manifest)
            report = {"status": "CLEANED", "database_removed": True}
        else:
            factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
            with asyncio.Runner(loop_factory=factory) as runner:
                report = runner.run(prepare_acceptance(arguments) if arguments.prepare else run_acceptance(arguments))
    except Exception as error:
        code = str(error) if isinstance(error, AcceptanceError) else type(error).__name__
        print(json.dumps({"status": "FAIL", "code": code}), flush=True)
        return 1
    print(json.dumps(report), flush=True)
    return 0 if report["status"] in {"PREPARED", "PASS", "CLEANED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
