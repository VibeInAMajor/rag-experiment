"""Explicitly provision pinned tokenizer assets; runtime indexing never downloads them."""

import argparse
import io
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

from apps.workbench.chunking.chunking_adapters import (
    _ASSET_ROOT,
    _PUNKT_FILES,
    _PUNKT_HASHES,
    _PUNKT_LANGUAGES,
    _PUNKT_SHA256,
    _PUNKT_URL,
    _TOKEN_SHA256,
    _TOKEN_URL,
    _punkt_digest,
)
from apps.workbench.chunking.chunking_profiles import ChunkingError
from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter, _read_assets


class _AssetError(ValueError):
    """Static provisioning diagnosis without operator paths or untrusted file content."""


def _download(url: str, expected: str) -> bytes:
    with urlopen(url, timeout=30) as response:
        if response.url != url:
            raise _AssetError("ASSET_REDIRECT_REFUSED")
        content = response.read(5_000_001)
    if len(content) > 5_000_000:
        raise _AssetError("ASSET_SIZE_EXCEEDED")
    if sha256(content).hexdigest() != expected:
        raise _AssetError("ASSET_DIGEST_MISMATCH")
    return content


def _members() -> tuple[tuple[Path, int], ...]:
    return (
        (Path("o200k_base.tiktoken"), 5_000_000),
        *(
            (Path("nltk/tokenizers/punkt_tab") / language / name, 2_000_000)
            for _code, language in _PUNKT_LANGUAGES
            for name in _PUNKT_FILES
        ),
    )


def _offline_payload(directory: Path) -> dict[Path, bytes]:
    payload = {}
    for relative, limit in _members():
        try:
            with (directory / relative).open("rb") as source:
                content = source.read(limit + 1)
        except OSError:
            raise _AssetError("ASSET_MISSING") from None
        if len(content) > limit:
            raise _AssetError("ASSET_SIZE_EXCEEDED")
        payload[relative] = content
    return payload


def _online_payload() -> dict[Path, bytes]:
    archive = _download(_PUNKT_URL, _PUNKT_SHA256)
    payload = {Path("o200k_base.tiktoken"): _download(_TOKEN_URL, _TOKEN_SHA256)}
    with ZipFile(io.BytesIO(archive)) as package:
        for relative, limit in _members()[1:]:
            with package.open("/".join(relative.parts[2:])) as source:
                content = source.read(limit + 1)
            if len(content) > limit:
                raise _AssetError("ASSET_SIZE_EXCEEDED")
            payload[relative] = content
    return payload


def _write_payload(directory: Path, payload: dict[Path, bytes]) -> None:
    for relative, content in payload.items():
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def _verify_payload(payload: dict[Path, bytes]) -> dict[str, str]:
    if sha256(payload[Path("o200k_base.tiktoken")]).hexdigest() != _TOKEN_SHA256:
        raise _AssetError("ASSET_DIGEST_MISMATCH")
    # Reuse runtime's digest on our bounded staged files, never reread untrusted source files without a cap.
    with TemporaryDirectory(prefix="workbench-chunking-") as temporary:
        staged = Path(temporary)
        _write_payload(staged, payload)
        revisions = {}
        for code, language in _PUNKT_LANGUAGES:
            digest = _punkt_digest(staged / "nltk/tokenizers/punkt_tab" / language)
            if digest != _PUNKT_HASHES[code]:
                raise _AssetError("ASSET_DIGEST_MISMATCH")
            revisions[code] = digest
    return revisions


def _verify_qwen(assets: dict[str, bytes]) -> dict[str, object]:
    with TemporaryDirectory(prefix="workbench-native-counter-") as temporary:
        staged = Path(temporary)
        for name, content in assets.items():
            (staged / name).write_bytes(content)
        counter = LocalQwenTokenCounter(staged)
        manifest = counter.manifest()
        return {
            "state": "verified",
            "model_id": manifest["model_id"],
            "model_revision": manifest["model_revision"],
            "counter_revision": counter.counter_revision,
            "asset_sha256": manifest["asset_sha256"],
        }


def main(argv: list[str] | None = None) -> None:
    """Import a verified offline tree, verify installed assets, or explicitly download the approved bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--from-directory", type=Path, help="Import an already provisioned asset tree without network access."
    )
    mode.add_argument("--verify-only", action="store_true", help="Verify destination files without modifying them.")
    parser.add_argument(
        "--destination", type=Path, default=_ASSET_ROOT, help="Asset root; defaults to the runtime cache."
    )
    parser.add_argument(
        "--qwen-from-directory", type=Path, help="Copy only the reviewed three local Qwen tokenizer JSON assets."
    )
    arguments = parser.parse_args(argv)
    if arguments.verify_only and arguments.qwen_from_directory is not None:
        parser.error("--qwen-from-directory provisions assets and cannot be combined with --verify-only")
    try:
        if arguments.verify_only:
            payload = _offline_payload(arguments.destination)
            provisioning_mode = "verify-only"
        elif arguments.from_directory is not None:
            payload = _offline_payload(arguments.from_directory)
            provisioning_mode = "offline-import"
        else:
            payload = _online_payload()
            provisioning_mode = "download"
        revisions = _verify_payload(payload)
        qwen_directory = arguments.destination / "qwen3-embedding-4b"
        qwen_assets = None
        native_counter: dict[str, object] = {"state": "absent"}
        if arguments.qwen_from_directory is not None:
            qwen_assets = _read_assets(arguments.qwen_from_directory)
            native_counter = _verify_qwen(qwen_assets)
        elif qwen_directory.exists():
            native_counter = _verify_qwen(_read_assets(qwen_directory))
        if not arguments.verify_only:
            _write_payload(arguments.destination, payload)
            if qwen_assets is not None:
                _write_payload(qwen_directory, {Path(name): content for name, content in qwen_assets.items()})
    except ChunkingError as error:
        parser.exit(status=1, message=f"Chunking assets refused: {error.code.value}:{error.reason}\n")
    except _AssetError as error:
        parser.exit(status=1, message=f"Chunking assets refused: {error}\n")
    except (OSError, ValueError, RuntimeError, KeyError, BadZipFile):
        parser.exit(status=1, message="Chunking assets refused: ASSET_PROVISIONING_FAILED\n")
    print(
        json.dumps(
            {
                "assets": "verified" if arguments.verify_only else "provisioned",
                "mode": provisioning_mode,
                "sentence_resource_hashes": revisions,
                "token_encoding_sha256": _TOKEN_SHA256,
                "native_counter": native_counter,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
