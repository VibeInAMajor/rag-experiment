"""Immutable policy validation and additive registry migration invariants."""

import json
from typing import Any

import psycopg
import pytest
from alembic import command
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError
from sqlalchemy import text

from apps.workbench.api import db_migrations
from apps.workbench.api.persistence import RecordConflict, WorkspaceContext
from apps.workbench.api.postgres_profiles import read_profile_rollouts, sync_registry, transition_profile
from apps.workbench.api.profile_registry import (
    ProfileConfigurationError,
    ProfileDefinition,
    ProfileNotAvailable,
    ProfileRegistry,
    default_profile_registry,
    load_profile_registry,
    validate_profile_registry_yaml,
)
from apps.workbench.api.tests.conftest import DisposableDatabase


def _definition(**changes: Any) -> ProfileDefinition:
    return ProfileDefinition.model_validate({**default_profile_registry().profiles[0].model_dump(), **changes})


def test_shipped_configuration_matches_the_immutable_baseline() -> None:
    """Default operator YAML normalizes to exactly the preserved baseline policy."""
    registry = load_profile_registry({})
    assert registry == default_profile_registry()
    profile = registry.resolve(
        "postgres-fts-baseline", expected_profile_revision="postgres-fts-baseline-r1", workspace_id="development"
    )
    assert profile.policy_hash == "f4855098f89769756f443f6534b21c5a5f6fa039192e18b3fc7e7ec44b12676d"
    assert profile.score_type == "postgres_ts_rank_cd"
    with pytest.raises(ValidationError):
        profile.max_top_k = 1
    assert isinstance(profile.workspace_ids, tuple)


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_k": 49},
        {"candidate_k": 1001},
        {"max_top_k": 51},
        {"max_top_k": True},
        {"score_direction": "lower_is_better"},
        {"score_type": "rrf_score"},
        {"capability_requirements": ("schema",)},
        {"workspace_ids": ("development", "development")},
        {"composition": "haystack.components.retrievers.ArbitraryRetriever"},
        {"provider_dsn": "credential-value"},
        {"dimensions": 2560},
        {"label": "unsafe\udfff"},
        {"rrf_k": 60},
        {"timeout_ms": 10001},
        {"capacity_policy_id": "unrelated"},
    ],
)
def test_incoherent_or_unbounded_lexical_policies_are_rejected(changes: dict[str, Any]) -> None:
    """A trusted config still cannot alter score meaning, instantiate code or hide missing dependencies."""
    with pytest.raises(ValidationError):
        _definition(**changes)


def test_semantic_and_ann_definitions_require_complete_compatible_references() -> None:
    """Valid planned halfvec metadata does not imply a provider, while incompatible dimensions are refused."""
    semantic = {
        "profile_id": "planned-dense",
        "profile_revision": "planned-dense-r1",
        "kind": "dense",
        "composition": "hnsw_dense",
        "score_type": "cosine_distance",
        "score_direction": "lower_is_better",
        "model_profile_id": "embedding-model",
        "model_profile_revision": "model-r1",
        "dimensions": 2560,
        "index_dimensions": 2560,
        "vector_representation": "halfvec",
        "normalization": "l2",
        "capacity_policy_id": "local-embedding-capacity",
        "capability_requirements": (
            "schema",
            "source_generation",
            "embedding_model",
            "embedding_coverage",
            "ann_index",
            "capacity_policy",
        ),
    }
    profile = _definition(**semantic)
    assert profile.dimensions == 2560
    for changes in (
        {"vector_representation": "vector"},
        {"index_dimensions": 1536},
        {"capacity_policy_id": None},
        {"model_profile_revision": None},
        {"dimensions": 4001, "index_dimensions": 4001},
    ):
        with pytest.raises(ValidationError):
            _definition(**{**semantic, **changes})


def test_historical_revisions_coexist_but_duplicate_identity_is_rejected() -> None:
    """Revision fencing is exact and historical definitions remain available for an explicit rollback."""
    baseline = _definition()
    replacement = _definition(profile_revision="postgres-fts-baseline-r2", candidate_k=60)
    registry = ProfileRegistry(profiles=(baseline, replacement))
    assert (
        registry.resolve(
            baseline.profile_id, expected_profile_revision=replacement.profile_revision, workspace_id="development"
        )
        == replacement
    )
    assert baseline.policy_hash != replacement.policy_hash
    with pytest.raises(ValidationError):
        ProfileRegistry(profiles=(baseline, baseline))
    for revision, workspace in (("missing", "development"), (baseline.profile_revision, "foreign")):
        with pytest.raises(ProfileNotAvailable):
            registry.resolve(baseline.profile_id, expected_profile_revision=revision, workspace_id=workspace)


@pytest.mark.parametrize(
    "content",
    [
        "profiles: []",
        "profiles: []\nprofiles: []",
        "profiles: &p []",
        "profiles: *p",
        "profiles: !!python/object:secret {}",
        "profiles: [{profile_id: a, profile_id: b}]",
        "profiles: []\nuntrusted: credential-value",
        "x" * 65537,
        'profiles: ["\udfff"]',
        "profiles: [{<<: {profile_id: dangerous}}]",
    ],
)
def test_registry_yaml_refuses_executable_ambiguous_or_oversized_input(content: str) -> None:
    """The established bounded node decoder rejects tags/aliases/duplicates without echoing source values."""
    with pytest.raises(ProfileConfigurationError) as caught:
        validate_profile_registry_yaml(content)
    assert str(caught.value) == "INVALID_PROFILE_CONFIGURATION"
    assert "credential-value" not in str(caught.value)


@pytest.mark.integration
def test_populated_generation_schema_upgrade_preserves_records_and_bootstraps_baseline(
    disposable_database: DisposableDatabase,
) -> None:
    """Migration 0004 preserves applied SQL and corpus rows while establishing auditable baseline selection."""
    database = disposable_database
    with db_migrations._connection(database.admin_dsn, transaction=True) as connection:
        db_migrations._ensure_role(connection)
        connection.execute(text("CREATE SCHEMA workbench"))
        command.upgrade(db_migrations._configuration(connection), "0003")
        db_migrations._grant_application(connection)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("INSERT INTO workbench.workspaces(workspace_id,name) VALUES('development','Existing')")
    checksums = {revision: db_migrations.migration_checksum(revision=revision) for revision in ("0001", "0002", "0003")}
    assert db_migrations.migrate(database.admin_dsn).revision == db_migrations.HEAD_REVISION
    assert checksums == {revision: db_migrations.migration_checksum(revision=revision) for revision in checksums}
    with psycopg.connect(database.admin_dsn) as connection:
        assert connection.execute("SELECT workspace_id,name FROM workbench.workspaces").fetchall() == [
            ("development", "Existing")
        ]
        row = connection.execute(
            "SELECT definition,policy_hash FROM workbench.retrieval_profile_revisions "
            "WHERE profile_id='postgres-fts-baseline'"
        ).fetchone()
        assert row is not None
        definition = ProfileDefinition.model_validate(row[0])
        assert definition == default_profile_registry().profiles[0]
        assert definition.policy_hash == row[1]
        assert json.loads(definition.canonical_json()) == row[0]
        assert connection.execute(
            "SELECT state,rollout_version,qualified_generation_id FROM workbench.retrieval_profile_rollouts"
        ).fetchall() == [("active", 1, 0)]
        assert connection.execute("SELECT count(*) FROM workbench.profile_rollout_events").fetchone() == (1,)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="function")
async def test_workspace_rollout_admission_preserves_baseline_at_the_read_bound(
    disposable_database: DisposableDatabase,
) -> None:
    """A normal operator cannot create a 65th binding that would disable every workspace lookup."""
    database = disposable_database
    db_migrations.migrate(database.admin_dsn)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("INSERT INTO workbench.workspaces(workspace_id,name) VALUES('development','Bound test')")
        for position in range(63):
            definition = _definition(profile_id=f"draft-{position}", profile_revision="draft-r1")
            connection.execute(
                "INSERT INTO workbench.retrieval_profile_revisions(profile_id,profile_revision,definition,policy_hash) "
                "VALUES(%s,%s,%s,%s)",
                (
                    definition.profile_id,
                    definition.profile_revision,
                    Jsonb(definition.model_dump(mode="json")),
                    definition.policy_hash,
                ),
            )
            connection.execute(
                "INSERT INTO workbench.retrieval_profile_rollouts(workspace_id,profile_id,profile_revision,"
                "policy_hash,state,rollout_version) VALUES('development',%s,%s,%s,'draft',1)",
                (definition.profile_id, definition.profile_revision, definition.policy_hash),
            )
    rejected = _definition(profile_id="draft-over-limit", profile_revision="draft-r1")
    sync_registry(database.admin_dsn, ProfileRegistry(profiles=(rejected,)))
    with pytest.raises(RecordConflict, match="approved bound"):
        transition_profile(
            database.admin_dsn,
            workspace_id="development",
            profile_id=rejected.profile_id,
            profile_revision=rejected.profile_revision,
            state="draft",
            expected_rollout_version=0,
        )
    async with await AsyncConnection.connect(database.app_dsn, row_factory=dict_row) as connection:
        await connection.execute("SELECT set_config('workbench.workspace_id','development',true)")
        rollouts = await read_profile_rollouts(connection, WorkspaceContext(workspace_id="development"))
    assert len(rollouts) == 64
    assert all(item.profile_id != rejected.profile_id for item in rollouts)
    baseline = next(item for item in rollouts if item.profile_id == "postgres-fts-baseline")
    assert baseline.state == "active" and baseline.rollout_version == 1
    assert baseline.policy_hash == default_profile_registry().profiles[0].policy_hash
    with psycopg.connect(database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM workbench.profile_rollout_events").fetchone() == (64,)
