"""Offline cache preparation checks isolate Docker mutations and preserve existing published data."""

import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import workbench_embedding_cache as cache
from scripts import workbench_embedding_qualify as qualifier


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use tiny pinned files while exercising the real manifest/digest implementation."""
    assets = ("weights.safetensors", "config.json", "1_Pooling/config.json")
    (tmp_path / "1_Pooling").mkdir()
    for name in assets:
        (tmp_path / name).write_bytes(name.encode())
    raw = (tmp_path / assets[0]).read_bytes()
    weights = {assets[0]: {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}
    monkeypatch.setattr(cache, "_ASSETS", assets)
    monkeypatch.setattr(cache, "_WEIGHTS", weights)
    monkeypatch.setattr(qualifier, "_ASSETS", assets)
    monkeypatch.setattr(qualifier, "_WEIGHTS", weights)
    monkeypatch.setattr(cache, "LocalQwenTokenCounter", lambda _directory: None)
    return tmp_path


def _volume(**changes: Any) -> str:
    return json.dumps(
        [
            {
                "Name": cache._CACHE_VOLUME,
                "Driver": "local",
                "Scope": "local",
                "Options": None,
                "Labels": cache._CACHE_LABELS,
                **changes,
            }
        ]
    )


def _docker_fake(
    monkeypatch: pytest.MonkeyPatch, *, outputs: list[str], volume: str | None = None, initially_missing: bool = False
) -> list[tuple[list[str], str | None]]:
    calls: list[tuple[list[str], str | None]] = []
    inspected = False

    def execute(arguments: list[str], *, content: str | None = None, missing_ok: bool = False) -> str | None:
        nonlocal inspected
        calls.append((arguments, content))
        if arguments[:2] == ["volume", "inspect"]:
            if initially_missing and not inspected and missing_ok:
                inspected = True
                return None
            return _volume() if volume is None else volume
        if arguments[:2] == ["volume", "create"]:
            return cache._CACHE_VOLUME
        assert arguments[0] == "run"
        return outputs.pop(0)

    monkeypatch.setattr(cache, "_docker", execute)
    return calls


def test_new_cache_requires_host_full_hash_before_cpu_copy(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a complete source fingerprint permits the helper to atomically publish new files."""
    calls = _docker_fake(monkeypatch, outputs=["missing", "prepared"], initially_missing=True)
    checks: list[bool] = []
    original = cache._source_manifest

    def manifest(directory: Path, *, full: bool) -> dict[str, Any]:
        checks.append(full)
        return original(directory, full=full)

    monkeypatch.setattr(cache, "_source_manifest", manifest)
    report = cache.prepare_embedding_cache(directory=source)
    assert checks == [False, True]
    assert report["mode"] == "prepared" and report["volume"] == cache._CACHE_VOLUME
    assert report["model_files_converted"] is False and report["inference_requests_sent"] is False
    assert str(source) not in json.dumps(report)
    create = next(arguments for arguments, _ in calls if arguments[:2] == ["volume", "create"])
    assert create[-1] == cache._CACHE_VOLUME
    for key, value in cache._CACHE_LABELS.items():
        assert f"{key}={value}" in create
    helpers = [(arguments, content) for arguments, content in calls if arguments[0] == "run"]
    assert len(helpers) == 2
    for arguments, content in helpers:
        assert arguments[arguments.index("--network") + 1] == "none"
        assert arguments[arguments.index("--pull") + 1] == "never"
        assert arguments[arguments.index("--entrypoint") + 1] == "sh"
        assert "NVIDIA_VISIBLE_DEVICES=void" in arguments and "CUDA_VISIBLE_DEVICES=" in arguments
        assert "--gpus" not in arguments and cache._IMAGE in arguments
        assert f"type=bind,source={source.resolve()},target=/source,readonly" in arguments
        assert f"type=volume,source={cache._CACHE_VOLUME},target=/cache,volume-nocopy" in arguments
        marker = json.loads(content or "null")
        assert marker == {"schema_version": 1, "model_revision": cache._REVISION, "assets": original(source, full=True)}


def test_complete_cache_reuse_never_hashes_host_weights_or_rewrites_published_data(
    source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid completed Linux cache uses metadata/stat checks without another 8GB host scan."""
    calls = _docker_fake(monkeypatch, outputs=["reused"])

    def forbidden_full_hash(_directory: Path) -> dict[str, Any]:
        raise AssertionError("A completed cache must not rescan the host weights")

    monkeypatch.setattr(cache, "_asset_manifest", forbidden_full_hash)
    report = cache.prepare_embedding_cache(directory=source)
    assert report["mode"] == "reused"
    helpers = [arguments for arguments, _ in calls if arguments[0] == "run"]
    assert len(helpers) == 1 and helpers[0][-1] == "inspect"
    assert not any(arguments[:2] == ["volume", "create"] for arguments, _ in calls)


@pytest.mark.parametrize(
    "changes",
    [
        {"Name": "foreign-models"},
        {"Driver": "remote"},
        {"Scope": "global"},
        {"Labels": {}},
        {"Options": {"type": "none", "o": "bind", "device": "/foreign/path"}},
    ],
)
def test_existing_foreign_volume_is_never_mounted_or_replaced(
    source: Path, monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any]
) -> None:
    """A colliding volume name cannot redirect cache writes to another owner or a host bind."""
    calls = _docker_fake(monkeypatch, outputs=[], volume=_volume(**changes))
    with pytest.raises(cache.EmbeddingCacheError, match="EMBEDDING_CACHE_OWNERSHIP_MISMATCH"):
        cache.prepare_embedding_cache(directory=source)
    assert len(calls) == 1 and calls[0][0][:2] == ["volume", "inspect"]


def test_wrong_completed_cache_fails_without_any_prepare_retry(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An existing wrong manifest/stat/hash never triggers replacement of published files."""
    actions: list[str] = []

    def fail_helper(_directory: Path, *, manifest: dict[str, Any], action: str) -> str:
        assert manifest
        actions.append(action)
        raise cache.EmbeddingCacheError

    monkeypatch.setattr(cache, "_owned_volume", lambda: None)
    monkeypatch.setattr(cache, "_run_helper", fail_helper)
    with pytest.raises(cache.EmbeddingCacheError):
        cache.prepare_embedding_cache(directory=source)
    assert actions == ["inspect"]


def test_corrupted_source_weights_never_reach_copy_helper(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A same-size corruption is detected by the mandatory full source digest before copying."""
    (source / "weights.safetensors").write_bytes(b"x" * len(b"weights.safetensors"))
    calls = _docker_fake(monkeypatch, outputs=["missing"])
    with pytest.raises(cache.EmbeddingCacheError):
        cache.prepare_embedding_cache(directory=source)
    helpers = [arguments for arguments, _ in calls if arguments[0] == "run"]
    assert len(helpers) == 1 and helpers[0][-1] == "inspect"


@pytest.mark.parametrize("name", ["model.safetensors", "pytorch_model.bin"])
def test_preferred_alternative_weights_refuse_before_docker(
    source: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Candle's preferred single-file formats cannot shadow the pinned sharded model."""
    (source / name).write_bytes(b"unexpected model")
    calls = _docker_fake(monkeypatch, outputs=[])
    with pytest.raises(cache.EmbeddingCacheError, match="INVALID_EMBEDDING_CACHE_SOURCE"):
        cache.prepare_embedding_cache(directory=source)
    assert calls == []


def test_helper_verifies_and_marks_staging_before_atomic_publish(source: Path) -> None:
    """Only whitelisted assets are copied and no recursive removal or provider command exists."""
    script = cache._helper_script(cache._source_manifest(source, full=True))
    copied = script.index('cp -- "/source/$asset" "$stage/$asset"')
    verified = script.index('(cd "$stage"; sha256sum -c')
    marker = script.index('cp /tmp/workbench-cache-expected.json "$stage/.workbench-cache.json"')
    published = script.index('mv -T -- "$stage" "$revision"')
    assert copied < verified < marker < published
    assert "rm " not in script and "rm -r" not in script
    assert "curl" not in script and "text-embeddings" not in script
    assert "mkdir /cache/.workbench-prepare-lock" in script
    assert 'cmp -s /tmp/workbench-cache-stats "$revision/.workbench-cache.stats"' in script
    assert "sha256sum -c /tmp/workbench-cache-small-sha256" in script


@pytest.mark.parametrize("failure", [OSError("secret source path"), subprocess.TimeoutExpired("private command", 300)])
def test_docker_failures_are_sanitized(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    """Paths and captured provider diagnostics never enter a CLI cache refusal."""

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise failure

    monkeypatch.setattr(cache.subprocess, "run", fail)
    with pytest.raises(cache.EmbeddingCacheError) as error:
        cache._docker(["volume", "inspect", cache._CACHE_VOLUME])
    assert str(error.value) == "EMBEDDING_CACHE_UNAVAILABLE"


@pytest.fixture(scope="module")
def posix_shell() -> list[str]:
    """Use local POSIX tools or the already installed WSL shell; no Docker API or model is called."""
    shell = shutil.which("sh")
    if shell is not None:
        return [shell]
    wsl = shutil.which("wsl.exe")
    if wsl is None:
        pytest.skip("A local POSIX shell is required for shell guard regression checks")
    command = [wsl, "--distribution", "docker-desktop", "--exec", "sh"]
    probe = subprocess.run([*command, "-c", "command -v sha256sum stat cmp mktemp >/dev/null"], check=False, timeout=20)
    if probe.returncode:
        pytest.skip("The installed WSL distribution has no local POSIX test tools")
    return command


@pytest.mark.parametrize(
    "defect", ["none", "model.safetensors", "pytorch_model.bin", "missing-first", "marker-symlink"]
)
def test_real_shell_rejects_wrong_cache_before_reuse(source: Path, posix_shell: list[str], defect: str) -> None:
    """Execute the actual guard branch, including failures that POSIX errexit ignores inside AND lists."""
    manifest = cache._source_manifest(source, full=True)
    marker = json.dumps(
        {"schema_version": 1, "model_revision": cache._REVISION, "assets": manifest},
        sort_keys=True,
        separators=(",", ":"),
    )
    helper = cache._helper_script(manifest).replace(
        f"revision='/cache/{cache._REVISION}'", f'revision="$WORKBENCH_CACHE_TEST_ROOT/cache/{cache._REVISION}"'
    )
    for name in ("expected.json", "sha256", "small-sha256", "stats"):
        helper = helper.replace(f"/tmp/workbench-cache-{name}", f'"$WORKBENCH_CACHE_TEST_ROOT/workbench-cache-{name}"')
    fixtures = "\n".join(f"printf '%s' {shlex.quote(name)} > \"$revision/{name}\"" for name in cache._ASSETS)
    injection = ":"
    if defect in {"model.safetensors", "pytorch_model.bin"}:
        injection = f'touch "$revision/{defect}"'
    elif defect == "missing-first":
        injection = f'rm "$revision/{cache._ASSETS[0]}"'
    elif defect == "marker-symlink":
        injection = (
            'rm "$revision/.workbench-cache.json"; '
            'ln -s "$WORKBENCH_CACHE_TEST_ROOT/marker" "$revision/.workbench-cache.json"'
        )
    names = " ".join(shlex.quote(name) for name in cache._ASSETS)
    wrapper = f"""set -eu
WORKBENCH_CACHE_TEST_ROOT=$(mktemp -d /tmp/workbench-cache-shell.XXXXXX)
export WORKBENCH_CACHE_TEST_ROOT
trap 'case "$WORKBENCH_CACHE_TEST_ROOT" in
  /tmp/workbench-cache-shell.*) rm -rf -- "$WORKBENCH_CACHE_TEST_ROOT";;
esac' EXIT
revision="$WORKBENCH_CACHE_TEST_ROOT/cache/{cache._REVISION}"
mkdir -p "$revision/1_Pooling"
{fixtures}
printf '%s' {shlex.quote(marker)} > "$WORKBENCH_CACHE_TEST_ROOT/marker"
cp "$WORKBENCH_CACHE_TEST_ROOT/marker" "$revision/.workbench-cache.json"
(cd "$revision"; stat -c '%s %y %n' -- {names}) > "$revision/.workbench-cache.stats"
{injection}
sh -eu -c {shlex.quote(helper)} workbench-cache inspect < "$WORKBENCH_CACHE_TEST_ROOT/marker"
"""
    result = subprocess.run([*posix_shell, "-c", wrapper], capture_output=True, text=True, timeout=20, check=False)
    if defect == "none":
        assert result.returncode == 0, result.stderr
        assert result.stdout == "reused"
    else:
        assert result.returncode != 0 and "reused" not in result.stdout
