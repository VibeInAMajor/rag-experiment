"""Offline provisioning uses the same pinned assets and actual Haystack runtime as ingestion."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from apps.workbench.chunking import chunking_adapters as adapters
from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter, _read_assets
from scripts import workbench_chunking_setup as setup


@pytest.fixture
def approved_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """Stage the actual approved bytes without modifying the operator's installed cache."""
    if not (adapters._ASSET_ROOT / "o200k_base.tiktoken").is_file():
        pytest.skip("Explicit pinned chunking setup is required for offline bundle qualification")
    bundle = tmp_path / "bundle"
    setup.main(["--from-directory", str(adapters._ASSET_ROOT), "--destination", str(bundle)])
    capsys.readouterr()
    return bundle


@pytest.fixture(autouse=True)
def forbid_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline import and verification must never enter the explicit download path."""

    def forbidden(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("Offline provisioning attempted a download")

    monkeypatch.setattr(setup, "_download", forbidden)


def test_offline_import_is_allowlisted_and_read_only_verification_is_stable(
    approved_bundle: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An extra source file cannot enter runtime assets, and verification leaves every byte untouched."""
    (approved_bundle / "untrusted.py").write_text("raise RuntimeError('do not execute')", encoding="utf-8")
    destination = tmp_path / "clean-runtime"
    setup.main(["--from-directory", str(approved_bundle), "--destination", str(destination)])
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "offline-import"
    assert report["sentence_resource_hashes"] == adapters._PUNKT_HASHES
    assert report["token_encoding_sha256"] == adapters._TOKEN_SHA256
    assert len(list(destination.rglob("*.*"))) == 9
    assert not (destination / "untrusted.py").exists()
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in destination.rglob("*") if path.is_file()}
    setup.main(["--verify-only", "--destination", str(destination)])
    assert json.loads(capsys.readouterr().out)["assets"] == "verified"
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}


@pytest.mark.parametrize("damage", ["missing", "changed", "oversized"])
def test_invalid_bundle_refuses_before_destination_write(
    damage: str, approved_bundle: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing, changed and oversized sentence data cannot partially overwrite a destination."""
    member = approved_bundle / "nltk/tokenizers/punkt_tab/english/abbrev_types.txt"
    if damage == "missing":
        member.unlink()
    else:
        member.write_bytes(b"x" * (2_000_001 if damage == "oversized" else 1))
    destination = tmp_path / "untouched"
    with pytest.raises(SystemExit) as failure:
        setup.main(["--from-directory", str(approved_bundle), "--destination", str(destination)])
    assert failure.value.code == 1
    assert not destination.exists()
    error = capsys.readouterr().err
    assert "ASSET_" in error
    assert str(approved_bundle) not in error


def test_missing_qwen_bundle_cannot_partially_provision_core_assets(
    approved_bundle: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A requested native safeguard must qualify before any core or model destination write."""
    destination = tmp_path / "untouched"
    with pytest.raises(SystemExit) as failure:
        setup.main(
            [
                "--from-directory",
                str(approved_bundle),
                "--destination",
                str(destination),
                "--qwen-from-directory",
                str(tmp_path / "missing-qwen"),
            ]
        )
    assert failure.value.code == 1
    assert not destination.exists()
    assert "MODEL_ASSET_MISSING" in capsys.readouterr().err


def test_real_qwen_import_copies_only_reviewed_json_and_verifies_without_writes(
    approved_bundle: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Native provisioning preserves the hash-pinned tokenizer and excludes model weights or extra files."""
    configured = os.environ.get("WORKBENCH_TEST_QWEN_TOKENIZER_DIR")
    if not configured:
        pytest.skip("WORKBENCH_TEST_QWEN_TOKENIZER_DIR is required for actual native asset provisioning")
    source = tmp_path / "local-model"
    source.mkdir()
    assets = _read_assets(Path(configured))
    for name, content in assets.items():
        (source / name).write_bytes(content)
    (source / "model.safetensors").write_bytes(b"model weights must not be copied")
    destination = tmp_path / "configured-runtime"
    setup.main(
        [
            "--from-directory",
            str(approved_bundle),
            "--destination",
            str(destination),
            "--qwen-from-directory",
            str(source),
        ]
    )
    report = json.loads(capsys.readouterr().out)
    native = destination / "qwen3-embedding-4b"
    assert {path.name for path in native.iterdir()} == set(assets)
    assert {name: (native / name).read_bytes() for name in assets} == assets
    assert report["native_counter"]["state"] == "verified"
    assert report["native_counter"]["counter_revision"] == LocalQwenTokenCounter(native).counter_revision
    before = {path: path.stat().st_mtime_ns for path in native.iterdir()}
    setup.main(["--verify-only", "--destination", str(destination)])
    assert json.loads(capsys.readouterr().out)["native_counter"] == report["native_counter"]
    assert before == {path: path.stat().st_mtime_ns for path in native.iterdir()}


_OFFLINE_PROBE = """
import json
import socket
import sys
from pathlib import Path

def forbidden(*args, **kwargs):
    raise RuntimeError('Network access is forbidden in offline runtime')

socket.create_connection = forbidden
socket.socket.connect = forbidden
import nltk
import tiktoken
nltk.download = forbidden
tiktoken.get_encoding = forbidden
nltk.data.path[:] = []
from apps.workbench.chunking import chunking_adapters as adapter
from apps.workbench.chunking.chunking_profiles import ChunkingProfile, DocumentFeatures, resolve_profile
from apps.workbench.parsing.parser_registry import ElementKind, FormatId
adapter._ASSET_ROOT = Path(sys.argv[1])
resources = adapter.inspect_chunking_resources()
features = DocumentFeatures(FormatId.PLAIN_TEXT, False, (ElementKind.PARAGRAPH,), language=sys.argv[2])
decision = resolve_profile(features, profile=ChunkingProfile(require_sentences=True), resources=resources)
text = ('Dr. Green stores backups. Keep the first line.\\nAnother paragraph follows! ' if sys.argv[2] == 'en'
        else 'Доктор Иванов хранит резервные копии. Первая строка сохранена.\\nСледующий абзац! ') * 100
spans = adapter.split_prose(text, decision=decision)
assert spans and all(0 < span.token_count <= 500 and 0 <= span.overlap_tokens <= 50 for span in spans)
assert spans[0].start == 0 and spans[-1].end == len(text)
assert decision.profile.sentence_language == sys.argv[2] and not decision.fallback_reasons
print(json.dumps(dict(result='PASS', sentence_language=decision.profile.sentence_language,
                     chunks=len(spans), source_preserved=True, network='blocked')))
"""


@pytest.mark.parametrize("language", ["en", "ru"])
def test_fresh_offline_process_uses_pinned_sentences_without_ambient_models(
    language: str, approved_bundle: Path, tmp_path: Path
) -> None:
    """A new process prepares real EN/RU chunks using only the copied tree with all network calls blocked."""
    destination = tmp_path / "fresh-runtime"
    setup.main(["--from-directory", str(approved_bundle), "--destination", str(destination)])
    process = subprocess.run(
        [sys.executable, "-c", _OFFLINE_PROBE, str(destination), language],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    report = json.loads(process.stdout)
    assert report["result"] == "PASS"
    assert report["sentence_language"] == language
    assert report["chunks"] > 1
    assert report["network"] == "blocked"
