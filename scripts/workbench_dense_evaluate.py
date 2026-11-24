"""Explicit real dense HTTP evaluation and an independent exact SQL oracle in an owned disposable database."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
import uvicorn
from pgvector import Vector

from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.embedding.embedding import EmbeddingBatch, EmbeddingPort, EmbeddingRequest
from apps.workbench.persistence.models import Workspace, WorkspaceContext
from apps.workbench.postgres.db_migrations import migrate
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.postgres.postgres_profiles import promote_profile, sync_registry
from apps.workbench.retrieval.dense import DenseService
from apps.workbench.retrieval.profile_registry import ProfileRegistry, default_profile_registry
from apps.workbench.retrieval.profiles import dense_profile_definition
from scripts.workbench_embedding_acceptance import (
    _OWNER_WORKSPACE,
    _create_database,
    _database,
    _drop_database,
    _owner_metadata,
)
from scripts.workbench_embedding_backfill import BackfillRuntime, open_backfill_runtime
from scripts.workbench_embedding_evaluate import (
    EvaluationFixture,
    EvaluationIntegrityError,
    _ensure_fixture_workspace,
    evaluate_query,
    load_evaluation_fixture,
    prepare_evaluation_vectors,
    score_ranking,
    summarize_evaluation,
)

_PROFILE_ID = "postgres-dense-exact"
_PROFILE_REVISION = "postgres-dense-exact-r1"


def _dense_registry(runtime: BackfillRuntime) -> ProfileRegistry:
    definition = dense_profile_definition(runtime.profile, capacity_policy_id=runtime.capacity.policy_id)
    return ProfileRegistry(profiles=(*default_profile_registry().profiles, definition))


def _http_fixture() -> EvaluationFixture:
    original = load_evaluation_fixture()
    data = original.model_dump(mode="json")
    data["fixture_id"] = "dense-http-retrieval-eval-v1"
    data["workspace_id"] = "development"
    for source in data["sources"]:
        if source["workspace_id"] == original.workspace_id:
            source["workspace_id"] = "development"
    return EvaluationFixture.model_validate_json(json.dumps(data))


def _distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered or any(not math.isfinite(value) or value < 0 for value in ordered):
        raise EvaluationIntegrityError("INVALID_DENSE_TIMING")
    return {
        "samples": len(ordered),
        "min": ordered[0],
        "p50": ordered[math.ceil(len(ordered) * 0.5) - 1],
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "max": ordered[-1],
    }


async def _server_inference_metrics(endpoint: str) -> tuple[int, float]:
    async with httpx.AsyncClient(base_url=endpoint, trust_env=False, follow_redirects=False, timeout=5) as client:
        response = await client.get("/metrics")
        response.raise_for_status()
    values = dict(
        line.split(" ", 1)
        for line in response.text.splitlines()
        if line.startswith(("te_request_inference_duration_sum ", "te_request_inference_duration_count "))
    )
    try:
        count = int(values["te_request_inference_duration_count"])
        total = float(values["te_request_inference_duration_sum"])
    except (KeyError, ValueError):
        raise EvaluationIntegrityError("PROVIDER_INFERENCE_METRICS_UNAVAILABLE") from None
    if count < 0 or not math.isfinite(total) or total < 0:
        raise EvaluationIntegrityError("PROVIDER_INFERENCE_METRICS_INVALID")
    return count, total


async def _dense_query(
    client: httpx.AsyncClient, *, endpoint: str, workspace_id: str, text: str, timings: dict[str, list[float]]
) -> httpx.Response:
    before = await _server_inference_metrics(endpoint)
    started = time.monotonic()
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/search",
        json={"query": text, "top_k": 10, "profile_id": _PROFILE_ID, "expected_profile_revision": _PROFILE_REVISION},
    )
    timings["http_wall_ms"].append((time.monotonic() - started) * 1000)
    after = await _server_inference_metrics(endpoint)
    if after[0] - before[0] != 1:
        raise EvaluationIntegrityError("PROVIDER_INFERENCE_SAMPLE_NOT_EXCLUSIVE")
    timings["provider_inference_ms"].append((after[1] - before[1]) * 1000)
    return response


class _ObservedEmbedding:
    def __init__(self, provider: EmbeddingPort) -> None:
        self.provider = provider
        self.batch: EmbeddingBatch | None = None
        self.elapsed_ms = 0.0
        self.trace_id: str | None = None

    async def warm_up_async(self) -> None:
        """Reuse the existing provider, which owns setup and attestation."""
        await self.provider.warm_up_async()

    async def close_async(self) -> None:
        """Keep provider lifetime with its owning runtime context."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingBatch:
        """Retain only this call's output in memory for an independent SQL comparison."""
        self.batch = None
        self.trace_id = request.trace_id
        started = time.monotonic()
        self.batch = await self.provider.embed(request)
        self.elapsed_ms = (time.monotonic() - started) * 1000
        return self.batch


async def _sql_oracle(
    dsn: str, *, workspace_id: str, profile_fingerprint: str, vector: tuple[float, ...], limit: int
) -> tuple[list[dict[str, Any]], float, int]:
    started = time.monotonic()
    async with await psycopg.AsyncConnection.connect(dsn) as connection:
        await connection.execute("SET TRANSACTION READ ONLY")
        await connection.execute("SELECT set_config('workbench.workspace_id',%s,true)", (workspace_id,))
        rows = await (
            await connection.execute(
                "SELECT c.chunk_id,c.source_id,c.version_id,e.vector <=> %s::vector AS distance,"
                "count(*) OVER() AS total FROM workbench.embedding_vectors e "
                "JOIN workbench.chunk_embeddings m "
                "USING(workspace_id,profile_fingerprint,processing_digest,input_hash) "
                "JOIN workbench.chunks c ON (c.workspace_id,c.chunk_id,c.source_id,c.version_id,c.content_hash)="
                "(m.workspace_id,m.chunk_id,m.source_id,m.version_id,m.expected_content_hash) "
                "JOIN workbench.source_versions s ON (s.workspace_id,s.source_id,s.version_id)="
                "(c.workspace_id,c.source_id,c.version_id) "
                "WHERE c.workspace_id=%s AND e.profile_fingerprint=%s AND s.status='active' "
                'ORDER BY distance,c.chunk_id COLLATE "C" LIMIT %s',
                (Vector(list(vector)).to_text(), workspace_id, profile_fingerprint, limit),
            )
        ).fetchall()
    return (
        [dict(zip(("chunk_id", "source_id", "source_version_id", "score"), row[:4], strict=True)) for row in rows],
        (time.monotonic() - started) * 1000,
        rows[0][4] if rows else 0,
    )


def _audit_response(payload: dict[str, Any], oracle: list[dict[str, Any]], *, trace_id: str) -> None:
    if payload.get("trace_id") != trace_id or not payload.get("run_id") or payload.get("mode") != "live":
        raise EvaluationIntegrityError("DENSE_TRACE_PROVENANCE_MISMATCH")
    results = payload["results"]
    if len(results) != len(oracle):
        raise EvaluationIntegrityError("DENSE_SQL_RESULT_COUNT_MISMATCH")
    for index, (result, expected) in enumerate(zip(results, oracle, strict=True), 1):
        if (
            any(result[key] != expected[key] for key in ("chunk_id", "source_id", "source_version_id"))
            or result["rank"] != index
            or result["score_type"] != "cosine_distance"
            or not math.isclose(result["score"], expected["score"], rel_tol=1e-6, abs_tol=1e-7)
        ):
            raise EvaluationIntegrityError("DENSE_SQL_DISTANCE_OR_IDENTITY_MISMATCH")


async def _evaluate_http(
    runtime: BackfillRuntime, fixture: EvaluationFixture, registry: ProfileRegistry, *, dsn: str, endpoint: str
) -> dict[str, Any]:
    observed = _ObservedEmbedding(runtime.adapter)

    async def readiness() -> None:
        await runtime.governor.check_ready_async()
        await runtime.adapter.check_ready_async()

    dense = DenseService(
        runtime.persistence,
        embedding=observed,
        profile=runtime.profile,
        counter=runtime.counter,
        registry=registry,
        readiness=readiness,
        capacity_policy_id=runtime.capacity.policy_id,
    )
    application = create_app(settings=ApiSettings(), persistence=runtime.persistence, dense=dense, registry=registry)
    context = WorkspaceContext(workspace_id=fixture.workspace_id, trace_id="dense-evaluation")
    records: list[dict[str, Any]] = []
    lexical_records: list[dict[str, Any]] = []
    timings: dict[str, list[float]] = {
        name: []
        for name in (
            "query_embedding_wall_ms",
            "provider_inference_ms",
            "vector_search_stage_ms",
            "sql_oracle_wall_ms",
            "http_wall_ms",
        )
    }
    coverage = await runtime.persistence.embedding_coverage(context, runtime.profile)
    if not coverage.ready or coverage.ready_embeddings < 100 or coverage.index_generation is None:
        raise EvaluationIntegrityError("DENSE_REQUIRES_100_REAL_PERSISTED_VECTORS")
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1:8011") as client,
    ):
        capabilities = (await client.get("/api/v1/capabilities")).json()
        if _PROFILE_ID not in {profile["profile_id"] for profile in capabilities["profiles"]}:
            raise EvaluationIntegrityError("DENSE_CAPABILITY_NOT_EXECUTABLE")
        for query in fixture.queries:
            response = await _dense_query(
                client, endpoint=endpoint, workspace_id=fixture.workspace_id, text=query.text, timings=timings
            )
            if response.status_code != 200 or observed.batch is None:
                raise EvaluationIntegrityError(f"DENSE_HTTP_{response.status_code}")
            payload = response.json()
            if payload["request_id"] != response.headers.get("x-request-id"):
                raise EvaluationIntegrityError("DENSE_HTTP_REQUEST_CORRELATION_MISMATCH")
            oracle, elapsed, count = await _sql_oracle(
                dsn,
                workspace_id=fixture.workspace_id,
                profile_fingerprint=runtime.profile.fingerprint,
                vector=observed.batch.vectors[0],
                limit=10,
            )
            if observed.trace_id is None:
                raise EvaluationIntegrityError("MISSING_MODEL_REQUEST_TRACE")
            _audit_response(payload, oracle, trace_id=observed.trace_id)
            if count != coverage.ready_embeddings:
                raise EvaluationIntegrityError("DENSE_ORACLE_COVERAGE_MISMATCH")
            independent_hits = await runtime.persistence.exact_embedding_search(
                context, runtime.profile, observed.batch.vectors[0], limit=10
            )
            record = evaluate_query(
                fixture,
                query,
                independent_hits,
                profile_fingerprint=runtime.profile.fingerprint,
                index_generation=coverage.index_generation,
            )
            record["trace_id"] = payload["trace_id"]
            record["request_id"] = payload["request_id"]
            record["run_id"] = payload["run_id"]
            record["stages"] = payload["stages"]
            record["sql_oracle_agrees"] = True
            records.append(record)
            timings["query_embedding_wall_ms"].append(observed.elapsed_ms)
            timings["sql_oracle_wall_ms"].append(elapsed)
            stages = {stage["stage"]: stage for stage in payload["stages"]}
            timings["vector_search_stage_ms"].append(stages["vector_search"]["duration_ms"])
            lexical = await client.post(
                f"/api/v1/workspaces/{fixture.workspace_id}/search",
                json={
                    "query": query.text,
                    "top_k": 10,
                    "profile_id": "postgres-fts-baseline",
                    "expected_profile_revision": "postgres-fts-baseline-r1",
                },
            )
            if lexical.status_code != 200:
                raise EvaluationIntegrityError("LEXICAL_REGRESSION_DURING_DENSE_EVALUATION")
            ranked = [hit["chunk_id"] for hit in lexical.json()["results"]]
            lexical_records.append(
                {
                    "query_id": query.query_id,
                    "ranked_chunk_ids": ranked,
                    "metrics": {str(k): score_ranking(query.relevance, ranked, cutoff=k) for k in (1, 5, 10)},
                }
            )
        exact_cases = []
        for source in [item for item in fixture.sources if item.workspace_id == fixture.workspace_id and item.active][
            :10
        ]:
            chunk = next(item for item in source.chunks if item.role == "primary")
            query_text = " ".join(chunk.content.split()[:6])
            response = await client.post(
                f"/api/v1/workspaces/{fixture.workspace_id}/search",
                json={
                    "query": query_text,
                    "top_k": 10,
                    "profile_id": "postgres-fts-baseline",
                    "expected_profile_revision": "postgres-fts-baseline-r1",
                },
            )
            if response.status_code != 200:
                raise EvaluationIntegrityError("EXACT_LEXICAL_HTTP_UNAVAILABLE")
            ids = [hit["chunk_id"] for hit in response.json()["results"]]
            exact_cases.append(
                {
                    "query_hash": hashlib.sha256(query_text.encode()).hexdigest(),
                    "expected_chunk_id": chunk.chunk_id,
                    "ranked_chunk_ids": ids,
                    "expected_in_top10": chunk.chunk_id in ids,
                }
            )
    return {
        "status": "PASS",
        "fixture_id": fixture.fixture_id,
        "fixture_digest": hashlib.sha256(fixture.model_dump_json().encode()).hexdigest(),
        "fixture_workspace_mapping": "main workspace mapped to development for existing HTTP authorization",
        "coverage": coverage.model_dump(mode="json"),
        "semantic_queries": len(records),
        "lexical_paraphrase_queries": len(lexical_records),
        "lexical_exact_queries": len(exact_cases),
        "profile_id": _PROFILE_ID,
        "profile_revision": _PROFILE_REVISION,
        "model_profile_fingerprint": runtime.profile.fingerprint,
        "model_revision": runtime.profile.model_revision,
        "model_digest": runtime.profile.model_digest,
        "quality": summarize_evaluation(records),
        "cases": records,
        "lexical_comparison": lexical_records,
        "lexical_exact_cases": exact_cases,
        "timings": {name: _distribution(values) for name, values in timings.items()},
        "timing_scope": (
            "wall clocks: governed adapter includes preparation, queue, HTTP and attestation; "
            "SQL oracle includes connection"
        ),
        "gpu_kernel_time": "NOT_MEASURED_PROVIDER_DOES_NOT_EXPOSE_KERNEL_TIMING",
        "provider_inference_scope": (
            "TEI te_request_inference_duration_sum/count delta; one real query per sample; seconds converted to ms"
        ),
        "ui_render_time": "NOT_MEASURED_ASGI_HTTP_ONLY",
        "relevance_labels": "fixed synthetic labels; no independent human or production qualification",
        "sql_oracle": "independently issued read-only exact pgvector SQL under application role and workspace RLS",
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    run_id = uuid4().hex
    database = _database(f"rag_test_{uuid4().hex}", run_id)
    await asyncio.to_thread(_create_database, database)
    initialized = False
    try:
        await asyncio.to_thread(migrate, database.admin_dsn)
        repository = PostgresPersistence(database.app_dsn)
        await repository.start()
        try:
            await repository.create_workspace(
                WorkspaceContext(workspace_id=_OWNER_WORKSPACE),
                Workspace(
                    workspace_id=_OWNER_WORKSPACE,
                    name="Disposable dense evaluation owner",
                    metadata=_owner_metadata(database),
                ),
            )
            initialized = True
            fixture = _http_fixture()
            # The real runtime requires an existing, tenant-owned workspace before it opens.
            await _ensure_fixture_workspace(repository, fixture, fixture.workspace_id)
        finally:
            await repository.close()
        async with open_backfill_runtime(
            dsn=database.app_dsn,
            model_directory=args.model_directory,
            capacity_config=args.capacity_config,
            context=WorkspaceContext(workspace_id="development"),
            endpoint=args.endpoint,
            container=args.container,
        ) as runtime:
            phases = await prepare_evaluation_vectors(runtime, fixture)
            registry = _dense_registry(runtime)
            await asyncio.to_thread(sync_registry, database.admin_dsn, registry)
            await asyncio.to_thread(
                promote_profile,
                database.admin_dsn,
                workspace_id="development",
                profile_id=_PROFILE_ID,
                profile_revision=_PROFILE_REVISION,
            )
            report = await _evaluate_http(runtime, fixture, registry, dsn=database.app_dsn, endpoint=args.endpoint)
            report["application_restart"] = await _restart_http(
                runtime, registry, fixture=fixture, dsn=database.app_dsn, first=report["cases"][0]
            )
            report["preparation_phases"] = phases
            report["admission"] = runtime.governor.summary()
            if getattr(args, "serve_seconds", 0):
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                await _serve_browser(runtime, registry, dsn=database.app_dsn, args=args)
        return report
    finally:
        await asyncio.to_thread(_drop_database, database, created_here=not initialized)


async def _restart_http(
    runtime: BackfillRuntime, registry: ProfileRegistry, *, fixture: EvaluationFixture, dsn: str, first: dict[str, Any]
) -> dict[str, Any]:
    async def readiness() -> None:
        await runtime.governor.check_ready_async()
        await runtime.adapter.check_ready_async()

    repository = PostgresPersistence(dsn)
    observed = _ObservedEmbedding(runtime.adapter)
    service = DenseService(
        repository,
        embedding=observed,
        profile=runtime.profile,
        counter=runtime.counter,
        registry=registry,
        capacity_policy_id=runtime.capacity.policy_id,
        readiness=readiness,
    )
    application = create_app(settings=ApiSettings(), persistence=repository, dense=service, registry=registry)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1:8011") as client,
    ):
        response = await client.post(
            "/api/v1/workspaces/development/search",
            json={
                "query": fixture.queries[0].text,
                "top_k": 10,
                "profile_id": _PROFILE_ID,
                "expected_profile_revision": _PROFILE_REVISION,
            },
        )
        if response.status_code != 200 or observed.batch is None or observed.trace_id is None:
            raise EvaluationIntegrityError("DENSE_RESTART_HTTP_UNAVAILABLE")
        payload = response.json()
        oracle, _, count = await _sql_oracle(
            dsn,
            workspace_id=fixture.workspace_id,
            profile_fingerprint=runtime.profile.fingerprint,
            vector=observed.batch.vectors[0],
            limit=10,
        )
        _audit_response(payload, oracle, trace_id=observed.trace_id)
        original_ids = [hit["chunk_id"] for hit in first["hits"]]
        if (
            count < 100
            or [hit["chunk_id"] for hit in payload["results"]] != original_ids
            or payload["model_digest"] != runtime.profile.model_digest
            or payload["trace_id"] == first["trace_id"]
            or payload["run_id"] == first["run_id"]
        ):
            raise EvaluationIntegrityError("DENSE_RESTART_PERSISTENCE_MISMATCH")
        differences = [
            abs(hit["score"] - old["distance"]) for hit, old in zip(payload["results"], first["hits"], strict=True)
        ]
        if max(differences) > 1e-5:
            raise EvaluationIntegrityError("DENSE_RESTART_DISTANCE_DRIFT")
    return {
        "status": "PASS",
        "scope": "new FastAPI app/lifespan and new PostgreSQL pool; same actual model/governor process",
        "source_chunk_ids_unchanged": True,
        "model_digest": runtime.profile.model_digest,
        "index_generation": payload["index_generation"],
        "new_trace_id": payload["trace_id"],
        "new_run_id": payload["run_id"],
        "maximum_distance_difference": max(differences),
        "repeat_query_distance_tolerance": 1e-5,
        "independent_sql_oracle_agrees": True,
    }


async def _serve_browser(
    runtime: BackfillRuntime, registry: ProfileRegistry, *, dsn: str, args: argparse.Namespace
) -> None:
    async def readiness() -> None:
        await runtime.governor.check_ready_async()
        await runtime.adapter.check_ready_async()

    repository = PostgresPersistence(dsn)
    dense = DenseService(
        repository,
        embedding=runtime.adapter,
        profile=runtime.profile,
        counter=runtime.counter,
        registry=registry,
        capacity_policy_id=runtime.capacity.policy_id,
        readiness=readiness,
    )
    application = create_app(settings=ApiSettings(), persistence=repository, dense=dense, registry=registry)
    server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=args.serve_port, access_log=False))
    task = asyncio.create_task(server.serve())
    started = time.monotonic()
    try:
        while not task.done() and time.monotonic() - started < args.serve_seconds:
            if args.stop_file is not None and args.stop_file.exists():
                break
            await asyncio.sleep(0.25)
    finally:
        server.should_exit = True
        await task


def main() -> int:
    """Refuse GPU/database work without explicit opt-in and fresh measured capacity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--capacity-config", type=Path, required=True)
    parser.add_argument("--model-directory", type=Path, default=Path("A:/AI/TEI/qwen3-4b"))
    parser.add_argument("--endpoint", default="http://127.0.0.1:8082")
    parser.add_argument("--container", default="rag-workbench-embedding-1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serve-seconds", type=int, default=0)
    parser.add_argument("--serve-port", type=int, default=8013)
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required for real-model disposable dense evaluation")
    if not 0 <= args.serve_seconds <= 600 or not 1 <= args.serve_port <= 65535:
        parser.error("browser server requires 0..600 seconds and a valid loopback port")
    try:
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
            report = runner.run(_run(args))
    except Exception as error:
        print(json.dumps({"status": "FAIL", "category": type(error).__name__}))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "semantic_queries": report["semantic_queries"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
