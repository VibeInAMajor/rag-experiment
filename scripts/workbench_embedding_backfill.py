"""Explicit measured-capacity embedding worker; startup never migrates or advertises dense HTTP search."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from pydantic import ValidationError

from apps.workbench.configuration.config import ApiSettings
from apps.workbench.configuration.document_processing import DocumentProcessingSettings
from apps.workbench.embedding.embedding import EmbeddingError, EmbeddingErrorCode, EmbeddingProfile
from apps.workbench.embedding.embedding_adapters import TeiEmbeddingAdapter
from apps.workbench.embedding.embedding_capacity import MeasuredEmbeddingCapacityPolicy, ProductionEmbeddingGovernor
from apps.workbench.embedding.embedding_config import validate_embedding_endpoint
from apps.workbench.embedding.embedding_ingestion import EmbeddingIngestionService
from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter
from apps.workbench.persistence.models import PersistenceError, WorkspaceContext
from apps.workbench.postgres.postgres import PostgresPersistence
from scripts.workbench_embedding_qualify import _DEFAULT_CONTAINER, _DEFAULT_ENDPOINT, LocalDeploymentVerifier


def load_capacity_configuration(path: Path) -> tuple[EmbeddingProfile, MeasuredEmbeddingCapacityPolicy]:
    """Read a bounded operator calibration envelope without treating its contents as runtime attestation."""
    try:
        with path.open("rb") as source:
            content = source.read(1_048_577)
        if len(content) > 1_048_576:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        data = json.loads(content)
        if not isinstance(data, dict) or not {"profile", "capacity"} <= data.keys() <= {
            "profile",
            "capacity",
            "report",
        }:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        profile = EmbeddingProfile.model_validate_json(json.dumps(data["profile"]))
        capacity = MeasuredEmbeddingCapacityPolicy.model_validate_json(json.dumps(data["capacity"]))
        if capacity.profile_fingerprint != profile.fingerprint:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        return profile, capacity
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED) from None


@dataclass(frozen=True)
class BackfillRuntime:
    """One operator-owned provider/governor/persistence composition shared with query diagnostics."""

    profile: EmbeddingProfile
    capacity: MeasuredEmbeddingCapacityPolicy
    counter: LocalQwenTokenCounter
    adapter: TeiEmbeddingAdapter
    governor: ProductionEmbeddingGovernor
    persistence: PostgresPersistence
    worker: EmbeddingIngestionService


@asynccontextmanager
async def open_backfill_runtime(
    *,
    dsn: str,
    model_directory: Path,
    capacity_config: Path,
    context: WorkspaceContext,
    endpoint: str = _DEFAULT_ENDPOINT,
    container: str = _DEFAULT_CONTAINER,
    processing: DocumentProcessingSettings | None = None,
) -> AsyncIterator[BackfillRuntime]:
    """Attest actual deployment, acquire its sole capacity owner and open the existing application database port."""
    profile, capacity = load_capacity_configuration(capacity_config)
    endpoint = validate_embedding_endpoint(endpoint)
    async with httpx.AsyncClient(base_url=endpoint, trust_env=False, follow_redirects=False, timeout=10) as client:
        verifier = LocalDeploymentVerifier(model_directory, container, client, endpoint=endpoint)
        identity = await verifier.initialize()
        governor = ProductionEmbeddingGovernor(capacity, profile=profile, identity=identity)
        await governor.warm_up_async()
        persistence = PostgresPersistence(dsn=dsn, max_size=4)
        adapter = TeiEmbeddingAdapter(
            profile, endpoint=endpoint, token_counter=verifier.counter, governor=governor, identity_verifier=verifier
        )
        try:
            await persistence.start()
            await persistence.preview_embedding_backfill(context, profile)
            await adapter.warm_up_async()
            worker = EmbeddingIngestionService(
                persistence, adapter, profile=profile, counter=verifier.counter, processing=processing
            )
            yield BackfillRuntime(
                profile=profile,
                capacity=capacity,
                counter=verifier.counter,
                adapter=adapter,
                governor=governor,
                persistence=persistence,
                worker=worker,
            )
            await verifier.finalize()
        finally:
            await adapter.close_async()
            await persistence.close()
            await governor.close_async()


async def run_backfill(
    runtime: BackfillRuntime,
    context: WorkspaceContext,
    *,
    max_steps: int = 10000,
    watch: bool = False,
    idle_seconds: float = 10.0,
) -> dict[str, Any]:
    """Enable scheduling and process bounded pages; unfinished/retryable work remains durable after exit."""
    if not 1 <= max_steps <= 1000000 or not 0 <= idle_seconds <= 300:
        raise ValueError("Backfill iteration and idle bounds are required")
    await runtime.persistence.register_embedding_profile(context, runtime.profile)
    enqueued = await runtime.persistence.enqueue_embedding_backfill(context, runtime.profile)
    steps = 0
    idle_since = monotonic()
    while watch or steps < max_steps:
        if await runtime.worker.process_one(context):
            steps += 1
            idle_since = monotonic()
            continue
        added = await runtime.persistence.enqueue_embedding_backfill(context, runtime.profile)
        enqueued += added
        if added:
            continue
        coverage = await runtime.persistence.embedding_coverage(context, runtime.profile)
        if not watch and (coverage.ready or monotonic() - idle_since >= idle_seconds):
            break
        await asyncio.sleep(0.5)
    coverage = await runtime.persistence.embedding_coverage(context, runtime.profile)
    return {
        "status": "READY" if coverage.ready else "NOT_READY",
        "coverage": coverage.model_dump(mode="json"),
        "enqueued": enqueued,
        "steps": steps,
        "worker": runtime.worker.statistics(),
        "admission": runtime.governor.summary(),
        "dense_http_enabled": False,
    }


async def _run(arguments: argparse.Namespace) -> dict[str, Any]:
    settings = ApiSettings.from_env()
    if settings.database_dsn is None:
        raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
    context = WorkspaceContext(workspace_id=arguments.workspace, trace_id="operator-embedding-backfill")
    if arguments.dry_run or arguments.status or arguments.disable or arguments.retry_job:
        profile, _ = load_capacity_configuration(arguments.capacity_config)
        persistence = PostgresPersistence(dsn=settings.database_dsn.get_secret_value())
        await persistence.start()
        try:
            if arguments.disable:
                await persistence.register_embedding_profile(context, profile, enabled=False)
                return {"status": "DISABLED", "vectors_deleted": False, "lexical_unchanged": True}
            if arguments.retry_job:
                job = await persistence.retry_embedding_job(context, arguments.retry_job)
                return {"status": "QUEUED", "job_id": job.job_id}
            coverage = (
                await persistence.preview_embedding_backfill(context, profile)
                if arguments.dry_run
                else await persistence.embedding_coverage(context, profile)
            )
            return {
                "status": "DRY_RUN" if arguments.dry_run else "READY" if coverage.ready else "NOT_READY",
                "coverage": coverage.model_dump(mode="json"),
                "provider_calls": 0,
            }
        finally:
            await persistence.close()
    async with open_backfill_runtime(
        dsn=settings.database_dsn.get_secret_value(),
        model_directory=arguments.model_directory,
        capacity_config=arguments.capacity_config,
        context=context,
        endpoint=arguments.endpoint,
        container=arguments.container,
        processing=settings.document_processing,
    ) as runtime:
        return await run_backfill(runtime, context, max_steps=arguments.max_steps, watch=arguments.watch)


def main() -> int:
    """Run explicitly configured local backfill; credentials, text and vectors never appear in output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capacity-config", type=Path, required=True)
    parser.add_argument(
        "--model-directory",
        type=Path,
        default=Path(os.environ.get("WORKBENCH_EMBEDDING_MODEL_DIRECTORY", "A:/AI/TEI/qwen3-4b")),
    )
    parser.add_argument("--endpoint", default=_DEFAULT_ENDPOINT)
    parser.add_argument("--container", default=_DEFAULT_CONTAINER)
    parser.add_argument("--workspace", default="development")
    parser.add_argument("--max-steps", type=int, default=10000)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--disable", action="store_true")
    group.add_argument("--retry-job")
    group.add_argument("--watch", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
        with asyncio.Runner(loop_factory=factory) as runner:
            report = runner.run(_run(arguments))
    except (EmbeddingError, PersistenceError, ValidationError, ValueError):
        print(json.dumps({"status": "FAILED", "code": "EMBEDDING_BACKFILL_UNAVAILABLE"}))
        return 1
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["status"] in {"READY", "DRY_RUN", "DISABLED", "QUEUED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
