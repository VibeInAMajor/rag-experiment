"""Offline admission counter for the reviewed local Qwen3-Embedding-4B tokenizer revision."""

import hashlib
import json
from importlib import metadata
from pathlib import Path
from typing import Any

from apps.workbench.api.chunking_profiles import ChunkingError, ChunkingErrorCode

_MODEL_ID = "Qwen/Qwen3-Embedding-4B"
_MODEL_REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"
_TOKENIZERS_VERSION = "0.23.3"
_APPROVED_ASSETS = (
    ("tokenizer.json", "83cdf8c3a34f68862319cb1810ee7b1e2c0a44e0864ae930194ddb76bb7feb8d", 16_777_216),
    ("tokenizer_config.json", "2f58f4bbd7bbce15d683f525954ef3a92cd82f5e06415a9c513859bf8ab72436", 32_768),
    ("config.json", "78d2861cbbfd80eee05839200c5a3b7ed64c789f6c1cab4fbb84cc4eae33eaf5", 32_768),
)
_MAX_INPUT_BYTES = 4_194_304


def _read_assets(directory: Path) -> dict[str, bytes]:
    if not isinstance(directory, Path):
        raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="INVALID_MODEL_DIRECTORY")
    assets = {}
    for name, expected, limit in _APPROVED_ASSETS:
        try:
            with (directory / name).open("rb") as source:
                content = source.read(limit + 1)
        except OSError:
            raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_ASSET_MISSING") from None
        if len(content) > limit:
            raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_ASSET_LIMIT_EXCEEDED")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_ASSET_MISMATCH")
        assets[name] = content
    return assets


def _manifest() -> dict[str, Any]:
    return {
        "model_id": _MODEL_ID,
        "model_revision": _MODEL_REVISION,
        "counter_adapter_revision": "qwen-local-token-counter-r1",
        "tokenizer_dependency": f"tokenizers:{_TOKENIZERS_VERSION}",
        "asset_sha256": {name: digest for name, digest, _ in _APPROVED_ASSETS},
        "input_policy": {
            "normalization": "NFC",
            "add_special_tokens": True,
            "post_processor": "serialized-embedding-template",
            "appended_special_token": "<|endoftext|>",
            "appended_special_token_id": 151643,
            "automatic_bos": False,
            "chat_template_applied": False,
            "padding": False,
            "truncation": False,
        },
    }


def _build_backend(assets: dict[str, bytes]) -> Any:
    from tokenizers import Tokenizer

    if metadata.version("tokenizers") != _TOKENIZERS_VERSION:
        raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_PACKAGE_MISMATCH")
    tokenizer_config = json.loads(assets["tokenizer_config.json"])
    model_config = json.loads(assets["config.json"])
    if (
        tokenizer_config.get("tokenizer_class") != "Qwen2Tokenizer"
        or tokenizer_config.get("add_bos_token") is not False
        or model_config.get("model_type") != "qwen3"
        or model_config.get("hidden_size") != 2560
    ):
        raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_CONFIGURATION_MISMATCH")
    backend = Tokenizer.from_buffer(assets["tokenizer.json"])
    backend.no_padding()
    backend.no_truncation()
    if backend.num_special_tokens_to_add(False) != 1 or backend.token_to_id("<|endoftext|>") != 151643:
        raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_SPECIAL_TOKEN_MISMATCH")
    return backend


def _load_backend(assets: dict[str, bytes]) -> Any:
    try:
        return _build_backend(assets)
    except ChunkingError:
        raise
    except Exception:
        raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_BACKEND_UNAVAILABLE") from None


class LocalQwenTokenCounter:
    """A trusted-configuration tokenizer counter; no model weights, Hub client or source-controlled loading."""

    def __init__(self, directory: Path) -> None:
        """
        Verify the reviewed assets and construct an entirely local tokenizer.

        :param directory: Operator-selected directory containing the approved three JSON files; never upload input.
        :raises ChunkingError: If files, dependency versions or tokenizer configuration fail qualification.
        """
        self._backend = _load_backend(_read_assets(directory))
        fingerprint = hashlib.sha256(
            json.dumps(_manifest(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self._counter_revision = (
            f"qwen3-embedding-4b:{_MODEL_REVISION}:tokenizers-{_TOKENIZERS_VERSION}:sha256:{fingerprint}"
        )

    @property
    def counter_revision(self) -> str:
        """Identity of model/assets, dependency version, normalization and special-token policy."""
        return self._counter_revision

    def manifest(self) -> dict[str, Any]:
        """Return a fresh metadata-only tokenizer identity, without an operator filesystem path."""
        return _manifest()

    def count_tokens(self, text: str) -> int:
        """
        Count the complete configured embedding input, including the serialized suffix token.

        :param text: Exact final embedding string, including any caller-controlled heading or instruction prefix.
        :returns: Actual Qwen tokenizer count with NFC and special-token processing, without padding or truncation.
        :raises ChunkingError: If input is invalid, exceeds the bounded allocation or cannot be encoded.
        """
        if not isinstance(text, str):
            raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_INPUT_INVALID")
        try:
            size = len(text.encode("utf-8"))
        except UnicodeError:
            raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_INPUT_INVALID") from None
        if size > _MAX_INPUT_BYTES:
            raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_INPUT_LIMIT_EXCEEDED")
        try:
            return len(self._backend.encode(text, add_special_tokens=True).ids)
        except Exception:
            raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE, reason="MODEL_ENCODING_FAILED") from None
