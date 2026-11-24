"""Strict server-owned document-processing settings and bounded operator YAML."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from apps.workbench.chunking.chunking_profiles import (
    ChunkingError,
    ChunkingResources,
    DocumentFeatures,
    resolve_profile,
)
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.configuration.document_processing import (
    DocumentProcessingConfigurationError,
    DocumentProcessingSettings,
    NativeModelGuardSettings,
    load_document_processing,
)
from apps.workbench.parsing.parser_registry import ElementKind, FormatId


def _file(tmp_path: Path, content: str) -> dict[str, str]:
    path = tmp_path / "operator.yaml"
    path.write_text(content, encoding="utf-8", newline="\n")
    return {"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": str(path)}


def test_typed_defaults_and_operator_defaults_share_exact_splitter_policy() -> None:
    """Operator startup enables independent Qwen admission without changing the approved token profile."""
    typed = DocumentProcessingSettings()
    operator = ApiSettings.from_env({}).document_processing
    assert typed.recursive_splitter == operator.recursive_splitter
    assert typed.default_language == operator.default_language == "en"
    assert typed.native_model_guard.enabled is False
    assert typed.native_model_guard.local_asset_directory is None
    assert operator.native_model_guard.enabled is True
    assert operator.native_model_guard.max_tokens == 32768
    assert operator.native_model_guard.include_heading_path is False
    assert Path(operator.native_model_guard.local_asset_directory or "").is_absolute()
    profile = operator.to_profile()
    assert (profile.target_size, profile.overlap, profile.unit) == (500, 50, "token")
    assert profile.tokenizer_encoding == "o200k_base"
    assert profile.separators == ("\n\n", "sentence", "\n", " ")
    assert profile.sentence_language == "en"
    assert profile.sentence_keep_white_spaces is True
    assert profile.require_sentences is True
    assert profile.profile_revision == "text-token-r2"


def test_operator_file_then_language_env_override_are_explicit_and_isolated(tmp_path: Path) -> None:
    """Higher-priority language settings synchronize both fields without mutating another settings instance."""
    environment = _file(
        tmp_path,
        "document_processing:\n  default_language: ru\n  recursive_splitter:\n"
        "    split_length: 250\n    split_overlap: 25\n    sentence_splitter_params:\n"
        "      language: ru\n      keep_white_spaces: false\n",
    )
    russian = ApiSettings.from_env(environment).document_processing
    assert russian.to_profile().sentence_language == "ru"
    assert russian.to_profile().sentence_keep_white_spaces is False
    english = ApiSettings.from_env({**environment, "WORKBENCH_DEFAULT_LANGUAGE": "en"}).document_processing
    assert english.default_language == english.recursive_splitter.sentence_splitter_params.language == "en"
    assert (english.to_profile().target_size, english.to_profile().overlap) == (250, 25)
    assert russian.default_language == "ru"
    assert ApiSettings.from_env({}).document_processing.to_profile().target_size == 500
    with pytest.raises(ValidationError):
        english.recursive_splitter.split_length = 123


@pytest.mark.parametrize("nested", [False, True])
def test_one_explicit_language_sets_both_logical_language_fields(nested: bool) -> None:
    """Either documented language setting can be supplied alone without ignored configuration."""
    values = (
        {"recursive_splitter": {"sentence_splitter_params": {"language": "ru"}}}
        if nested
        else {"default_language": "ru"}
    )
    settings = DocumentProcessingSettings.model_validate(values)
    assert settings.default_language == settings.recursive_splitter.sentence_splitter_params.language == "ru"
    assert values == (
        {"recursive_splitter": {"sentence_splitter_params": {"language": "ru"}}}
        if nested
        else {"default_language": "ru"}
    )


@pytest.mark.parametrize(
    "values",
    [
        {"default_language": "uk"},
        {"default_language": "zh"},
        {"default_language": "EN"},
        {"default_language": "en", "recursive_splitter": {"sentence_splitter_params": {"language": "ru"}}},
        {"recursive_splitter": {"split_length": 0}},
        {"recursive_splitter": {"split_length": 8193}},
        {"recursive_splitter": {"split_length": True}},
        {"recursive_splitter": {"split_length": "500"}},
        {"recursive_splitter": {"split_length": 1.5}},
        {"recursive_splitter": {"split_overlap": -1}},
        {"recursive_splitter": {"split_overlap": 500}},
        {"recursive_splitter": {"split_overlap": True}},
        {"recursive_splitter": {"split_unit": "word"}},
        {"recursive_splitter": {"split_unit": "char"}},
        {"recursive_splitter": {"tokenizer_encoding": "qwen3"}},
        {"recursive_splitter": {"tokenizer_encoding": "cl100k_base"}},
        {"recursive_splitter": {"separators": []}},
        {"recursive_splitter": {"separators": ["sentence", "sentence"]}},
        {"recursive_splitter": {"separators": [".*"]}},
        {"recursive_splitter": {"separators": ["\\n"]}},
        {"recursive_splitter": {"separators": [1]}},
        {"recursive_splitter": {"sentence_splitter_params": {"keep_white_spaces": "true"}}},
        {"recursive_splitter": {"sentence_splitter_params": {"language": "uk"}}},
        {"recursive_splitter": {"type": "module.Class"}},
        {"workspace_id": "other-workspace"},
        {"native_model_guard": {"enabled": True}},
        {"native_model_guard": {"max_tokens": 0}},
        {"native_model_guard": {"max_tokens": 1000001}},
        {"native_model_guard": {"max_tokens": True}},
        {"native_model_guard": {"prefix": "p" * 5000, "suffix": "s" * 4000}},
        {"native_model_guard": {"include_heading_path": "false"}},
    ],
)
def test_invalid_policy_values_fail_without_coercion_or_alternate_units(values: dict[str, Any]) -> None:
    """Malformed operator values cannot silently select a different tokenizer or processing mode."""
    with pytest.raises((ValidationError, ChunkingError)):
        DocumentProcessingSettings.model_validate(values)


@pytest.mark.parametrize("directory", ["", "//server/share", "\\\\server\\share", "https://host/model", "bad\x00path"])
def test_model_directory_is_local_and_bounded(directory: str) -> None:
    """Configuration cannot point the offline adapter at a network location or control-bearing path."""
    with pytest.raises(ValidationError):
        NativeModelGuardSettings(local_asset_directory=directory)


def test_relative_asset_directory_is_stable_against_current_working_directory(tmp_path: Path, monkeypatch: Any) -> None:
    """Portable checked-in asset paths resolve against the repository rather than the launching shell."""
    expected = NativeModelGuardSettings(local_asset_directory=".cache/model").local_asset_directory
    monkeypatch.chdir(tmp_path)
    assert NativeModelGuardSettings(local_asset_directory=".cache/model").local_asset_directory == expected


def test_ordered_literal_overrides_and_whitespace_reach_existing_profile() -> None:
    """Operational separator order and whitespace changes are retained by the fingerprinted profile."""
    settings = DocumentProcessingSettings.model_validate(
        {
            "recursive_splitter": {
                "separators": ["sentence", "\n\n", " ", "\n"],
                "sentence_splitter_params": {"keep_white_spaces": False},
            }
        }
    )
    profile = settings.to_profile()
    assert profile.separators == ("sentence", "\n\n", " ", "\n")
    assert profile.sentence_keep_white_spaces is False
    assert asdict(profile) != asdict(DocumentProcessingSettings().to_profile())


def test_explicit_structural_configuration_does_not_require_sentence_assets() -> None:
    """Removing the sentence sentinel is an explicit structural policy, independent of Punkt availability."""
    settings = DocumentProcessingSettings.model_validate({"recursive_splitter": {"separators": ["\n", ".", " "]}})
    decision = resolve_profile(
        DocumentFeatures(FormatId.PLAIN_TEXT, False, (ElementKind.PARAGRAPH,)),
        profile=settings.to_profile(),
        resources=ChunkingResources(token_counter_revision="installed:o200k:sha256"),
    )
    assert decision.profile.separators == ("\n", ".", " ")
    assert decision.profile.require_sentences is False
    assert decision.profile.sentence_language is None
    assert decision.fallback_reasons == ("structural_profile_requested",)


def test_configured_sentences_refuse_missing_resources_instead_of_silently_falling_back() -> None:
    """The configured default requires its declared sentence resource rather than accepting fallback."""
    with pytest.raises(ChunkingError, match="^SENTENCE_RESOURCE_UNAVAILABLE$"):
        resolve_profile(
            DocumentFeatures(FormatId.PLAIN_TEXT, False, (ElementKind.PARAGRAPH,)),
            profile=DocumentProcessingSettings().to_profile(),
            resources=ChunkingResources(token_counter_revision="installed:o200k:sha256"),
        )


@pytest.mark.parametrize(
    "content",
    [
        "",
        "document_processing: null",
        "document_processing: []",
        "document_processing: {}\nother: 1",
        "document_processing: {}\ndocument_processing: {}",
        "document_processing:\n  default_language: en\n  default_language: ru",
        "document_processing: &policy {}",
        "document_processing: {recursive_splitter: &a {separators: [sentence]}, native_model_guard: *a}",
        "document_processing: !!python/object:module.Class {}",
        "document_processing: {1: en}",
        "document_processing: {<<: {default_language: ru}}",
        "document_processing: {}\n---\ndocument_processing: {}",
        "document_processing: {default_language: [}",
        "document_processing:\n  default_language: 2026-11-22",
        "document_processing: " + "[" * 15 + "0" + "]" * 15,
        "document_processing: {recursive_splitter: {separators: [" + ",".join(["sentence"] * 600) + "]}}",
        "document_processing: {}\n#" + "x" * 65536,
    ],
)
def test_yaml_rejects_ambiguous_executable_or_unbounded_documents(tmp_path: Path, content: str) -> None:
    """YAML cannot execute constructors, redefine settings or exhaust unbounded parser structures."""
    with pytest.raises(DocumentProcessingConfigurationError, match="^INVALID_DOCUMENT_PROCESSING_CONFIGURATION$"):
        load_document_processing(_file(tmp_path, content))


def test_missing_and_non_utf8_files_fail_with_sanitized_diagnostics(tmp_path: Path) -> None:
    """Deployment diagnostics expose a stable refusal without filenames or parser excerpts."""
    path = tmp_path / "private-canary.yaml"
    environment = {"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": str(path)}
    for raw in (None, b"\xff\xfe"):
        if raw is not None:
            path.write_bytes(raw)
        with pytest.raises(DocumentProcessingConfigurationError) as error:
            load_document_processing(environment)
        assert "private-canary" not in str(error.value)
        assert error.value.__cause__ is None


def test_invalid_file_settings_do_not_leak_source_values(tmp_path: Path) -> None:
    """Validation errors crossing the environment loader omit private operator input."""
    environment = _file(tmp_path, "document_processing:\n  default_language: private-config-canary\n")
    with pytest.raises(DocumentProcessingConfigurationError) as error:
        ApiSettings.from_env(environment)
    assert "private-config-canary" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize("language", ["", "uk", "zh", "en-us", "RU"])
def test_environment_language_override_is_validated(tmp_path: Path, language: str) -> None:
    """Environment precedence never bypasses the qualified sentence-language allowlist."""
    environment = _file(tmp_path, "document_processing: {}")
    with pytest.raises(DocumentProcessingConfigurationError):
        load_document_processing({**environment, "WORKBENCH_DEFAULT_LANGUAGE": language})


def test_manifest_reports_policy_and_provenance_without_paths_or_raw_affixes(tmp_path: Path) -> None:
    """Metadata preserves policy identity while excluding local directories and embedding affix text."""
    content = (
        "document_processing:\n  native_model_guard:\n    local_asset_directory: private-directory-canary\n"
        "    prefix: private-prefix-canary\n    suffix: private-suffix-canary\n"
    )
    settings = load_document_processing(_file(tmp_path, content))
    manifest = settings.safe_manifest()
    encoded = json.dumps(manifest)
    assert "private-directory-canary" not in encoded
    assert "private-prefix-canary" not in encoded
    assert "private-suffix-canary" not in encoded
    assert manifest["configuration_provenance"] == {
        "source": "selected_operator_file",
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
    }
    assert manifest["native_model_guard"]["prefix_sha256"] == hashlib.sha256(b"private-prefix-canary").hexdigest()
    assert manifest["recursive_splitter"]["split_unit"] == "token"


def test_loading_configuration_does_not_initialize_or_import_native_counter(monkeypatch: Any) -> None:
    """Parsing operator settings has no model-loading or asset-provisioning side effects."""

    def forbid(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("Configuration must not load model assets")

    monkeypatch.setattr("apps.workbench.embedding.model_token_counter.LocalQwenTokenCounter.__init__", forbid)
    assert ApiSettings.from_env({}).document_processing.native_model_guard.enabled is True


def test_environment_has_no_undocumented_splitter_override_surface() -> None:
    """Only the selected YAML and approved language environment field influence processing policy."""
    settings = ApiSettings.from_env(
        {"WORKBENCH_DOCUMENT_SPLIT_LENGTH": "1", "WORKBENCH_DOCUMENT_PROCESSING_READY": "true"}
    )
    assert settings.document_processing.to_profile().target_size == 500


def test_default_operator_file_is_independent_of_working_directory(tmp_path: Path, monkeypatch: Any) -> None:
    """Starting the API from another directory still reads the same checked-in profile."""
    expected = load_document_processing({}).safe_manifest()
    monkeypatch.chdir(tmp_path)
    assert load_document_processing({}).safe_manifest() == expected


@pytest.mark.parametrize("selected", ["", "//server/config.yaml", "https://host/config.yaml", "bad\x00path"])
def test_config_selector_rejects_nonlocal_or_malformed_paths(selected: str) -> None:
    """An invalid explicit selector fails instead of silently loading the default operator file."""
    with pytest.raises(DocumentProcessingConfigurationError):
        load_document_processing({"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": selected})


@pytest.mark.parametrize("field", ["prefix", "suffix", "local_asset_directory"])
@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
def test_native_strings_reject_surrogates_before_runtime_hashing_or_file_access(field: str, surrogate: str) -> None:
    """Unpaired UTF-16 surrogates cannot survive configuration and fail later during ingestion."""
    with pytest.raises(ValidationError) as error:
        NativeModelGuardSettings.model_validate({field: "private-operator-canary" + surrogate})
    assert "private-operator-canary" not in str(error.value)


@pytest.mark.parametrize("field", ["prefix", "suffix", "local_asset_directory"])
def test_yaml_escaped_surrogate_is_a_sanitized_configuration_error(tmp_path: Path, field: str) -> None:
    """Safe YAML string escapes still pass the scalar validation shared by direct settings."""
    environment = _file(
        tmp_path, f'document_processing:\n  native_model_guard:\n    {field}: "private-operator-canary\\uD800"\n'
    )
    with pytest.raises(DocumentProcessingConfigurationError) as error:
        load_document_processing(environment)
    assert str(error.value) == "INVALID_DOCUMENT_PROCESSING_CONFIGURATION"
    assert error.value.__cause__ is None


def test_config_selector_rejects_surrogates_before_path_access() -> None:
    """A malformed environment-selected filename fails with the same stable configuration refusal."""
    with pytest.raises(DocumentProcessingConfigurationError, match="^INVALID_DOCUMENT_PROCESSING_CONFIGURATION$"):
        load_document_processing({"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": "private-operator-canary\ud800.yaml"})
