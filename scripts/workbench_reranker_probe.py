"""Measure the pinned local reranker with bounded synthetic and shared-TEI traffic."""

import argparse
import asyncio
import json
import math
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx

from apps.workbench.embedding.embedding_adapters import TeiEmbeddingAdapter
from apps.workbench.embedding.embedding_dispatch import QualificationCapacityPolicy, QualificationEmbeddingGovernor
from apps.workbench.reranking.local_reranker import LocalReranker, RerankErrorCode, RerankFailure
from scripts.workbench_embedding_capacity_benchmark import _calibration_profile
from scripts.workbench_embedding_qualify import LocalDeploymentVerifier, _distribution, _gpu, _request

_RERANKER = "rag-workbench-reranker-1"
_EMBEDDING = "rag-workbench-embedding-1"
_TEI = "http://127.0.0.1:8082"
_DEPTHS = (10, 20, 50)
_CONTROLS = (
    (
        "en",
        "What is the western site's retry interval?",
        "The eastern site retries after 30 seconds.",
        "The western site retries after 30 seconds.",
    ),
    (
        "ru",
        "При какой температуре отключается насос северной станции?",
        "Южный насос отключается при 85 градусах.",
        "Насос северной станции отключается при 85 градусах.",
    ),
    (
        "uk",
        "Коли починається заняття з фізики?",
        "Заняття з хімії починається о 14:00.",
        "Заняття з фізики починається о 14:00.",
    ),
    (
        "code",
        "Which function in the calendar module exports a date as ISO text?",
        "def parse_iso_date(value: str): return date.fromisoformat(value)",
        "def format_date(value: date) -> str: return value.isoformat()",
    ),
)


def _docker(*arguments: str) -> str:
    return subprocess.run(["docker", *arguments], check=True, capture_output=True, text=True, timeout=12).stdout.strip()


def _container() -> dict[str, Any]:
    state = json.loads(_docker("inspect", "--format", "{{json .State}}", _RERANKER))
    return {
        "id": _docker("inspect", "--format", "{{.Id}}", _RERANKER),
        "image": _docker("inspect", "--format", "{{.Image}}", _RERANKER),
        "started_at": state["StartedAt"],
        "status": state["Status"],
        "health": state.get("Health", {}).get("Status"),
        "restarts": int(_docker("inspect", "--format", "{{.RestartCount}}", _RERANKER)),
    }


def _memory() -> list[dict[str, str]]:
    return [
        json.loads(line)
        for line in _docker(
            "stats",
            "--no-stream",
            "--format",
            '{"name":"{{.Name}}","memory":"{{.MemUsage}}","cpu":"{{.CPUPerc}}"}',
            _RERANKER,
            _EMBEDDING,
        ).splitlines()
    ]


def _documents(negative: str, primary: str, depth: int) -> tuple[str, ...]:
    padding = tuple(
        f"Station {index}. " + "Measurements from unrelated stations are archived once per minute. " * 35
        for index in range(depth - 2)
    )
    return (negative, primary, *padding)


def _latency(samples: list[float]) -> dict[str, float]:
    return {**_distribution(samples), "p99": sorted(samples)[math.ceil(0.99 * len(samples)) - 1]}


async def _controls(reranker: LocalReranker) -> dict[str, object]:
    oversize = "standalone " * 5000
    try:
        await reranker.rank(_CONTROLS[0][1], (oversize,))
    except RerankFailure as error:
        rejection = error.code.value
        if error.code != RerankErrorCode.INPUT_REJECTED:
            raise
    else:
        raise RuntimeError("Oversized formatted pair was accepted")
    return {"oversize_rejected": rejection}


async def _isolated(reranker: LocalReranker) -> dict[str, object]:
    output: dict[str, object] = {}
    for depth in _DEPTHS:
        rows = [
            (family, await reranker.rank(query, _documents(negative, primary, depth)))
            for _ in range(3)
            for family, query, negative, primary in _CONTROLS
        ]
        elapsed = [result.elapsed_ms for _, result in rows]
        pairs = len(rows) * depth
        output[str(depth)] = {
            "queries": len(rows),
            "pairs": pairs,
            "batches": sum(len(result.batch_latencies_ms) for _, result in rows),
            "first_rank_counts": {
                family: sum(result.indices[0] == 1 for key, result in rows if key == family) for family, *_ in _CONTROLS
            },
            "query_ms": _latency(elapsed),
            "batch_ms": _latency([value for _, result in rows for value in result.batch_latencies_ms]),
            "ms_per_pair_amortized": sum(elapsed) / pairs,
            "pairs_per_second": pairs / (sum(elapsed) / 1000),
        }
    return output


async def _shared(reranker: LocalReranker, directory: Path) -> dict[str, object]:
    async with httpx.AsyncClient(base_url=_TEI, trust_env=False, follow_redirects=False, timeout=10) as client:
        verifier = LocalDeploymentVerifier(directory, _EMBEDDING, client, endpoint=_TEI)
        identity = await verifier.initialize()
        profile = _calibration_profile(identity)
        governor = QualificationEmbeddingGovernor(
            QualificationCapacityPolicy(
                profile_id=profile.profile_id,
                profile_revision=profile.profile_revision,
                deployment_id=identity.deployment_id,
                policy_revision="finite-reranking-overlap-r1",
                max_attempts=40,
                max_total_tokens=8192,
                max_request_tokens=256,
                max_duration_seconds=120.0,
            )
        )
        adapter = TeiEmbeddingAdapter(
            profile, endpoint=_TEI, token_counter=verifier.counter, governor=governor, identity_verifier=verifier
        )
        timings: dict[str, list[float]] = {"tei_alone": [], "tei_then_rerank": [], "tei_overlap": []}
        overlap_tei: list[float] = []
        await governor.warm_up_async()
        try:
            await adapter.warm_up_async()
            for repeat in range(3):
                modes = tuple(timings) if repeat % 2 == 0 else tuple(reversed(timings))
                for family, query, negative, primary in _CONTROLS:
                    for mode in modes:
                        request = _request(profile, "query", [(f"{family}-{repeat}", query)])
                        started = time.monotonic()
                        if mode == "tei_overlap":
                            async with asyncio.TaskGroup() as tasks:
                                embedding = tasks.create_task(adapter.embed(request))
                                tasks.create_task(reranker.rank(query, _documents(negative, primary, 10)))
                                await embedding
                                overlap_tei.append((time.monotonic() - started) * 1000)
                        else:
                            await adapter.embed(request)
                            if mode == "tei_then_rerank":
                                await reranker.rank(query, _documents(negative, primary, 10))
                        timings[mode].append((time.monotonic() - started) * 1000)
            await verifier.finalize()
        finally:
            await adapter.close_async()
            await governor.close_async()
        return {
            "scope": "synthetic TEI queries only; sequential and overlapping reranker calls; no retrieval or database",
            "samples_per_arm": len(overlap_tei),
            "timings_ms": {name: _latency(values) for name, values in timings.items()},
            "tei_latency_during_overlap_ms": _latency(overlap_tei),
            "admission": governor.summary(),
        }


async def _probe(expected_id: str, embedding_directory: Path) -> dict[str, object]:
    before = _container()
    if before["id"] != expected_id or before["health"] != "healthy":
        raise RuntimeError("Expected local reranker container is unavailable")
    gpu: list[dict[str, Any]] = []
    memory: list[list[dict[str, str]]] = []
    stop = asyncio.Event()

    async def sample() -> None:
        while not stop.is_set():
            gpu.append(await asyncio.to_thread(_gpu))
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), 0.5)

    async def sample_memory() -> None:
        while not stop.is_set():
            memory.append(await asyncio.to_thread(_memory))
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), 2)

    async with LocalReranker(batch_size=16) as reranker, asyncio.TaskGroup() as observers:
        observers.create_task(sample())
        observers.create_task(sample_memory())
        try:
            controls = await _controls(reranker)
            isolated = await _isolated(reranker)
            try:
                shared = await _shared(reranker, embedding_directory)
            except (
                RuntimeError,
                OSError,
                ValueError,
                httpx.HTTPError,
                subprocess.SubprocessError,
                ExceptionGroup,
            ) as error:
                shared = {"status": "UNAVAILABLE", "failure": type(error).__name__}
        finally:
            stop.set()
    after = _container()
    if after != before:
        raise RuntimeError("Reranker runtime identity changed during measurement")
    return {
        "status": "MEASURED",
        "container": before,
        "controls": controls,
        "isolated": isolated,
        "shared": shared,
        "resources": {
            "gpu": gpu,
            "docker_stats": memory,
            "scope": "shared physical device and individual Docker container samples",
        },
    }


def main() -> int:
    """Run fixed synthetic probes and produce exclusive, content-free evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--embedding-model-directory", default=Path("A:/AI/TEI/qwen3-4b"), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        report = asyncio.run(_probe(args.container_id, args.embedding_model_directory))
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
