"""Bounded operator configuration mapped to the existing token chunking contract."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator, model_validator
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from apps.workbench.api.chunking_profiles import ChunkingProfile, validate_configured_separators

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONFIG = _ROOT / "apps" / "workbench" / "document_processing.yaml"
_MAX_CONFIG_BYTES = 65_536
_SCALAR_TAGS = frozenset(f"tag:yaml.org,2002:{kind}" for kind in ("str", "int", "bool", "null", "float"))


@dataclass(frozen=True)
class ConfigurationIssue:
    """Safe diagnostic coordinates; input values and parser snippets are deliberately excluded."""

    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None


class DocumentProcessingConfigurationError(ValueError):
    """Operator errors expose no file contents, local paths or parser diagnostics."""

    def __init__(self, issues: tuple[ConfigurationIssue, ...] = ()) -> None:
        self.issues = issues or (ConfigurationIssue("Invalid or unsupported YAML configuration."),)
        super().__init__("INVALID_DOCUMENT_PROCESSING_CONFIGURATION")


class _Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


def _validate_utf8(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("Configuration strings must contain valid Unicode scalars") from None
    return value


class SentenceSplitterSettings(_Settings):
    """Sentence resources are qualified for explicit English and Russian only."""

    language: Literal["en", "ru"] = "en"
    keep_white_spaces: bool = True


class RecursiveSplitterSettings(_Settings):
    """Approved Haystack constructor values, expressed in encoding tokens."""

    split_length: int = Field(default=500, ge=1, le=8192)
    split_overlap: int = Field(default=50, ge=0, le=8191)
    split_unit: Literal["token"] = "token"
    tokenizer_encoding: Literal["o200k_base"] = "o200k_base"
    separators: tuple[str, ...] = ("\n\n", "sentence", "\n", " ")
    sentence_splitter_params: SentenceSplitterSettings = Field(default_factory=SentenceSplitterSettings)

    @field_validator("separators", mode="before")
    @classmethod
    def _validate_separators(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, list):
            value = tuple(value)
        return validate_configured_separators(value)

    @model_validator(mode="after")
    def _validate_overlap(self) -> "RecursiveSplitterSettings":
        if self.split_overlap >= self.split_length:
            raise ValueError("Overlap must be smaller than the token budget")
        return self


class NativeModelGuardSettings(_Settings):
    """Independent native-token admission; directory contents are verified by its existing adapter."""

    enabled: bool = False
    max_tokens: int = Field(default=32_768, ge=1, le=1_000_000)
    local_asset_directory: str | None = Field(default=None, repr=False)
    prefix: str = Field(default="", max_length=8192, repr=False)
    suffix: str = Field(default="", max_length=8192, repr=False)
    include_heading_path: bool = False

    @field_validator("prefix", "suffix")
    @classmethod
    def _validate_affix(cls, value: str) -> str:
        return _validate_utf8(value)

    @field_validator("local_asset_directory")
    @classmethod
    def _validate_directory(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _validate_utf8(value)
        if (
            not value
            or len(value) > 2048
            or value.startswith(("\\\\", "//"))
            or any(ord(character) < 32 for character in value)
            or "://" in value
        ):
            raise ValueError("Tokenizer assets require a bounded local directory")
        path = Path(value)
        if (path.drive or path.root) and not path.is_absolute():
            raise ValueError("Tokenizer assets require an unambiguous local directory")
        if not path.is_absolute():
            path = _ROOT / path
        return str(path.resolve())

    @model_validator(mode="after")
    def _validate_guard(self) -> "NativeModelGuardSettings":
        if self.enabled and self.local_asset_directory is None:
            raise ValueError("Enabled native guard requires an explicit local asset directory")
        if len(self.prefix) + len(self.suffix) > 8192:
            raise ValueError("Native admission affixes exceed the input budget")
        return self


class DocumentProcessingSettings(_Settings):
    """One server-owned profile, shared by ingestion without request/workspace overrides."""

    default_language: Literal["en", "ru"] = "en"
    recursive_splitter: RecursiveSplitterSettings = Field(default_factory=RecursiveSplitterSettings)
    native_model_guard: NativeModelGuardSettings = Field(default_factory=NativeModelGuardSettings)
    _configuration_source: str = PrivateAttr(default="typed_defaults")
    _configuration_sha256: str | None = PrivateAttr(default=None)

    @model_validator(mode="before")
    @classmethod
    def _synchronize_language(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        result = dict(value)
        recursive = result.get("recursive_splitter", {})
        if isinstance(recursive, RecursiveSplitterSettings):
            language = recursive.sentence_splitter_params.language
            if "default_language" not in result:
                result["default_language"] = language
            return result
        if not isinstance(recursive, dict):
            return result
        sentence = recursive.get("sentence_splitter_params", {})
        if isinstance(sentence, SentenceSplitterSettings):
            sentence = sentence.model_dump()
        if not isinstance(sentence, dict):
            return result
        recursive = dict(recursive)
        sentence = dict(sentence)
        if "default_language" in result and "language" not in sentence:
            sentence["language"] = result["default_language"]
        elif "language" in sentence and "default_language" not in result:
            result["default_language"] = sentence["language"]
        recursive["sentence_splitter_params"] = sentence
        result["recursive_splitter"] = recursive
        return result

    @model_validator(mode="after")
    def _validate_language(self) -> "DocumentProcessingSettings":
        if self.default_language != self.recursive_splitter.sentence_splitter_params.language:
            raise ValueError("Default and sentence languages must agree")
        return self

    def to_profile(self) -> ChunkingProfile:
        """Map effective operator values without introducing another splitter or routing implementation."""
        splitter = self.recursive_splitter
        has_sentences = "sentence" in splitter.separators
        return ChunkingProfile(
            profile_revision="text-token-r2",
            unit=splitter.split_unit,
            target_size=splitter.split_length,
            overlap=splitter.split_overlap,
            tokenizer_encoding=splitter.tokenizer_encoding,
            separator_profile_id="prose_token_configured",
            separators=splitter.separators,
            sentence_language=self.default_language if has_sentences else None,
            require_sentences=has_sentences,
            sentence_keep_white_spaces=splitter.sentence_splitter_params.keep_white_spaces,
        )

    def safe_manifest(self) -> dict[str, Any]:
        """Expose effective policy and provenance without local paths or affix contents."""
        manifest = self.model_dump(exclude={"native_model_guard": {"local_asset_directory", "prefix", "suffix"}})
        guard = manifest["native_model_guard"]
        guard["prefix_sha256"] = hashlib.sha256(self.native_model_guard.prefix.encode("utf-8")).hexdigest()
        guard["suffix_sha256"] = hashlib.sha256(self.native_model_guard.suffix.encode("utf-8")).hexdigest()
        manifest["configuration_provenance"] = {
            "source": self._configuration_source,
            "sha256": self._configuration_sha256,
        }
        return manifest


def _yaml_value(node: Node, *, depth: int, remaining: list[int], loader: yaml.SafeLoader) -> Any:
    remaining[0] -= 1
    if depth > 12 or remaining[0] < 0:
        raise DocumentProcessingConfigurationError
    if isinstance(node, ScalarNode) and node.tag in _SCALAR_TAGS:
        return loader.construct_object(node)
    if isinstance(node, SequenceNode) and node.tag == "tag:yaml.org,2002:seq":
        return [_yaml_value(item, depth=depth + 1, remaining=remaining, loader=loader) for item in node.value]
    if isinstance(node, MappingNode) and node.tag == "tag:yaml.org,2002:map":
        result: dict[str, Any] = {}
        for key_node, item in node.value:
            if not isinstance(key_node, ScalarNode) or key_node.tag != "tag:yaml.org,2002:str":
                raise DocumentProcessingConfigurationError
            key = key_node.value
            if key in result or key == "<<":
                raise DocumentProcessingConfigurationError(
                    (
                        ConfigurationIssue(
                            "Duplicate or merge keys are not supported.",
                            line=key_node.start_mark.line + 1,
                            column=key_node.start_mark.column + 1,
                        ),
                    )
                )
            result[key] = _yaml_value(item, depth=depth + 1, remaining=remaining, loader=loader)
        return result
    raise DocumentProcessingConfigurationError


def _parse_configuration(raw: bytes) -> tuple[dict[str, Any], str]:
    try:
        if len(raw) > _MAX_CONFIG_BYTES:
            raise DocumentProcessingConfigurationError
        content = raw.decode("utf-8")
        if any(
            isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None for event in yaml.parse(content)
        ):
            raise DocumentProcessingConfigurationError
        loader = yaml.SafeLoader(content)
        try:
            node = loader.get_single_node()
            if node is None:
                raise DocumentProcessingConfigurationError
            value = _yaml_value(node, depth=0, remaining=[512], loader=loader)
        finally:
            loader.dispose()
        if not isinstance(value, dict) or set(value) != {"document_processing"}:
            raise DocumentProcessingConfigurationError
        if not isinstance(value["document_processing"], dict):
            raise DocumentProcessingConfigurationError
        return value["document_processing"], hashlib.sha256(raw).hexdigest()
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        raise DocumentProcessingConfigurationError(
            (
                ConfigurationIssue(
                    "Invalid YAML syntax.",
                    line=mark.line + 1 if mark else None,
                    column=mark.column + 1 if mark else None,
                ),
            )
        ) from None
    except (UnicodeError, yaml.YAMLError, RecursionError):
        raise DocumentProcessingConfigurationError from None


def _read_configuration(path: Path) -> tuple[dict[str, Any], str]:
    try:
        with path.open("rb") as source:
            return _parse_configuration(source.read(_MAX_CONFIG_BYTES + 1))
    except OSError:
        raise DocumentProcessingConfigurationError from None


def _diagnostic_path(parts: tuple[str | int, ...]) -> str:
    names = [str(part) for part in parts]
    if any(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) is None for name in names):
        return "document_processing"
    return ".".join(("document_processing", *names))[:512]


def validate_document_processing_yaml(
    content: str, *, default_language_override: str | None = None
) -> DocumentProcessingSettings:
    """Validate editor/file content with the same bounded parser and typed runtime schema."""
    try:
        values, digest = _parse_configuration(content.encode("utf-8"))
        settings = DocumentProcessingSettings.model_validate(values)
        if default_language_override is not None:
            overridden = settings.model_dump()
            overridden["default_language"] = default_language_override
            overridden["recursive_splitter"]["sentence_splitter_params"]["language"] = default_language_override
            settings = DocumentProcessingSettings.model_validate(overridden)
        settings.to_profile()
        settings._configuration_source = "selected_operator_file"
        settings._configuration_sha256 = digest
        return settings
    except ValidationError as error:
        issues = tuple(
            ConfigurationIssue(
                "Unsupported setting." if item["type"] == "extra_forbidden" else item["msg"][:240],
                path=_diagnostic_path(item["loc"]),
            )
            for item in error.errors(include_input=False, include_context=False)[:20]
        )
        raise DocumentProcessingConfigurationError(issues) from None
    except UnicodeError:
        raise DocumentProcessingConfigurationError from None


def document_processing_configuration_path(environ: Mapping[str, str]) -> Path:
    """Resolve the single trusted operator source; never accept a browser-selected path."""
    selected = environ.get("WORKBENCH_DOCUMENT_PROCESSING_CONFIG")
    try:
        if selected is None:
            return _DEFAULT_CONFIG
        _validate_utf8(selected)
        if (
            not selected
            or len(selected) > 2048
            or selected.startswith(("\\\\", "//"))
            or any(ord(c) < 32 for c in selected)
            or "://" in selected
        ):
            raise DocumentProcessingConfigurationError
        path = Path(selected)
        if (path.drive or path.root) and not path.is_absolute():
            raise DocumentProcessingConfigurationError
        return (path if path.is_absolute() else _ROOT / path).resolve()
    except (ValueError, OSError):
        raise DocumentProcessingConfigurationError from None


def load_document_processing(environ: Mapping[str, str]) -> DocumentProcessingSettings:
    """Load typed defaults < selected operator YAML < explicit default-language environment override."""
    selected = environ.get("WORKBENCH_DOCUMENT_PROCESSING_CONFIG")
    try:
        path = document_processing_configuration_path(environ)
        values, digest = _read_configuration(path)
        language = environ.get("WORKBENCH_DEFAULT_LANGUAGE")
        if language is not None:
            values["default_language"] = language
            recursive = values.setdefault("recursive_splitter", {})
            if not isinstance(recursive, dict):
                raise DocumentProcessingConfigurationError
            sentence = recursive.setdefault("sentence_splitter_params", {})
            if not isinstance(sentence, dict):
                raise DocumentProcessingConfigurationError
            sentence["language"] = language
        settings = DocumentProcessingSettings.model_validate(values)
        settings._configuration_source = "default_operator_file" if selected is None else "selected_operator_file"
        settings._configuration_sha256 = digest
        return settings
    except ValueError:
        raise DocumentProcessingConfigurationError from None
