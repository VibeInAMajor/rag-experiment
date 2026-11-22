"""Reviewed local Docling artifacts; model installation is an explicit operator action."""

import hashlib
import json
import os
from importlib import metadata
from pathlib import Path

_MANIFEST = Path(__file__).with_name("pdf_asset_manifest.json")
_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES = (
    ("docling", "2.151.1"),
    ("docling-core", "2.108.0"),
    ("docling-ibm-models", "4.0.4"),
    ("docling-parse", "7.27.0"),
    ("torch", "2.15.0"),
    ("transformers", "5.24.0"),
    ("pypdfium2", "5.15.2"),
    ("pypdf", "7.1.1"),
    ("psutil", "7.2.2"),
    ("huggingface-hub", "1.33.0"),
)


class PdfAssetsUnavailable(ValueError):
    """A fixed dependency refusal with no deployment paths or library diagnostics."""


def pdf_assets_directory() -> Path:
    """Resolve only the trusted deployment environment; upload input never chooses a model path."""
    selected = os.environ.get("WORKBENCH_PDF_MODEL_DIRECTORY", ".cache/workbench-pdf/models")
    if not selected or "://" in selected or "\0" in selected:
        raise PdfAssetsUnavailable("PDF_PARSER_UNAVAILABLE")
    path = Path(selected)
    return path.resolve() if path.is_absolute() else (_ROOT / path).resolve()


def pdf_packages_available() -> bool:
    """Check the reviewed parser runtime without importing Torch or loading a model."""
    try:
        return all(metadata.version(name) == version for name, version in _PACKAGES)
    except metadata.PackageNotFoundError:
        return False


def pdf_assets_revision() -> str:
    """Bind processing identity to the reviewed expected hashes, not to an operator path."""
    return "sha256:" + hashlib.sha256(_MANIFEST.read_bytes()).hexdigest()


def pdf_runtime_available() -> bool:
    """Advertise a provisioned installation; the isolated worker verifies full hashes before use."""
    try:
        root = pdf_assets_directory()
        manifest = json.loads(_MANIFEST.read_bytes())
        return pdf_packages_available() and all(
            (root / item["path"]).is_file() and (root / item["path"]).stat().st_size == item["bytes"]
            for item in manifest["files"]
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def verify_pdf_assets(root: Path) -> None:
    """Hash every approved local model/config file before deserializing any weights."""
    if not pdf_packages_available():
        raise PdfAssetsUnavailable("PDF_PARSER_UNAVAILABLE")
    try:
        manifest = json.loads(_MANIFEST.read_bytes())
        for item in manifest["files"]:
            path = (root / item["path"]).resolve()
            if not path.is_relative_to(root.resolve()) or path.stat().st_size != item["bytes"]:
                raise PdfAssetsUnavailable("PDF_PARSER_UNAVAILABLE")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1_048_576), b""):
                    digest.update(block)
            if digest.hexdigest() != item["sha256"]:
                raise PdfAssetsUnavailable("PDF_PARSER_UNAVAILABLE")
    except (OSError, ValueError, KeyError, TypeError):
        raise PdfAssetsUnavailable("PDF_PARSER_UNAVAILABLE") from None
