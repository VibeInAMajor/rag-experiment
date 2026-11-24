"""Immutable provider-neutral retrieval definitions and bounded operator configuration."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from yaml.events import AliasEvent

from apps.workbench.configuration.document_processing import _yaml_value
from apps.workbench.contracts.schemas import Identifier

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONFIGURATION = _ROOT / "apps" / "workbench" / "profile_registry.yaml"
_MAX_CONFIGURATION_BYTES = 65_536


class ProfileConfigurationError(ValueError):
    """An operator registry is invalid without exposing its source or submitted values."""

    def __init__(self) -> None:
        super().__init__("INVALID_PROFILE_CONFIGURATION")


class ProfileNotAvailable(ValueError):
    """A profile identity, revision or workspace is outside the approved registry."""

    def __init__(self) -> None:
        super().__init__("PROFILE_NOT_AVAILABLE")


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class ProfileDefinition(_ImmutableModel):
    """An immutable policy; lifecycle belongs to a separately audited workspace rollout."""

    profile_id: Identifier
    profile_revision: Identifier
    label: str = Field(min_length=1, max_length=100)
    kind: Literal["lexical", "dense", "hybrid", "bm25"]
    composition: Literal["postgres_fts", "exact_dense", "hnsw_dense", "rrf", "bm25"]
    workspace_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    index_generation_selector: Literal["current"] = "current"
    model_profile_id: Identifier | None = None
    model_profile_revision: Identifier | None = None
    dimensions: int | None = Field(default=None, ge=1, le=16000)
    index_dimensions: int | None = Field(default=None, ge=1, le=16000)
    vector_representation: Literal["vector", "halfvec"] | None = None
    normalization: Literal["none", "l2"] | None = None
    parser_profile_revision: Identifier | None = None
    chunk_profile_revision: Identifier | None = None
    processing_policy_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    capacity_policy_id: Identifier | None = None
    score_type: Literal["postgres_ts_rank_cd", "bm25_raw", "cosine_distance", "rrf_score"]
    score_direction: Literal["higher_is_better", "lower_is_better"]
    max_top_k: int = Field(default=50, ge=1, le=50)
    max_query_characters: int = Field(default=4096, ge=1, le=4096)
    candidate_k: int = Field(default=50, ge=1, le=1000)
    lexical_candidate_k: int | None = Field(default=None, ge=1, le=1000)
    dense_candidate_k: int | None = Field(default=None, ge=1, le=1000)
    rrf_k: int | None = Field(default=None, ge=1, le=1000)
    filtering_policy: Literal["workspace_active_version"] = "workspace_active_version"
    timeout_ms: int = Field(default=10000, ge=1, le=10000)
    max_concurrent: int = Field(default=2, ge=1, le=2)
    max_corpus_chunks: int = Field(default=10000, ge=1, le=10000)
    max_corpus_bytes: int = Field(default=52428800, ge=1, le=52428800)
    capability_requirements: tuple[
        Literal[
            "schema",
            "source_generation",
            "lexical_index",
            "embedding_model",
            "embedding_coverage",
            "ann_index",
            "capacity_policy",
            "bm25_index",
        ],
        ...,
    ] = Field(min_length=1, max_length=8)

    @field_validator("workspace_ids", "capability_requirements", mode="before")
    @classmethod
    def _tuple_values(cls, value: Any) -> Any:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("label")
    @classmethod
    def _safe_label(cls, value: str) -> str:
        if any(
            ord(character) < 32 or ord(character) == 127 or 0xD800 <= ord(character) <= 0xDFFF for character in value
        ):
            raise ValueError("Profile labels must contain printable Unicode")
        return value

    @model_validator(mode="after")
    def _coherent_policy(self) -> "ProfileDefinition":
        if self.profile_id == "bm25-v1" and self.composition != "bm25":
            raise ValueError("The reserved BM25 identity cannot change score semantics")
        if self.profile_id in {"postgres-fts-baseline", "postgres-keyword-v1"} and self.composition != "postgres_fts":
            raise ValueError("Reserved PostgreSQL lexical identities cannot change score semantics")
        semantics = {
            "postgres_fts": ("lexical", "postgres_ts_rank_cd", "higher_is_better"),
            "exact_dense": ("dense", "cosine_distance", "lower_is_better"),
            "hnsw_dense": ("dense", "cosine_distance", "lower_is_better"),
            "rrf": ("hybrid", "rrf_score", "higher_is_better"),
            "bm25": ("bm25", "bm25_raw", "higher_is_better"),
        }
        if (self.kind, self.score_type, self.score_direction) != semantics[self.composition]:
            raise ValueError("Composition, kind and score semantics must agree")
        if len(set(self.workspace_ids)) != len(self.workspace_ids) or len(set(self.capability_requirements)) != len(
            self.capability_requirements
        ):
            raise ValueError("Workspace eligibility and capability requirements must be unique")
        if self.candidate_k < self.max_top_k:
            raise ValueError("Candidate count must cover the maximum top-k")
        required = {"schema", "source_generation"}
        semantic = self.kind in {"dense", "hybrid"}
        if semantic:
            required.update(("embedding_model", "embedding_coverage", "capacity_policy"))
            if any(
                value is None
                for value in (
                    self.model_profile_id,
                    self.model_profile_revision,
                    self.dimensions,
                    self.index_dimensions,
                    self.normalization,
                    self.vector_representation,
                    self.capacity_policy_id,
                )
            ):
                raise ValueError("Semantic profiles require explicit model, representation and capacity references")
            if self.dimensions != self.index_dimensions:
                raise ValueError("Model and index dimensions must agree")
        elif any(
            value is not None
            for value in (
                self.model_profile_id,
                self.model_profile_revision,
                self.dimensions,
                self.index_dimensions,
                self.normalization,
                self.vector_representation,
                self.capacity_policy_id,
            )
        ):
            raise ValueError("Nonsemantic profiles cannot claim model or capacity dependencies")
        if self.composition in {"postgres_fts", "rrf"}:
            required.add("lexical_index")
        if self.composition == "bm25":
            required.add("bm25_index")
        if self.composition == "hnsw_dense":
            required.add("ann_index")
            limit = 4000 if self.vector_representation == "halfvec" else 2000
            if self.dimensions is None or self.dimensions > limit:
                raise ValueError("The ANN representation cannot index the configured dimensions")
        if self.composition == "rrf":
            if self.rrf_k is None or self.lexical_candidate_k is None or self.dense_candidate_k is None:
                raise ValueError("RRF requires explicit fusion and branch candidate counts")
            if min(self.lexical_candidate_k, self.dense_candidate_k) < self.max_top_k:
                raise ValueError("Each RRF branch must cover the maximum top-k")
            if max(self.lexical_candidate_k, self.dense_candidate_k) > self.candidate_k:
                raise ValueError("RRF branches cannot exceed the configured candidate cap")
        elif any(value is not None for value in (self.rrf_k, self.lexical_candidate_k, self.dense_candidate_k)):
            raise ValueError("Only RRF profiles accept fusion or branch candidate policies")
        if not required.issubset(self.capability_requirements):
            raise ValueError("The composition is missing required capability dependencies")
        return self

    @property
    def policy_hash(self) -> str:
        """Fingerprint the complete normalized immutable policy, including its revision."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def canonical_json(self) -> str:
        """Return stable JSON used by durable revisions and equality checks."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ProfileRollout(_ImmutableModel):
    """The current durable selection for one logical profile in an authorized workspace."""

    workspace_id: Identifier
    profile_id: Identifier
    profile_revision: Identifier
    state: Literal["draft", "qualified", "active", "retired"]
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rollout_version: int = Field(ge=1)
    qualified_generation_id: int | None = Field(default=None, ge=0)


class ProfileRegistry(_ImmutableModel):
    """A bounded catalog; historical revisions coexist without ambiguous identities."""

    profiles: tuple[ProfileDefinition, ...] = Field(min_length=1, max_length=32)

    @field_validator("profiles", mode="before")
    @classmethod
    def _profile_tuple(cls, value: Any) -> Any:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def _unique_revisions(self) -> "ProfileRegistry":
        identities = [(item.profile_id, item.profile_revision) for item in self.profiles]
        if len(set(identities)) != len(identities):
            raise ValueError("Profile identities and revisions must be unique")
        return self

    def resolve(self, profile_id: str, *, expected_profile_revision: str, workspace_id: str) -> ProfileDefinition:
        """Resolve an exact revision without any storage or provider operation."""
        for definition in self.profiles:
            if (definition.profile_id, definition.profile_revision) == (profile_id, expected_profile_revision):
                if workspace_id in definition.workspace_ids:
                    return definition
                break
        raise ProfileNotAvailable


def default_profile_registry() -> ProfileRegistry:
    """Preserve the approved lexical baseline; no semantic profile is activated implicitly."""
    return ProfileRegistry(
        profiles=(
            ProfileDefinition(
                profile_id="postgres-fts-baseline",
                profile_revision="postgres-fts-baseline-r1",
                label="PostgreSQL keyword search",
                kind="lexical",
                composition="postgres_fts",
                workspace_ids=("development",),
                score_type="postgres_ts_rank_cd",
                score_direction="higher_is_better",
                capability_requirements=("schema", "source_generation", "lexical_index"),
            ),
        )
    )


def validate_profile_registry_yaml(content: str) -> ProfileRegistry:
    """Reuse the established alias-free, duplicate-key-denying bounded YAML node decoder."""
    try:
        if len(content.encode("utf-8")) > _MAX_CONFIGURATION_BYTES:
            raise ProfileConfigurationError
        if any(
            isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None for event in yaml.parse(content)
        ):
            raise ProfileConfigurationError
        loader = yaml.SafeLoader(content)
        try:
            node = loader.get_single_node()
            if node is None:
                raise ProfileConfigurationError
            value = _yaml_value(node, depth=0, remaining=[4096], loader=loader)
        finally:
            loader.dispose()
        if not isinstance(value, dict) or set(value) != {"profiles"}:
            raise ProfileConfigurationError
        return ProfileRegistry.model_validate(value)
    except (ValueError, UnicodeError, yaml.YAMLError, RecursionError):
        raise ProfileConfigurationError from None


def load_profile_registry(environ: Mapping[str, str]) -> ProfileRegistry:
    """Read a trusted local operator file; configuration cannot select executable classes."""
    selected = environ.get("WORKBENCH_PROFILE_REGISTRY_CONFIG")
    try:
        if selected is not None and (
            not selected
            or len(selected) > 2048
            or selected.startswith(("\\\\", "//"))
            or "://" in selected
            or any(ord(character) < 32 for character in selected)
        ):
            raise ProfileConfigurationError
        path = _DEFAULT_CONFIGURATION if selected is None else Path(selected)
        if (path.drive or path.root) and not path.is_absolute():
            raise ProfileConfigurationError
        path = (path if path.is_absolute() else _ROOT / path).resolve()
        with path.open("rb") as source:
            raw = source.read(_MAX_CONFIGURATION_BYTES + 1)
        if len(raw) > _MAX_CONFIGURATION_BYTES:
            raise ProfileConfigurationError
        return validate_profile_registry_yaml(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise ProfileConfigurationError from None
