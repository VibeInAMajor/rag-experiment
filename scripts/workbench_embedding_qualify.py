"""Explicit, local-only embedding qualification; default execution performs metadata checks only."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import socket
import statistics
import subprocess
import time
import unicodedata
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from apps.workbench.embedding.embedding import (
    EmbeddingBatch,
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingItem,
    EmbeddingProfile,
    EmbeddingRequest,
    EmbeddingRuntimeIdentity,
    prepare_embedding_request,
)
from apps.workbench.embedding.embedding_adapters import TeiEmbeddingAdapter
from apps.workbench.embedding.embedding_config import EmbeddingConfigurationError, validate_embedding_endpoint
from apps.workbench.embedding.embedding_dispatch import QualificationCapacityPolicy, QualificationEmbeddingGovernor
from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter

_REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"
_IMAGE = "sha256:d139efce84ee1d23405d64e4dc0b82d583c463fce3ff707eb65c47a8a1b7f69c"
_MODEL_PATH = f"/models/{_REVISION}"
_MODEL_ID = "Qwen/Qwen3-Embedding-4B"
_COMMAND = [
    "--disable-spans",
    "--model-id",
    _MODEL_PATH,
    "--served-model-name",
    _MODEL_ID,
    "--pooling",
    "last-token",
    "--dtype",
    "float16",
    "--max-concurrent-requests",
    "8",
    "--max-client-batch-size",
    "8",
    "--max-batch-tokens",
    "40960",
    "--payload-limit",
    "1048576",
    "--auto-truncate",
    "false",
]
_DEFAULT_ENDPOINT = "http://127.0.0.1:8082"
_DEFAULT_CONTAINER = "rag-workbench-embedding-1"
_COMPOSE_PROJECT = "rag-workbench-embedding"
_COMPOSE_SERVICE = "embedding"
_CACHE_VOLUME = "rag-workbench-embedding-qwen3-4b-5cf2132abc99"
_CACHE_LABELS = {"com.rag.workbench.project": _COMPOSE_PROJECT, "com.rag.workbench.model-revision": _REVISION}
_HEALTHCHECK = ["CMD", "curl", "--fail", "--silent", "--max-time", "2", "http://127.0.0.1/info"]
_WEIGHTS = {
    "model-00001-of-00002.safetensors": {
        "size": 4965826464,
        "sha256": "e70bfe3c970523fb7ef4eddffed2254ce3f1e7150c3de2af4342de129dd756f8",
    },
    "model-00002-of-00002.safetensors": {
        "size": 3077765624,
        "sha256": "ed1b87c8e9eb7e535a1a155e4fd00d9f4dba80e58a6db48a4c9f82cede7079c1",
    },
}
_ASSETS = (
    *_WEIGHTS,
    "tokenizer.json",
    "tokenizer_config.json",
    "config.json",
    "model.safetensors.index.json",
    "modules.json",
    "config_sentence_transformers.json",
    "1_Pooling/config.json",
)
_ROOT = Path(__file__).resolve().parents[1]
_PURPOSES: tuple[Literal["document", "query"], ...] = ("document", "query")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _command(arguments: list[str]) -> str:
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=20).stdout.strip()


def _asset_manifest(directory: Path) -> dict[str, Any]:
    _asset_stats(directory)
    result = {}
    for name in _ASSETS:
        path = directory / name
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        result[name] = {"size": path.stat().st_size, "sha256": digest}
    if any(result[name] != expected for name, expected in _WEIGHTS.items()):
        raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
    return result


def _asset_stats(directory: Path) -> dict[str, tuple[int, int]]:
    if any((directory / name).exists() for name in ("model.safetensors", "pytorch_model.bin")):
        raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
    return {name: ((directory / name).stat().st_size, (directory / name).stat().st_mtime_ns) for name in _ASSETS}


def _cache_volume() -> dict[str, Any]:
    volume = json.loads(_command(["docker", "volume", "inspect", _CACHE_VOLUME]))[0]
    labels = volume.get("Labels") or {}
    if (
        volume.get("Name") != _CACHE_VOLUME
        or volume.get("Driver") != "local"
        or volume.get("Options") not in (None, {})
        or any(labels.get(key) != value for key, value in _CACHE_LABELS.items())
    ):
        raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
    return {
        "name": volume["Name"],
        "driver": volume["Driver"],
        "mountpoint": volume["Mountpoint"],
        "ownership_labels": {key: labels[key] for key in _CACHE_LABELS},
    }


def _cached_asset_stats(container: str) -> dict[str, tuple[int, str, str]]:
    script = (
        'if [ -e "$1/model.safetensors" ] || [ -e "$1/pytorch_model.bin" ]; then '
        'printf "ALTERNATE_WEIGHTS\\n"; exit 0; fi; shift; stat --printf "%n|%s|%y|%z\\n" -- "$@"'
    )
    output = _command(
        [
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            script,
            "workbench-cache-stat",
            _MODEL_PATH,
            *(f"{_MODEL_PATH}/{name}" for name in _ASSETS),
        ]
    )
    result = {}
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 4 or not fields[0].startswith(f"{_MODEL_PATH}/"):
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        name = fields[0][len(_MODEL_PATH) + 1 :]
        if name not in _ASSETS or name in result or not fields[1].isdigit():
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        result[name] = (int(fields[1]), fields[2], fields[3])
    if set(result) != set(_ASSETS):
        raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
    return result


def _cached_asset_manifest(container: str) -> dict[str, Any]:
    before = _cached_asset_stats(container)
    output = _command(["docker", "exec", container, "sha256sum", "--", *(f"{_MODEL_PATH}/{name}" for name in _ASSETS)])
    result = {}
    for line in output.splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) != 2 or not fields[1].startswith(f"{_MODEL_PATH}/"):
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        name = fields[1][len(_MODEL_PATH) + 1 :]
        if (
            name not in before
            or name in result
            or len(fields[0]) != 64
            or any(character not in "0123456789abcdef" for character in fields[0])
        ):
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        result[name] = {"size": before[name][0], "sha256": fields[0]}
    if set(result) != set(_ASSETS) or before != _cached_asset_stats(container):
        raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
    return result


def _deployment(container: str, directory: Path, *, endpoint: str = _DEFAULT_ENDPOINT) -> dict[str, Any]:
    address = urlsplit(validate_embedding_endpoint(endpoint))
    bindings = {"80/tcp": [{"HostIp": address.hostname, "HostPort": str(address.port)}]}
    raw = json.loads(_command(["docker", "inspect", container]))[0]
    labels = raw["Config"].get("Labels", {})
    healthcheck = raw["Config"].get("Healthcheck")
    volume = _cache_volume()
    model_mounts = [mount for mount in raw["Mounts"] if mount["Destination"] == "/models"]
    if (
        raw["Image"] != _IMAGE
        or raw.get("Name") != f"/{container}"
        or labels.get("com.docker.compose.project") != _COMPOSE_PROJECT
        or labels.get("com.docker.compose.service") != _COMPOSE_SERVICE
        or raw["State"]["Running"] is not True
        or raw["Config"]["Entrypoint"] != ["./entrypoint.sh"]
        or raw["Config"]["Cmd"] != _COMMAND
        or not isinstance(healthcheck, dict)
        or healthcheck.get("Test") != _HEALTHCHECK
        or raw["HostConfig"]["PortBindings"] != bindings
        or raw["NetworkSettings"]["Ports"] != bindings
        or len(raw["Mounts"]) != 1
        or len(model_mounts) != 1
        or model_mounts[0]["Type"] != "volume"
        or model_mounts[0].get("Name") != _CACHE_VOLUME
        or model_mounts[0]["RW"] is not False
        or model_mounts[0]["Source"] != volume["mountpoint"]
    ):
        raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
    return {
        "container_id": raw["Id"],
        "source_model_directory": str(directory.resolve()),
        "container_name": raw["Name"],
        "compose_project": labels["com.docker.compose.project"],
        "compose_service": labels["com.docker.compose.service"],
        "endpoint": validate_embedding_endpoint(endpoint),
        "image_id": raw["Image"],
        "started_at": raw["State"]["StartedAt"],
        "command": raw["Config"]["Cmd"],
        "entrypoint": raw["Config"]["Entrypoint"],
        "healthcheck_test": healthcheck["Test"],
        "cache_volume": volume,
        "configured_port_bindings": raw["HostConfig"]["PortBindings"],
        "actual_port_bindings": raw["NetworkSettings"]["Ports"],
        "model_mount": {key: model_mounts[0][key] for key in ("Source", "Destination", "RW")},
    }


def _verify_model_info(info: dict[str, Any]) -> None:
    if (
        info.get("model_id") != _MODEL_PATH
        or info.get("served_model_name") != _MODEL_ID
        or info.get("version") != "1.9.4"
        or info.get("sha") != "e80ef225ed0e6cb1717ce632a6a84b6cf211bb67"
        or info.get("model_dtype") != "float16"
        or info.get("model_type") != {"embedding": {"pooling": "last_token"}}
    ):
        raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)


class LocalDeploymentVerifier:
    """Bind this operator-selected deployment to pinned local assets before and after every dispatch."""

    def __init__(
        self, directory: Path, container: str, client: httpx.AsyncClient, *, endpoint: str = _DEFAULT_ENDPOINT
    ) -> None:
        self.directory = directory
        self.container = container
        self.client = client
        self.endpoint = validate_embedding_endpoint(endpoint)
        if str(client.base_url).rstrip("/") != self.endpoint:
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        self.counter = LocalQwenTokenCounter(directory)
        self.manifest: dict[str, Any] = {}
        self.evidence: dict[str, Any] = {}
        self._stats: dict[str, tuple[int, int]] = {}
        self._cache_stats: dict[str, tuple[int, str, str]] = {}
        self._identity: EmbeddingRuntimeIdentity | None = None

    async def initialize(self) -> EmbeddingRuntimeIdentity:
        """Hash all assets and require the actual deployment metadata before any inference."""
        before = await asyncio.to_thread(_asset_stats, self.directory)
        self.manifest = await asyncio.to_thread(_asset_manifest, self.directory)
        self._stats = await asyncio.to_thread(_asset_stats, self.directory)
        if before != self._stats:
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        deployment = await asyncio.to_thread(_deployment, self.container, self.directory, endpoint=self.endpoint)
        self._cache_stats = await asyncio.to_thread(_cached_asset_stats, self.container)
        cached_manifest = await asyncio.to_thread(_cached_asset_manifest, self.container)
        if cached_manifest != self.manifest:
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        response = await self.client.get("/info")
        response.raise_for_status()
        info = response.json()
        _verify_model_info(info)
        self.evidence = {
            "deployment": deployment,
            "assets": self.manifest,
            "cached_assets": cached_manifest,
            "info": info,
        }
        self._identity = EmbeddingRuntimeIdentity(
            deployment_id=f"tei-{deployment['container_id'][:24]}",
            adapter_id="tei-openai",
            model_digest=_digest({"model_revision": _REVISION, "files": _WEIGHTS}),
            tokenizer_digest=_digest(self.counter.manifest()),
            tokenizer_revision=self.counter.counter_revision,
            served_model_id=info["served_model_name"],
            info_digest=_digest(info),
            runtime_revision="tei-1.9.4",
            evidence_digest=_digest(self.evidence),
        )
        return self._identity

    async def verify(self) -> EmbeddingRuntimeIdentity:
        """Detect changed files, container replacement, restart or runtime metadata drift."""
        if self._identity is None:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        stats = await asyncio.to_thread(_asset_stats, self.directory)
        cache_stats = await asyncio.to_thread(_cached_asset_stats, self.container)
        deployment = await asyncio.to_thread(_deployment, self.container, self.directory, endpoint=self.endpoint)
        response = await self.client.get("/info")
        response.raise_for_status()
        if (
            stats != self._stats
            or cache_stats != self._cache_stats
            or deployment != self.evidence["deployment"]
            or _digest(response.json()) != self._identity.info_digest
        ):
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        return self._identity

    async def finalize(self) -> None:
        """Rehash the complete weights and input-policy assets after the bounded experiment."""
        await self.verify()
        final_manifest = await asyncio.to_thread(_asset_manifest, self.directory)
        final_cache = await asyncio.to_thread(_cached_asset_manifest, self.container)
        if final_manifest != self.manifest or final_cache != self.manifest:
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        await self.verify()


def _fixtures() -> list[tuple[str, str]]:
    groups = {
        "en": [
            "How do I restore PostgreSQL after an interrupted transaction?",
            "Only the active source version is visible in a consistent search snapshot.",
            "A failed background job retries without publishing incomplete chunks.",
            "Tenant isolation prevents another workspace from reading private documents.",
            "The embedding dimension is fixed by the immutable model profile.",
            "Cafe\u0301, naïve Unicode, emoji 🧪 and a literal <|endoftext|> are data.",
        ],
        "ru": [
            "Как восстановить PostgreSQL после прерванной транзакции?",
            "В согласованном снимке поиска видна только активная версия источника.",
            "Повтор фоновой задачи не публикует незавершённые фрагменты.",
            "Изоляция арендаторов защищает частные документы другого пространства.",
            "Размерность вектора закреплена неизменяемым профилем модели.",
            "Проверяем длинное слово, кавычки «пример», перенос\nстроки и число 2560.",
        ],
        "uk": [
            "Як відновити PostgreSQL після перерваної транзакції?",
            "В узгодженому знімку пошуку видно лише активну версію джерела.",
            "Повтор фонової задачі не публікує незавершені фрагменти.",
            "Ізоляція орендарів захищає приватні документи іншого простору.",
            "Розмірність вектора закріплена незмінним профілем моделі.",
            "Перевіряємо апостроф, літери ї є ґ, емодзі 🔎 та новий\nрядок.",
        ],
        "code": [
            "def active_version(source_id: str) -> str:\n    return source_id\n",
            "SELECT chunk_id FROM workbench.chunks WHERE source_version_id = $1;",
            '{"profile_id":"qwen-local","normalized":true,"dimensions":2560}',
            "async function search(query: string) { return await client.search(query); }",
            "BEGIN; UPDATE source_versions SET active = TRUE WHERE id = $1; COMMIT;",
            "# Unicode sentinel\nname = 'джерело'\nassert len(name) > 0\n",
        ],
        "long": [
            "Durable indexing preserves source identity and consistent snapshots. " * 32,
            "Согласованность поиска и безопасная публикация версии источника. " * 48,
            "Узгодженість пошуку та безпечна публікація версії джерела. " * 48,
            "def publish(version):\n    return version.active and version.complete\n" * 32,
            "alpha beta gamma delta; " * 512,
            "boundary " * 2000,
        ],
    }
    return [(f"{group}-{index}", text) for group, texts in groups.items() for index, text in enumerate(texts)]


def _request(
    profile: EmbeddingProfile, purpose: Literal["query", "document"], texts: list[tuple[str, str]]
) -> EmbeddingRequest:
    return EmbeddingRequest(
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        task_kind=purpose,
        items=tuple(
            EmbeddingItem(item_id=item_id, text=text, input_hash=hashlib.sha256(text.encode()).hexdigest())
            for item_id, text in texts
        ),
        deadline=time.monotonic() + profile.timeout_seconds,
        trace_id="local-model-qualification",
    )


def _batches(
    profile: EmbeddingProfile,
    counter: LocalQwenTokenCounter,
    purpose: Literal["query", "document"],
    texts: list[tuple[str, str]],
) -> list[list[tuple[str, str]]]:
    batches: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    tokens = 0
    for item in texts:
        prepared = prepare_embedding_request(profile, _request(profile, purpose, [item]), counter)[0]
        if current and (
            len(current) == profile.max_batch_items or tokens + prepared.token_count > profile.max_batch_tokens
        ):
            batches.append(current)
            current, tokens = [], 0
        current.append(item)
        tokens += prepared.token_count
    if current:
        batches.append(current)
    return batches


def _comparison(left: tuple[float, ...], right: tuple[float, ...]) -> dict[str, float]:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return {"cosine": dot / norm, "max_absolute_difference": max(abs(a - b) for a, b in zip(left, right, strict=True))}


def _distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "min": min(values),
        "p50": statistics.median(values),
        "p95": ordered[math.ceil(len(values) * 0.95) - 1],
        "max": max(values),
    }


def _gpu() -> dict[str, Any]:
    fields = (
        _command(
            [
                "nvidia-smi",
                "--query-gpu=name,uuid,memory.total,memory.used,driver_version",
                "--format=csv,noheader,nounits",
            ]
        )
        .splitlines()[0]
        .split(",")
    )
    return {
        "name": fields[0].strip(),
        "uuid": fields[1].strip(),
        "total_mib": int(fields[2]),
        "used_mib": int(fields[3]),
        "driver": fields[4].strip(),
    }


async def _tokenizer_parity(verifier: LocalDeploymentVerifier) -> list[dict[str, Any]]:
    from tokenizers import Tokenizer

    backend = Tokenizer.from_file(str(verifier.directory / "tokenizer.json"))
    backend.no_padding()
    backend.no_truncation()
    selected = [_fixtures()[index] for index in (0, 5, 6, 12, 18)]
    selected.append(
        (
            "query-format",
            "Instruct: Given a web search query, retrieve relevant passages that answer the query"
            "\nQuery: PostgreSQL recovery",
        )
    )
    result = []
    for item_id, text in selected:
        normalized = unicodedata.normalize("NFC", text)
        response = await verifier.client.post("/tokenize", json={"inputs": [normalized], "add_special_tokens": True})
        response.raise_for_status()
        actual = [token["id"] for token in response.json()[0]]
        expected = backend.encode(normalized, add_special_tokens=True).ids
        count = verifier.counter.count_tokens(normalized)
        if actual != expected or len(actual) != count:
            raise EmbeddingError(EmbeddingErrorCode.TOKENIZER_MISMATCH)
        result.append(
            {"item_id": item_id, "token_count": count, "exact_ids_match": True, "ids_sha256": _digest(actual)}
        )
    return result


def _cross_language(vectors: dict[tuple[str, str], tuple[float, ...]]) -> dict[str, Any]:
    result = {}
    for left, right in (("en", "ru"), ("en", "uk"), ("ru", "uk")):
        values = [
            _comparison(vectors[("document", f"{left}-{index}")], vectors[("document", f"{right}-{index}")])["cosine"]
            for index in range(5)
        ]
        result[f"{left}-{right}"] = _distribution(values)
    return result


async def _exercise(
    adapter: TeiEmbeddingAdapter, profile: EmbeddingProfile, counter: LocalQwenTokenCounter
) -> dict[str, Any]:
    texts = _fixtures()
    records = []
    vectors: dict[tuple[str, str], tuple[float, ...]] = {}
    durations: list[float] = []
    provider_tokens = 0

    async def dispatch(
        purpose: Literal["query", "document"], batch: list[tuple[str, str]], *, native: bool = False
    ) -> EmbeddingBatch:
        nonlocal provider_tokens
        request = _request(profile, purpose, batch)
        started = time.monotonic()
        output = await (adapter.probe_native(request) if native else adapter.embed(request))
        wall_ms = (time.monotonic() - started) * 1000
        if output.item_ids != tuple(item_id for item_id, _ in batch):
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        records.append(
            {
                "purpose": purpose,
                "item_ids": list(output.item_ids),
                "source_hashes": list(output.source_hashes),
                "sent_input_hashes": list(output.input_hashes),
                "token_counts": list(output.token_counts),
                "usage_tokens": output.usage_tokens,
                "usage_provenance": output.usage_provenance,
                "route": "native-diagnostic" if native else "openai",
                "adapter_duration_ms": output.duration_ms,
                "attested_wall_ms": wall_ms,
                "dimensions": len(output.vectors[0]),
                "norms": [math.sqrt(sum(value * value for value in vector)) for vector in output.vectors],
            }
        )
        if not native:
            durations.append(output.duration_ms)
            provider_tokens += output.usage_tokens or 0
        return output

    for purpose in _PURPOSES:
        for batch in _batches(profile, counter, purpose, texts):
            output = await dispatch(purpose, batch)
            vectors.update(
                ((purpose, item_id), vector) for item_id, vector in zip(output.item_ids, output.vectors, strict=True)
            )
    ordering = []
    for item in texts:
        output = await dispatch("document", [item])
        comparison = _comparison(vectors[("document", item[0])], output.vectors[0])
        if comparison["cosine"] < 0.995:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        ordering.append({"item_id": item[0], **comparison})
    repeatability = []
    native_parity = []
    for index in (0, 6, 12, 18, 24):
        item = texts[index]
        output = await dispatch("query", [item])
        comparison = _comparison(vectors[("query", item[0])], output.vectors[0])
        if comparison["cosine"] < 0.995:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        repeatability.append({"item_id": item[0], **comparison})
        native = await dispatch("query", [item], native=True)
        comparison = _comparison(output.vectors[0], native.vectors[0])
        if comparison["cosine"] < 0.995:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        native_parity.append({"item_id": item[0], **comparison})
    boundary = []
    for purpose in _PURPOSES:
        low, high = _boundary_repeats(profile, counter, purpose)
        output = await dispatch(purpose, [("boundary", "x " * low)])
        try:
            await adapter.embed(_request(profile, purpose, [("oversize", "x " * high)]))
        except EmbeddingError as error:
            if error.code != EmbeddingErrorCode.REQUEST_TOO_LARGE:
                raise
        else:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        boundary.append(
            {"purpose": purpose, "accepted_tokens": output.token_counts[0], "next_repeat_refused_before_dispatch": True}
        )
    return {
        "status": "PASS",
        "representative_texts": len(texts),
        "purposes": ["document", "query"],
        "records": records,
        "ordering_batch_vs_all_document_singles": ordering,
        "repeatability_query_batch_vs_singles": repeatability,
        "native_openai_parity": native_parity,
        "boundary": boundary,
        "cross_language_matched_document_cosine": _cross_language(vectors),
        "quality_claim": "descriptive synthetic diagnostics only; no relevance-quality acceptance claim",
        "first_observed_adapter_ms": durations[0],
        "warm_adapter_latency_ms": _distribution(durations[1:]),
        "warm_request_count": len(durations) - 1,
        "provider_reported_tokens": provider_tokens,
        "adapter_token_throughput_tokens_per_second": provider_tokens / (sum(durations) / 1000),
        "throughput_denominator": "sum of adapter call durations including input preparation and pre/post attestation",
        "cold_start": "not measured by this harness; first-observed is the first inference in this run",
        "qualified_concurrency": 1,
        "maximum_sustainable_concurrency": "NOT TESTED",
        "retries": 0,
        "production_sustainable_tpm": "NOT_QUALIFIED",
    }


def _boundary_repeats(
    profile: EmbeddingProfile, counter: LocalQwenTokenCounter, purpose: Literal["query", "document"]
) -> tuple[int, int]:
    low, high = 1, profile.max_tokens + 1
    while low + 1 < high:
        middle = (low + high) // 2
        try:
            prepare_embedding_request(profile, _request(profile, purpose, [("boundary", "x " * middle)]), counter)
        except EmbeddingError as error:
            if error.code != EmbeddingErrorCode.REQUEST_TOO_LARGE:
                raise
            high = middle
        else:
            low = middle
    return low, high


async def _negative_diagnostics(
    verifier: LocalDeploymentVerifier, profile: EmbeddingProfile, governor: QualificationEmbeddingGovernor
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("model_digest", "tokenizer_digest"):
        bad_profile = profile.model_copy(update={field: "0" * 64})
        adapter = TeiEmbeddingAdapter(
            bad_profile,
            endpoint=verifier.endpoint,
            token_counter=verifier.counter,
            governor=governor,
            identity_verifier=verifier,
        )
        try:
            await adapter.warm_up_async()
        except EmbeddingError as error:
            if error.code != EmbeddingErrorCode.IDENTITY_MISMATCH:
                raise
            result[f"{field}_mismatch"] = error.code.value
        else:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        finally:
            await adapter.close_async()

    class DriftVerifier:
        changed = False

        async def verify(self) -> EmbeddingRuntimeIdentity:
            identity = await verifier.verify()
            return identity.model_copy(update={"evidence_digest": "0" * 64}) if self.changed else identity

    drift = DriftVerifier()
    adapter = TeiEmbeddingAdapter(
        profile, endpoint=verifier.endpoint, token_counter=verifier.counter, governor=governor, identity_verifier=drift
    )
    try:
        await adapter.warm_up_async()
        drift.changed = True
        try:
            await adapter.embed(_request(profile, "query", [("drift", "Safe synthetic sentinel")]))
        except EmbeddingError as error:
            if error.code != EmbeddingErrorCode.IDENTITY_MISMATCH:
                raise
            result["simulated_trusted_attestation_drift"] = error.code.value
        else:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        try:
            await adapter.embed(_request(profile, "query", [("drift-repeat", "Safe synthetic sentinel")]))
        except EmbeddingError as error:
            if error.code != EmbeddingErrorCode.NOT_QUALIFIED:
                raise
            result["after_drift_provider_disabled"] = error.code.value
        else:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
    finally:
        await adapter.close_async()
    with socket.socket() as reserved_socket:
        reserved_socket.bind(("127.0.0.1", 0))
        port = reserved_socket.getsockname()[1]
        adapter = TeiEmbeddingAdapter(
            profile,
            endpoint=f"http://127.0.0.1:{port}",
            token_counter=verifier.counter,
            governor=governor,
            identity_verifier=verifier,
        )
        try:
            await adapter.warm_up_async()
        except EmbeddingError as error:
            if error.code != EmbeddingErrorCode.MODEL_UNAVAILABLE:
                raise
            result["simulated_client_unreachable_endpoint"] = error.code.value
        else:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        finally:
            await adapter.close_async()
    result["scope"] = (
        "real adapter and attestation; injected identity/client outage; dedicated TEI was not stopped or reloaded"
    )
    return result


async def run_qualification(
    *, directory: Path, container: str = _DEFAULT_CONTAINER, endpoint: str = _DEFAULT_ENDPOINT, run_model: bool = False
) -> dict[str, Any]:
    """Verify local metadata and optionally run the finite, shared-owner inference experiment."""
    endpoint = validate_embedding_endpoint(endpoint)
    async with httpx.AsyncClient(base_url=endpoint, trust_env=False, follow_redirects=False, timeout=10) as client:
        verifier = LocalDeploymentVerifier(directory, container, client, endpoint=endpoint)
        identity = await verifier.initialize()
        profile = EmbeddingProfile(
            profile_id="qwen3-embedding-4b-local",
            profile_revision="qwen3-4b-web-r1",
            provider_adapter_id="tei-openai",
            model_id=_MODEL_ID,
            model_revision=_REVISION,
            model_digest=identity.model_digest,
            tokenizer_digest=identity.tokenizer_digest,
            tokenizer_revision=identity.tokenizer_revision,
            dimensions=2560,
        )
        gpu = await asyncio.to_thread(_gpu)
        if "RTX 4090" not in gpu["name"]:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        report: dict[str, Any] = {
            "mode": "live" if run_model else "metadata_only",
            "identity": identity.model_dump(),
            "profile": profile.model_dump(exclude={"query_instruction"}),
            "profile_fingerprint": profile.fingerprint,
            "attestation": verifier.evidence,
            "tokenizer_manifest": verifier.counter.manifest(),
            "gpu": gpu,
            "attestation_limit": "trusted operator deployment chain and mounted assets; no GPU-memory attestation",
            "tokenizer_parity": await _tokenizer_parity(verifier),
        }
        if run_model:
            governor = QualificationEmbeddingGovernor(
                QualificationCapacityPolicy(
                    profile_id=profile.profile_id,
                    profile_revision=profile.profile_revision,
                    deployment_id=identity.deployment_id,
                )
            )
            adapter = TeiEmbeddingAdapter(
                profile,
                endpoint=endpoint,
                token_counter=verifier.counter,
                governor=governor,
                identity_verifier=verifier,
            )
            peak = gpu["used_mib"]
            stop = asyncio.Event()

            async def sample_gpu() -> None:
                nonlocal peak
                while not stop.is_set():
                    peak = max(peak, (await asyncio.to_thread(_gpu))["used_mib"])
                    with suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=0.2)

            await governor.warm_up_async()
            sampler = asyncio.create_task(sample_gpu())
            started = time.monotonic()
            try:
                await adapter.warm_up_async()
                report["inference"] = await _exercise(adapter, profile, verifier.counter)
                before_negatives = int(governor.summary()["attempts_sent"])
                report["negative_diagnostics"] = await _negative_diagnostics(verifier, profile, governor)
                report["negative_diagnostics"]["inference_attempts_added"] = (
                    int(governor.summary()["attempts_sent"]) - before_negatives
                )
            finally:
                stop.set()
                await sampler
                await adapter.close_async()
                report["governor"] = governor.summary()
                await governor.close_async()
                report["gpu"]["sampled_device_peak_used_mib"] = peak
                report["gpu"]["memory_scope"] = (
                    "device-wide observed samples; unrelated clients may contribute; not allocation-exclusive"
                )
                report["live_elapsed_seconds"] = time.monotonic() - started
        await verifier.finalize()
        report["full_asset_hashes_unchanged_after_run"] = True
        report["full_cached_asset_hashes_unchanged_after_run"] = True
        return report


def main() -> int:
    """Write sanitized counts, hashes, metadata and timings without texts or vectors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path, default=Path("A:/AI/TEI/qwen3-4b"))
    parser.add_argument("--container", default=_DEFAULT_CONTAINER)
    parser.add_argument("--endpoint", default=_DEFAULT_ENDPOINT)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Enable bounded real model inference through the shared qualification governor",
    )
    parser.add_argument(
        "--output", type=Path, default=_ROOT / "tasks/evidence/embedding-2026-11-23/optimized-runtime.json"
    )
    args = parser.parse_args()
    try:
        report = asyncio.run(
            run_qualification(
                directory=args.model_directory, container=args.container, endpoint=args.endpoint, run_model=args.run
            )
        )
    except EmbeddingError as error:
        print(json.dumps({"status": "FAIL", "code": error.code.value}))
        return 1
    except EmbeddingConfigurationError:
        print(json.dumps({"status": "FAIL", "code": "INVALID_EMBEDDING_CONFIGURATION"}))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "mode": report["mode"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
