"""Prepare verified local Qwen assets in one Workbench-owned Linux Docker volume."""

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter
from scripts.workbench_embedding_qualify import (
    _ASSETS,
    _CACHE_LABELS,
    _CACHE_VOLUME,
    _IMAGE,
    _REVISION,
    _WEIGHTS,
    _asset_manifest,
)


class EmbeddingCacheError(ValueError):
    """Expose a bounded preparation failure without local paths or Docker diagnostics."""

    def __init__(self, code: str = "EMBEDDING_CACHE_UNAVAILABLE") -> None:
        self.code = code
        super().__init__(code)


def _docker(arguments: list[str], *, content: str | None = None, missing_ok: bool = False) -> str | None:
    try:
        result = subprocess.run(
            ["docker", *arguments], input=content, capture_output=True, text=True, timeout=300, check=False
        )
    except (OSError, subprocess.SubprocessError):
        raise EmbeddingCacheError from None
    if result.returncode:
        if missing_ok:
            return None
        raise EmbeddingCacheError
    return result.stdout.strip()


def _owned_volume() -> None:
    existing = _docker(["volume", "inspect", _CACHE_VOLUME], missing_ok=True)
    if existing is None:
        labels = [part for key, value in _CACHE_LABELS.items() for part in ("--label", f"{key}={value}")]
        _docker(["volume", "create", "--driver", "local", *labels, _CACHE_VOLUME])
        existing = _docker(["volume", "inspect", _CACHE_VOLUME])
    try:
        volume = json.loads(existing or "null")[0]
        valid = (
            volume["Name"] == _CACHE_VOLUME
            and volume["Driver"] == "local"
            and volume["Scope"] == "local"
            and volume.get("Options") in (None, {})
            and all(volume.get("Labels", {}).get(key) == value for key, value in _CACHE_LABELS.items())
        )
    except (TypeError, KeyError, IndexError, ValueError):
        valid = False
    if not valid:
        raise EmbeddingCacheError("EMBEDDING_CACHE_OWNERSHIP_MISMATCH")


def _source_manifest(directory: Path, *, full: bool) -> dict[str, Any]:
    root = directory.resolve(strict=True)
    if not root.is_dir() or str(root).startswith(("\\\\", "//")) or "," in str(root):
        raise EmbeddingCacheError("INVALID_EMBEDDING_CACHE_SOURCE")
    if any((root / name).exists() for name in ("model.safetensors", "pytorch_model.bin")):
        raise EmbeddingCacheError("INVALID_EMBEDDING_CACHE_SOURCE")
    LocalQwenTokenCounter(root)
    manifest = {}
    for name in _ASSETS:
        asset = root / name
        if asset.is_symlink() or not asset.is_file() or not asset.resolve().is_relative_to(root):
            raise EmbeddingCacheError("INVALID_EMBEDDING_CACHE_SOURCE")
        if name in _WEIGHTS:
            if asset.stat().st_size != _WEIGHTS[name]["size"]:
                raise EmbeddingCacheError("INVALID_EMBEDDING_CACHE_SOURCE")
            manifest[name] = dict(_WEIGHTS[name])
        else:
            with asset.open("rb") as source:
                raw = source.read(16_777_217)
            if len(raw) > 16_777_216:
                raise EmbeddingCacheError("INVALID_EMBEDDING_CACHE_SOURCE")
            manifest[name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if full and _asset_manifest(root) != manifest:
        raise EmbeddingCacheError("INVALID_EMBEDDING_CACHE_SOURCE")
    return manifest


def _helper_script(manifest: dict[str, Any]) -> str:
    checks = []
    small_checks = []
    for name in _ASSETS:
        digest = manifest[name]["sha256"]
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise EmbeddingCacheError("INVALID_EMBEDDING_CACHE_SOURCE")
        checks.append(f"'{digest}  {name}'")
        if name not in _WEIGHTS:
            small_checks.append(checks[-1])
    names = " ".join(f"'{name}'" for name in _ASSETS)
    return f"""set -eu
revision='/cache/{_REVISION}'
cat > /tmp/workbench-cache-expected.json
printf '%s\\n' {" ".join(checks)} > /tmp/workbench-cache-sha256
printf '%s\\n' {" ".join(small_checks)} > /tmp/workbench-cache-small-sha256
if [ -e "$revision" ] || [ -L "$revision" ]; then
  [ -d "$revision" ]
  [ ! -L "$revision" ]
  [ ! -e "$revision/model.safetensors" ]
  [ ! -e "$revision/pytorch_model.bin" ]
  [ -f "$revision/.workbench-cache.json" ]
  [ ! -L "$revision/.workbench-cache.json" ]
  [ -f "$revision/.workbench-cache.stats" ]
  [ ! -L "$revision/.workbench-cache.stats" ]
  cmp -s /tmp/workbench-cache-expected.json "$revision/.workbench-cache.json"
  (cd "$revision"; for asset in {names}; do [ -f "$asset" ]; [ ! -L "$asset" ]; done)
  (cd "$revision"; stat -c '%s %y %n' -- {names}) > /tmp/workbench-cache-stats
  cmp -s /tmp/workbench-cache-stats "$revision/.workbench-cache.stats"
  (cd "$revision"; sha256sum -c /tmp/workbench-cache-small-sha256 > /dev/null)
  printf 'reused'
  exit 0
fi
if [ "$1" = inspect ]; then printf 'missing'; exit 0; fi
mkdir /cache/.workbench-prepare-lock
trap 'rmdir /cache/.workbench-prepare-lock' EXIT
stage='/cache/.workbench-stage-{uuid4().hex}'
mkdir "$stage"
mkdir "$stage/1_Pooling"
for asset in {names}; do
  [ -f "/source/$asset" ]
  [ ! -L "/source/$asset" ]
  cp -- "/source/$asset" "$stage/$asset"
done
(cd "$stage"; sha256sum -c /tmp/workbench-cache-sha256 > /dev/null)
cp /tmp/workbench-cache-expected.json "$stage/.workbench-cache.json"
(cd "$stage"; stat -c '%s %y %n' -- {names}) > "$stage/.workbench-cache.stats"
[ ! -e "$revision" ]
[ ! -L "$revision" ]
mv -T -- "$stage" "$revision"
printf 'prepared'
"""


def _run_helper(directory: Path, *, manifest: dict[str, Any], action: str) -> str:
    marker = json.dumps(
        {"schema_version": 1, "model_revision": _REVISION, "assets": manifest}, sort_keys=True, separators=(",", ":")
    )
    output = _docker(
        [
            "run",
            "--rm",
            "--interactive",
            "--pull",
            "never",
            "--network",
            "none",
            "--env",
            "NVIDIA_VISIBLE_DEVICES=void",
            "--env",
            "CUDA_VISIBLE_DEVICES=",
            "--entrypoint",
            "sh",
            "--mount",
            f"type=bind,source={directory.resolve()},target=/source,readonly",
            "--mount",
            f"type=volume,source={_CACHE_VOLUME},target=/cache,volume-nocopy",
            _IMAGE,
            "-eu",
            "-c",
            _helper_script(manifest),
            "workbench-cache",
            action,
        ],
        content=marker,
    )
    if output not in {"missing", "prepared", "reused"}:
        raise EmbeddingCacheError
    return output


def prepare_embedding_cache(*, directory: Path) -> dict[str, str | float | bool]:
    """Reuse a completed cache or copy and verify exact assets before atomic publication."""
    started = time.monotonic()
    if not directory.is_absolute():
        raise EmbeddingCacheError("INVALID_EMBEDDING_CACHE_SOURCE")
    try:
        manifest = _source_manifest(directory, full=False)
        _owned_volume()
        mode = _run_helper(directory, manifest=manifest, action="inspect")
        if mode == "missing":
            manifest = _source_manifest(directory, full=True)
            mode = _run_helper(directory, manifest=manifest, action="prepare")
        return {
            "mode": mode,
            "volume": _CACHE_VOLUME,
            "model_revision": _REVISION,
            "preparation_ms": (time.monotonic() - started) * 1000,
            "model_files_converted": False,
            "inference_requests_sent": False,
        }
    except EmbeddingCacheError:
        raise
    except Exception:
        raise EmbeddingCacheError from None


def main() -> int:
    """Write bounded cache evidence without source paths or model inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        report = prepare_embedding_cache(directory=arguments.model_directory)
    except EmbeddingCacheError as error:
        print(json.dumps({"status": "FAIL", "code": error.code}))
        return 1
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", **report}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
