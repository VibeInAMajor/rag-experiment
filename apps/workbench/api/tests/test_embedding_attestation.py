"""Offline regression checks for the trusted local deployment-to-endpoint identity chain."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from apps.workbench.api.embedding import EmbeddingError, EmbeddingErrorCode
from apps.workbench.api.embedding_config import EmbeddingConfigurationError
from scripts import workbench_embedding_qualify as qualification


@pytest.fixture
def volume() -> dict[str, Any]:
    """A local, project-owned volume must not resolve through configurable bind-driver options."""
    return {
        "Name": qualification._CACHE_VOLUME,
        "Driver": "local",
        "Options": None,
        "Mountpoint": f"/var/lib/docker/volumes/{qualification._CACHE_VOLUME}/_data",
        "Labels": dict(qualification._CACHE_LABELS),
    }


def _mock_docker(monkeypatch: pytest.MonkeyPatch, deployment: dict[str, Any], volume: dict[str, Any]) -> None:
    def command(arguments: list[str]) -> str:
        return json.dumps([volume if arguments[1:3] == ["volume", "inspect"] else deployment])

    monkeypatch.setattr(qualification, "_command", command)


@pytest.fixture
def deployment(volume: dict[str, Any]) -> dict[str, Any]:
    """Represent the reviewed Docker command, immutable image and exact loopback port ownership."""
    return {
        "Id": "a" * 64,
        "Name": "/approved-local-container",
        "Image": qualification._IMAGE,
        "State": {"Running": True, "StartedAt": "2026-11-23T20:33:36Z"},
        "Config": {
            "Entrypoint": ["./entrypoint.sh"],
            "Cmd": list(qualification._COMMAND),
            "Healthcheck": {"Test": list(qualification._HEALTHCHECK)},
            "Labels": {
                "com.docker.compose.project": "rag-workbench-embedding",
                "com.docker.compose.service": "embedding",
            },
        },
        "Mounts": [
            {
                "Type": "volume",
                "Name": qualification._CACHE_VOLUME,
                "Source": volume["Mountpoint"],
                "Destination": "/models",
                "RW": False,
            }
        ],
        "HostConfig": {"PortBindings": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8082"}]}},
        "NetworkSettings": {"Ports": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8082"}]}},
    }


def test_deployment_binds_served_endpoint_to_selected_read_only_weights(
    deployment: dict[str, Any], volume: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Accept only the selected model mount reached through the inspected container's port binding."""
    _mock_docker(monkeypatch, deployment, volume)
    result = qualification._deployment("approved-local-container", tmp_path)
    assert result["actual_port_bindings"] == result["configured_port_bindings"]
    assert result["command"][2] == f"{result['model_mount']['Destination']}/{qualification._REVISION}"
    assert result["cache_volume"]["ownership_labels"] == qualification._CACHE_LABELS


def test_qualification_attestation_matches_owned_compose_contract() -> None:
    """Keep strict runtime identity checks aligned with the project-owned startup command and port."""
    source = qualification._ROOT / "apps/workbench/embedding/compose.yaml"
    compose = yaml.safe_load(source.read_text(encoding="utf-8"))
    service = compose["services"][qualification._COMPOSE_SERVICE]
    assert compose["name"] == qualification._COMPOSE_PROJECT
    assert service["container_name"] == qualification._DEFAULT_CONTAINER
    assert service["command"] == qualification._COMMAND
    assert service["healthcheck"]["test"] == qualification._HEALTHCHECK
    assert service["image"].split("@", 1)[1] == qualification._IMAGE
    assert service["ports"] == ["127.0.0.1:8082:80"]
    assert qualification._DEFAULT_ENDPOINT == "http://127.0.0.1:8082"
    assert service["volumes"][0]["type"] == "volume"
    assert service["volumes"][0]["target"] == "/models"
    assert service["volumes"][0]["read_only"] is True
    assert service["volumes"][0]["volume"]["nocopy"] is True
    volume_key = service["volumes"][0]["source"]
    assert compose["volumes"][volume_key]["external"] is True
    assert compose["volumes"][volume_key]["name"] == qualification._CACHE_VOLUME


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("Image",), "sha256:" + "0" * 64),
        (("Name",), "/another-container"),
        (("Config", "Labels", "com.docker.compose.project"), "portable-tei"),
        (("Config", "Labels", "com.docker.compose.service"), "another-service"),
        (("Config", "Labels"), {}),
        (("State", "Running"), False),
        (("Config", "Entrypoint"), "./other-server.sh"),
        (("Config", "Cmd", 2), "/models/another-model"),
        (("Config", "Cmd"), [*qualification._COMMAND, "--model-id", "/models/another-model"]),
        (("Config", "Cmd"), []),
        (("Config", "Healthcheck"), None),
        (("Config", "Healthcheck"), {}),
        (("Config", "Healthcheck", "Test"), ["CMD", "curl", "http://127.0.0.1/health"]),
        (("Config", "Healthcheck", "Test", 6), "http://127.0.0.1/health"),
        (("Config", "Cmd", qualification._COMMAND.index("--served-model-name") + 1), "another-model"),
        (("Config", "Cmd", qualification._COMMAND.index("--max-concurrent-requests") + 1), "1"),
        (("Config", "Cmd", qualification._COMMAND.index("--max-concurrent-requests") + 1), "128"),
        (("Config", "Cmd", qualification._COMMAND.index("--max-client-batch-size") + 1), "16"),
        (("Config", "Cmd", qualification._COMMAND.index("--max-batch-tokens") + 1), "8192"),
        (("HostConfig", "PortBindings", "80/tcp", 0, "HostIp"), "0.0.0.0"),
        (("HostConfig", "PortBindings", "80/tcp", 0, "HostPort"), "8081"),
        (("HostConfig", "PortBindings"), {"8081/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8081"}]}),
        (("NetworkSettings", "Ports", "80/tcp", 0, "HostIp"), "0.0.0.0"),
        (("NetworkSettings", "Ports", "80/tcp", 0, "HostPort"), "8081"),
        (("NetworkSettings", "Ports"), {}),
        (("Mounts", 0, "Destination"), "/models/another-model"),
        (("Mounts", 0, "Source"), "other-local-directory"),
        (("Mounts", 0, "Name"), "other-cache-volume"),
        (("Mounts", 0, "RW"), True),
        (("Mounts", 0, "Type"), "bind"),
    ],
)
def test_unbound_or_changed_deployment_is_rejected_before_network_or_inference(
    deployment: dict[str, Any],
    volume: dict[str, Any],
    path: tuple[str | int, ...],
    value: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A matching server version cannot substitute for model-path and endpoint ownership evidence."""
    owner: Any = deployment
    for key in path[:-1]:
        owner = owner[key]
    owner[path[-1]] = value
    _mock_docker(monkeypatch, deployment, volume)
    with pytest.raises(EmbeddingError) as failure:
        qualification._deployment("approved-local-container", tmp_path)
    assert failure.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH


@pytest.mark.parametrize("endpoint", ["https://127.0.0.1:8082", "http://example.com:8082", "http://localhost:8082"])
def test_invalid_endpoint_is_rejected_before_docker_inspection(
    endpoint: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Use the existing endpoint validator before any deployment command or model work."""

    def forbidden(_arguments: list[str]) -> str:
        raise AssertionError("Docker inspection must not precede endpoint validation")

    monkeypatch.setattr(qualification, "_command", forbidden)
    with pytest.raises(EmbeddingConfigurationError):
        qualification._deployment("approved-local-container", tmp_path, endpoint=endpoint)


def test_explicit_endpoint_must_match_both_docker_binding_tables(
    deployment: dict[str, Any], volume: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit endpoint override cannot point at another local service using this container's identity."""
    _mock_docker(monkeypatch, deployment, volume)
    with pytest.raises(EmbeddingError) as failure:
        qualification._deployment("approved-local-container", tmp_path, endpoint="http://127.0.0.1:8083")
    assert failure.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH
    for owner, key in (("HostConfig", "PortBindings"), ("NetworkSettings", "Ports")):
        deployment[owner][key]["80/tcp"][0]["HostPort"] = "8083"
    result = qualification._deployment("approved-local-container", tmp_path, endpoint="http://127.0.0.1:8083/")
    assert result["endpoint"] == "http://127.0.0.1:8083"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("Name", "another-project-cache"),
        ("Driver", "remote-driver"),
        ("Options", {"type": "none", "o": "bind", "device": "/unreviewed-host-path"}),
        ("Labels", {}),
        ("Labels", {**qualification._CACHE_LABELS, "com.rag.workbench.project": "another-project"}),
        ("Labels", {**qualification._CACHE_LABELS, "com.rag.workbench.model-revision": "0" * 40}),
    ],
)
def test_cache_volume_requires_fixed_local_storage_and_ownership(
    volume: dict[str, Any], key: str, value: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An identically named volume cannot redirect trusted model reads to another storage owner."""
    volume[key] = value
    monkeypatch.setattr(qualification, "_command", lambda _arguments: json.dumps([volume]))
    with pytest.raises(EmbeddingError) as failure:
        qualification._cache_volume()
    assert failure.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH


@pytest.mark.parametrize("alternate", ["model.safetensors", "pytorch_model.bin"])
def test_source_rejects_weights_that_shadow_the_approved_sharded_index(tmp_path: Path, alternate: str) -> None:
    """Candle prefers these names, so valid reviewed shards alone cannot attest the loaded weights."""
    (tmp_path / alternate).write_bytes(b"unapproved")
    with pytest.raises(EmbeddingError) as failure:
        qualification._asset_stats(tmp_path)
    assert failure.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH


@pytest.mark.parametrize("output", ["ALTERNATE_WEIGHTS", "", "unexpected|1|mtime|ctime"])
def test_cached_stats_reject_shadow_weights_or_missing_inventory(output: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Actual cached files, including a negative check for preferred alternative weights, are mandatory."""
    monkeypatch.setattr(qualification, "_command", lambda _arguments: output)
    with pytest.raises(EmbeddingError) as failure:
        qualification._cached_asset_stats("approved-local-container")
    assert failure.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH


def test_cached_full_hashes_cover_all_nine_assets_and_detect_concurrent_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """A marker file cannot substitute for hashing the actual immutable model and tokenizer files."""
    stats = {
        name: (index + 1, "mtime-nanoseconds", "ctime-nanoseconds") for index, name in enumerate(qualification._ASSETS)
    }
    rows = "\n".join(f"{'1' * 64}  {qualification._MODEL_PATH}/{name}" for name in qualification._ASSETS)
    monkeypatch.setattr(qualification, "_cached_asset_stats", lambda _container: dict(stats))
    monkeypatch.setattr(qualification, "_command", lambda _arguments: rows)
    manifest = qualification._cached_asset_manifest("approved-local-container")
    assert set(manifest) == set(qualification._ASSETS)
    assert manifest["tokenizer.json"]["sha256"] == "1" * 64
    changed = {**stats, "tokenizer.json": (stats["tokenizer.json"][0], "changed-mtime", "changed-ctime")}
    snapshots = iter([stats, changed])
    monkeypatch.setattr(qualification, "_cached_asset_stats", lambda _container: next(snapshots))
    with pytest.raises(EmbeddingError) as failure:
        qualification._cached_asset_manifest("approved-local-container")
    assert failure.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH


@pytest.mark.parametrize("model_id", [None, "Qwen/Qwen3-Embedding-4B", "/models/another-model"])
def test_runtime_model_path_must_match_pinned_command_and_mount(model_id: str | None) -> None:
    """Reject a different or absent actual loaded path even if all runtime version fields match."""
    info = {
        "model_id": model_id,
        "served_model_name": qualification._MODEL_ID,
        "version": "1.9.4",
        "sha": "e80ef225ed0e6cb1717ce632a6a84b6cf211bb67",
        "model_dtype": "float16",
        "model_type": {"embedding": {"pooling": "last_token"}},
    }
    with pytest.raises(EmbeddingError) as failure:
        qualification._verify_model_info(info)
    assert failure.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH


@pytest.mark.parametrize("served_name", [None, "another-model", qualification._MODEL_PATH])
def test_runtime_served_name_must_match_explicit_startup_contract(served_name: str | None) -> None:
    """Preserve the loaded local path while validating the explicitly declared public served name."""
    info: dict[str, Any] = {
        "model_id": qualification._MODEL_PATH,
        "served_model_name": qualification._MODEL_ID,
        "version": "1.9.4",
        "sha": "e80ef225ed0e6cb1717ce632a6a84b6cf211bb67",
        "model_dtype": "float16",
        "model_type": {"embedding": {"pooling": "last_token"}},
    }
    qualification._verify_model_info(info)
    info["served_model_name"] = served_name
    with pytest.raises(EmbeddingError) as failure:
        qualification._verify_model_info(info)
    assert failure.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH
