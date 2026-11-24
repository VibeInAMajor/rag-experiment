---
title: Approved execution profiles
description: Immutable retrieval policies, workspace rollout state and revision-fenced lexical execution.
---

# Approved execution profiles

**Updated:** 2026-11-23

The application owns the profile registry. A profile identifies a reviewed execution policy, rather than a Python class, browser graph or model endpoint. The existing [lexical search contract](postgres-lexical-search.md) and [persisted source generations](persisted-index-generations.md) remain the retrieval and corpus owners. The [implementation task](../../../tasks/TASK-RAG-PROFILE-001-versioned-retrieval-and-processing-profile-registry.md) records actual qualification evidence.

## Identity and processing provenance

Each `(profile_id, profile_revision)` has one immutable definition and policy hash. Changes to limits, algorithm, score direction, dependencies or processing references require a new revision. Multiple revisions of one ID may coexist for a deliberate rollback; duplicate identity pairs or changed content under an existing revision are refused.

`apps/workbench/profile_registry.yaml` is the shipped baseline catalog. Configuration is capped at 64 KiB and 32 revision definitions; a workspace rollout read is capped at 64 logical profile IDs, including retired bindings. Ordinary administrator operations refuse the 65th binding before writing, preserving existing executable profiles. Definitions use typed tuples and frozen models. Unsafe YAML tags, aliases/anchors, duplicate keys, unknown fields and invalid score/composition/dependency combinations are rejected. These are admission bounds, not an automatic history-deletion policy.

Definition identity and workspace rollout state are separate. A workspace binding selects the current revision and records its lifecycle/audit version. Publishing documents does not rewrite a profile. A profile's source/index selector refers to the authoritative corpus generation, and a lexical generation does not attest semantic model coverage.

Document-processing configuration retains its existing parser/chunker selection and fingerprint. A retrieval policy may link processing provenance, but it does not create a second processing registry or override ingestion settings. `capacity_policy_id` identifies a separately implemented capacity policy; its presence cannot prove TPM admission or model readiness.

## Executable capabilities

The current reviewed composition executes PostgreSQL `simple` FTS and returns raw `postgres_ts_rank_cd`, where larger scores sort first. It keeps the existing Haystack pipeline and source-version predicates. Dense exact/ANN, hybrid/RRF and BM25 definitions do not become executable merely by being stored, labeled active or selected in YAML. Their actual adapters, model/index identity, coverage and capacity dependencies must be implemented and qualified by their owning tasks.

Capabilities lists only profiles that qualify for the authorized workspace and complete current corpus. Draft, retired or unready policies are excluded. The Live selector consumes those executable descriptors; Preview remains a separate fixture mode. The browser cannot authorize a profile by a canvas label or silently choose another profile after an error.

The baseline remains `postgres-fts-baseline` / `postgres-fts-baseline-r1`. Its descriptor, raw score meaning and four-field request stay compatible:

```json
{
  "query": "PostgreSQL",
  "top_k": 5,
  "profile_id": "postgres-fts-baseline",
  "expected_profile_revision": "postgres-fts-baseline-r1"
}
```

Only currently advertised profile identifiers and revisions may be submitted. Server policy owns candidate budgets and query/top-K bounds within the public transport ceiling. Callers cannot submit candidate counts, provider settings, SQL or executable graph fields. `corpus_revision` remains the committed source/index-generation identity. Internal policy/audit provenance is operational metadata, not a calibrated relevance score.

## Admission and concurrent changes

Malformed requests return 400. Unknown IDs and revisions absent from the trusted configuration return 409 before persistence work. A known profile's current retirement or revision requires a bounded durable metadata lookup: a rejected request performs no corpus retrieval or embedding work, but that lookup is not described as zero SQL. An active policy whose actual dependencies fail qualification returns 503.

Runtime composition uses a static allowlist. No profile field is imported as a Python symbol or deserialized as a Haystack graph. Server-resolved workspace authorization precedes profile/dependency work. Profile state, revision and rollout fences prevent a request from executing a different revision under an old response identity. An admitted request either retains its explicitly verified policy or fails safely when its fence no longer holds.

Refresh discovery after a 409 or an operator rollout. The client cancels invalidated work, drops stale execution context and requires an explicit choice when a prior selection is no longer available. Network failures never produce fixture results in a Live run.

## Operator configuration and recovery

`WORKBENCH_PROFILE_REGISTRY_CONFIG` selects the trusted local registry configuration. It is not a request field or a browser-editable provider configuration. Configuration parsing is bounded and strict: duplicate identity pairs, unknown fields, unsafe YAML constructs and invalid policy/dependency combinations refuse without exposing input contents or secrets.

Use the separate administrator for durable configuration publication and lifecycle changes. Application startup does not create tables, apply migrations, seed documents or rewrite profile history. Keep existing source/vector data and applied migrations intact. Retire an unusable new policy and select a previously qualified revision explicitly; never modify its historical definition to simulate rollback. Model changes require their own embedding generations and qualification.

Migration `0004` adds immutable `retrieval_profile_revisions`, workspace-scoped `retrieval_profile_rollouts` and append-only `profile_rollout_events` to the existing schema. The reviewed baseline is bootstrapped for the development workspace; its active flag still requires actual corpus/index/pipeline qualification. Existing applied `0001`–`0003` SQL stays immutable. The generation read-path switch remains separate: public profile execution now requires the governance tables even when `WORKBENCH_CORPUS_SNAPSHOT_MODE=legacy` selects the old bounded corpus read.

Stop old application writers, back up the selected database using the [foundation runbook](postgresql-foundation.md), then upgrade explicitly:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-status
hatch run workbench-api:db-migrate
hatch run workbench-api:db-status
hatch run workbench-api:python -m apps.workbench.postgres.postgres_profiles status
```

The CLI reads `WORKBENCH_DB_ADMIN_DSN`; it never accepts or returns provider credentials through HTTP. To add a policy, create a new immutable revision in the selected trusted catalog, retaining the current revision for a deliberate rollback. Then publish definitions:

```powershell
$env:WORKBENCH_PROFILE_REGISTRY_CONFIG = 'apps/workbench/profile_registry.yaml'
hatch run workbench-api:python -m apps.workbench.postgres.postgres_profiles sync
```

`sync` inserts definitions only. A repeat with the same content is a no-op; content drift under an existing identity refuses the whole sync transaction. Restart the API with the same selected configuration before activating a newly configured identity, so that its in-memory allowlist contains both the current and proposed revisions. Workspace lifecycle changes are read from the database for subsequent requests; editing the YAML file alone does not reload an API process or activate a policy.

The example selects the shipped local catalog; select your reviewed local file when publishing an additional revision. Inspect `status` and supply its current `rollout_version` as `--expected-rollout-version` for a compare-and-set operation. This runnable example requalifies the existing baseline; use a reviewed configured identity/revision when selecting another policy:

```powershell
$profileStatus = hatch run workbench-api:python -m apps.workbench.postgres.postgres_profiles status | ConvertFrom-Json
$baselineStatus = @($profileStatus) | Where-Object profile_id -EQ 'postgres-fts-baseline' | Select-Object -First 1
hatch run workbench-api:python -m apps.workbench.postgres.postgres_profiles promote --workspace-id development --profile-id postgres-fts-baseline --profile-revision postgres-fts-baseline-r1 --expected-rollout-version $baselineStatus.rollout_version
```

`promote` qualifies the exact revision and activates it in one transaction while holding the workspace lock. If either step fails, the preceding selection and audit history remain committed unchanged. `rollback` has the same atomic behavior for a historical revision that remains in the API's trusted catalog. Separate `qualify` and `activate` commands are available when the operator intentionally wants a non-executable qualified state between steps; `activate` refuses an unqualified exact revision. `retire` removes the selected logical profile from executable capabilities. All lifecycle operations preserve source, vector and corpus-generation data. Unsupported semantic/ANN/hybrid/BM25 compositions and unproven processing pins refuse qualification rather than acquiring readiness from an operator flag.

The application role reads scoped rollout state and cannot rewrite immutable definitions or audit history. Diagnostics contain safe identifiers, revisions, policy hashes, counts, durations and trace/error codes. Provider DSNs, credentials, document text, vectors and model responses do not belong in registry definitions or operational logs.

## Qualification boundary

Registry, HTTP and browser checks must cover malformed definitions, same-revision drift, unknown/stale/retired selection, workspace denial, missing dependencies, out-of-bounds inputs, concurrent rollout, deliberate rollback and unchanged lexical golden results. Run real PostgreSQL lifecycle tests in disposable databases. A passing model mock or a stored planned definition does not qualify semantic execution.

The [dated qualification report](../../../tasks/evidence/profile-2026-11-23/report.md) links actual commands and artifacts. The isolated harness uses its own UUID-named database and loopback API on port 8021. Its lifecycle commands are `prepare`, `start`, `verify`, `retire`, `activate`, `restart` and `cleanup` under `hatch run workbench-api:python -m scripts.workbench_profile_smoke`; test DSNs are required. State under `.cache/workbench-profile-smoke/` contains only the owned database identity, process identity and public catalog, while credentials stay in inherited environment references. Do not use this harness to modify the main development database.
