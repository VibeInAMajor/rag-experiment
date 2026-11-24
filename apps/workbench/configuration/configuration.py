"""Locked, atomic revision updates to the existing authoritative operator YAML."""

import hashlib
import os
import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml
from filelock import FileLock, Timeout

from apps.workbench.configuration.config import ApiSettings
from apps.workbench.configuration.document_processing import (
    ConfigurationIssue,
    DocumentProcessingConfigurationError,
    DocumentProcessingSettings,
    NativeModelGuardSettings,
    validate_document_processing_yaml,
)

_ROOT = Path(__file__).resolve().parents[3]
_MAX_BYTES = 65_536


class ConfigurationFailure(Exception):
    """A stable public category without paths, source text or filesystem errors."""

    def __init__(self, code: str, status: int = 503) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass(frozen=True)
class ConfigurationDocument:
    yaml: str
    revision: str
    exists: bool
    activation: str


def _revision(raw: bytes) -> str:
    return "config-" + hashlib.sha256(raw).hexdigest()


def _atomic_write(path: Path, raw: bytes) -> None:
    pending: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".configuration-", delete=False) as destination:
            pending = destination.name
            destination.write(raw)
            destination.flush()
            os.fsync(destination.fileno())
        if path.exists():
            os.chmod(pending, path.stat().st_mode)
        os.replace(pending, path)
        pending = None
    finally:
        if pending is not None:
            Path(pending).unlink(missing_ok=True)


class ConfigurationStore:
    """One deployment-selected file; active consumers retain their startup snapshot until restart."""

    def __init__(self, settings: ApiSettings, *, state_directory: Path | None = None) -> None:
        self._path = Path(settings.configuration_file) if settings.configuration_file is not None else None
        self._active = settings.document_processing
        self._language_override = settings.configuration_language_override
        self._state = state_directory or _ROOT / ".cache/workbench-configuration"
        self._secrets = []
        if settings.database_dsn is not None:
            dsn = settings.database_dsn.get_secret_value()
            self._secrets.append(dsn)
            password = unquote(urlsplit(dsn).password or "")
            if len(password) >= 8:
                self._secrets.append(password)

    def _source(self) -> Path:
        if self._path is None:
            raise ConfigurationFailure("CONFIGURATION_UNAVAILABLE")
        return self._path

    def _nonsecret(self, text: str) -> None:
        if any(secret in text for secret in self._secrets) or re.search(
            r"(?:postgres(?:ql)?|mysql|redis)://\S+|\bsk-[A-Za-z0-9_-]{20,}", text
        ):
            raise ConfigurationFailure("SECRET_VALUES_NOT_ALLOWED", 400)

    def _raw(self) -> bytes | None:
        try:
            with self._source().open("rb") as source:
                raw = source.read(_MAX_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(raw) > _MAX_BYTES:
            raise ConfigurationFailure("CONFIGURATION_TOO_LARGE", 413)
        text = raw.decode("utf-8")
        self._nonsecret(text)
        try:
            parsed = validate_document_processing_yaml(text)
        except DocumentProcessingConfigurationError:
            pass
        else:
            self._nonsecret(parsed.model_dump_json())
        return raw

    def validate(self, text: str) -> DocumentProcessingSettings:
        """Use canonical parsing/schema and prohibit browser-controlled native filesystem redirection."""
        self._nonsecret(text)
        settings = validate_document_processing_yaml(text)
        self._nonsecret(settings.model_dump_json())
        guard = settings.native_model_guard
        if guard.local_asset_directory != self._active.native_model_guard.local_asset_directory:
            raise DocumentProcessingConfigurationError(
                (
                    ConfigurationIssue(
                        "Tokenizer directory is deployment-managed; keep the current reference.",
                        path="document_processing.native_model_guard.local_asset_directory",
                    ),
                )
            )
        return settings

    def _activation(self, text: str) -> str:
        try:
            effective = validate_document_processing_yaml(text, default_language_override=self._language_override)
        except DocumentProcessingConfigurationError:
            return "requires_restart"
        return "active" if effective.model_dump() == self._active.model_dump() else "requires_restart"

    def read(self) -> ConfigurationDocument:
        """Read atomic file bytes or explicitly return a starter generated from canonical defaults."""
        try:
            raw = self._raw()
            if raw is None:
                starter = DocumentProcessingSettings(
                    native_model_guard=NativeModelGuardSettings(
                        local_asset_directory=self._active.native_model_guard.local_asset_directory
                    )
                )
                text = yaml.safe_dump({"document_processing": starter.model_dump(mode="json")}, sort_keys=False)
                return ConfigurationDocument(text, "config-missing", False, "requires_restart")
            text = raw.decode("utf-8")
            return ConfigurationDocument(text, _revision(raw), True, self._activation(text))
        except (OSError, UnicodeError):
            raise ConfigurationFailure("CONFIGURATION_UNAVAILABLE") from None

    def save(self, text: str, *, expected_revision: str) -> ConfigurationDocument:
        """Validate again, compare under a cross-process lock, retain ten prior revisions, replace atomically."""
        self.validate(text)
        activation = self._activation(text)
        raw = text.encode("utf-8")
        if len(raw) > _MAX_BYTES:
            raise ConfigurationFailure("CONFIGURATION_TOO_LARGE", 413)
        path = self._source()
        identity = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
        state = self._state / identity
        try:
            state.mkdir(parents=True, exist_ok=True)
            with FileLock(str(state / "write.lock"), timeout=1):
                previous = self._raw()
                revision = "config-missing" if previous is None else _revision(previous)
                if expected_revision != revision:
                    raise ConfigurationFailure("CONFIGURATION_CONFLICT", 409)
                if previous == raw:
                    return ConfigurationDocument(text, revision, True, activation)
                if previous is not None:
                    _atomic_write(state / (revision + ".yaml"), previous)
                _atomic_write(path, raw)
                with suppress(OSError):
                    retained = sorted(
                        state.glob("config-*.yaml"), key=lambda item: item.stat().st_mtime_ns, reverse=True
                    )
                    for old in retained[10:]:
                        if old.parent.resolve() == state.resolve() and re.fullmatch(
                            r"config-[0-9a-f]{64}\.yaml", old.name
                        ):
                            old.unlink(missing_ok=True)
            return ConfigurationDocument(text, _revision(raw), True, activation)
        except Timeout:
            raise ConfigurationFailure("CONFIGURATION_BUSY", 503) from None
        except (OSError, UnicodeError):
            raise ConfigurationFailure("CONFIGURATION_UNAVAILABLE") from None
