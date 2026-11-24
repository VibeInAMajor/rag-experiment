"""Approved offline Qwen tokenizer qualification; actual-model checks use explicit local test assets."""

import json
import os
import re
import socket
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from apps.workbench.chunking.chunking import ModelTokenAdmission
from apps.workbench.chunking.chunking_adapters import count_tokens
from apps.workbench.chunking.chunking_profiles import ChunkingError, ChunkingErrorCode
from apps.workbench.embedding import model_token_counter as model_module
from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter


@pytest.fixture(autouse=True)
def forbid_model_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """All tokenizer construction and counting must work without a model Hub or socket connection."""

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Model tokenizer network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.fixture(scope="module")
def local_directory() -> Path:
    """Only an operator-provided environment variable enables actual local-model qualification."""
    configured = os.environ.get("WORKBENCH_TEST_QWEN_TOKENIZER_DIR")
    if not configured:
        pytest.skip("WORKBENCH_TEST_QWEN_TOKENIZER_DIR is not configured")
    return Path(configured)


@pytest.fixture(scope="module")
def qwen_counter(local_directory: Path) -> LocalQwenTokenCounter:
    """Use the real reviewed tokenizer and model configuration, without a fake parity fixture."""
    return LocalQwenTokenCounter(local_directory)


def test_missing_local_assets_fail_closed(tmp_path: Path) -> None:
    """A missing approved directory never triggers a model download or another tokenizer."""
    with pytest.raises(ChunkingError) as failure:
        LocalQwenTokenCounter(tmp_path / "private-path-canary")
    assert failure.value.code == ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE
    assert failure.value.reason == "MODEL_ASSET_MISSING"
    assert "private-path-canary" not in str(failure.value)


def test_unreviewed_tokenizer_bytes_are_refused(tmp_path: Path) -> None:
    """JSON syntax alone cannot qualify a different tokenizer or arbitrary model file."""
    (tmp_path / "tokenizer.json").write_text('{"version":"1.0"}', encoding="utf-8")
    with pytest.raises(ChunkingError) as failure:
        LocalQwenTokenCounter(tmp_path)
    assert failure.value.reason == "MODEL_ASSET_MISMATCH"


def test_oversize_asset_is_refused_before_backend_loading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Asset reads have a finite allocation bound independently of the tokenizer engine."""
    with (tmp_path / "tokenizer.json").open("wb") as asset:
        asset.truncate(16_777_217)

    def forbidden_backend(_assets: dict[str, bytes]) -> Any:
        raise AssertionError("Oversized asset reached the tokenizer engine")

    monkeypatch.setattr(model_module, "_load_backend", forbidden_backend)
    with pytest.raises(ChunkingError) as failure:
        LocalQwenTokenCounter(tmp_path)
    assert failure.value.reason == "MODEL_ASSET_LIMIT_EXCEEDED"


def test_changed_dependency_revision_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new tokenizer implementation cannot silently reuse the approved counter identity."""
    monkeypatch.setattr(model_module.metadata, "version", lambda _name: "unapproved-version")
    with pytest.raises(ChunkingError) as failure:
        model_module._load_backend({})
    assert failure.value.reason == "MODEL_PACKAGE_MISMATCH"


def test_backend_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operational errors disclose neither SDK internals nor asset paths or source excerpts."""

    def failed_backend(_assets: dict[str, bytes]) -> Any:
        raise RuntimeError("private-tokenizer-detail-canary")

    monkeypatch.setattr(model_module, "_build_backend", failed_backend)
    with pytest.raises(ChunkingError) as failure:
        model_module._load_backend({})
    assert failure.value.reason == "MODEL_BACKEND_UNAVAILABLE"
    assert "private-tokenizer-detail-canary" not in str(failure.value)


@pytest.mark.parametrize(
    ("text", "expected_qwen", "expected_tiktoken"),
    [
        ("Hello world", 3, 2),
        ("Привет, мир!", 7, 5),
        ("Привіт, світе!", 10, 7),
        ("cafe\u0301", 3, 3),
        ("café", 3, 2),
        ("Hello<|im_end|>", 3, 7),
        ("Instruct: Retrieve relevant passages.\nQuery: Hello world", 12, 11),
    ],
)
def test_real_qwen_and_tiktoken_counts_are_separate(
    qwen_counter: LocalQwenTokenCounter, text: str, expected_qwen: int, expected_tiktoken: int
) -> None:
    """Pinned EN/RU/UK and normalization goldens record actual counter differences."""
    assert qwen_counter.count_tokens(text) == expected_qwen
    assert count_tokens(text) == expected_tiktoken


def test_real_serialized_postprocessor_appends_endoftext(qwen_counter: LocalQwenTokenCounter) -> None:
    """The embedding suffix comes from tokenizer.json rather than the generation EOS name."""
    assert qwen_counter.count_tokens("") == 1
    assert qwen_counter.count_tokens("Hello world") == 3
    assert qwen_counter.count_tokens("Hello world<|endoftext|>") == 4
    policy = qwen_counter.manifest()["input_policy"]
    assert policy["add_special_tokens"] is True
    assert policy["appended_special_token"] == "<|endoftext|>"
    assert policy["appended_special_token_id"] == 151643
    assert policy["automatic_bos"] is False
    assert policy["chat_template_applied"] is False


def test_real_counter_identity_is_reproducible_and_path_free(
    qwen_counter: LocalQwenTokenCounter, local_directory: Path
) -> None:
    """A restart with the same verified files produces the same immutable counter revision."""
    fresh = LocalQwenTokenCounter(local_directory)
    assert fresh.counter_revision == qwen_counter.counter_revision
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+@=,/-]{0,255}", fresh.counter_revision)
    manifest = fresh.manifest()
    assert manifest["model_id"] == "Qwen/Qwen3-Embedding-4B"
    assert manifest["model_revision"] == "5cf2132abc99cad020ac570b19d031efec650f2b"
    assert manifest["tokenizer_dependency"] == "tokenizers:0.23.3"
    assert str(local_directory) not in json.dumps(manifest)
    manifest["asset_sha256"]["tokenizer.json"] = "changed"
    assert fresh.manifest()["asset_sha256"]["tokenizer.json"] != "changed"


def test_real_counter_does_not_truncate_or_pad(qwen_counter: LocalQwenTokenCounter) -> None:
    """The complete input is counted even beyond the model card's short example limit."""
    short = qwen_counter.count_tokens("Hello")
    long = qwen_counter.count_tokens("Hello " * 10_000)
    assert short == 2
    assert long > 8192
    policy = qwen_counter.manifest()["input_policy"]
    assert policy["padding"] is False
    assert policy["truncation"] is False


def test_real_counter_counts_the_complete_configured_embedding_input(qwen_counter: LocalQwenTokenCounter) -> None:
    """Admission includes actual headings and caller formatting before Qwen special-token processing."""
    admission = ModelTokenAdmission(
        counter_revision=qwen_counter.counter_revision,
        max_tokens=32_768,
        prefix="Document: ",
        suffix="\n",
        include_heading_path=True,
    )
    embedding = admission.embedding_input("Привіт, світе!", heading_path=("Огляд", "Деталі"))
    assert embedding == "Document: Огляд > Деталі\n\nПривіт, світе!\n"
    assert qwen_counter.count_tokens(embedding) > qwen_counter.count_tokens("Привіт, світе!")


@pytest.mark.parametrize("text", ["\ud800", "a" * 4_194_305])
def test_real_counter_refuses_invalid_or_unbounded_input(qwen_counter: LocalQwenTokenCounter, text: str) -> None:
    """Malformed scalars and excessive input cannot reach unbounded tokenizer allocation."""
    with pytest.raises(ChunkingError) as failure:
        qwen_counter.count_tokens(text)
    assert failure.value.code == ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE
