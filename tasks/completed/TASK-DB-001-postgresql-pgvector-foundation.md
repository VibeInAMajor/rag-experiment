# TASK-DB-001-postgresql-pgvector-foundation

**Created:** 2026-11-20  
**Updated:** 2026-11-21  
**Status:** COMPLETE  
**Priority:** P0 · required before live retrieval  
**Dependencies:** TASK-API-001, TASK-ARCH-001  
**Repository snapshot reviewed:** `5e7086364f62d4f15b7370e55767a8f84ed4dc14`

## A. Title

Provision persistent PostgreSQL + pgvector storage, migrations, and an application-owned document-store boundary

## B. Context / Problem

PostgreSQL with pgvector is a **target product dependency**, not an optional later replacement for an in-memory prototype. The first real retrieval slice must query persisted documents from the target database. The API bootstrap has no database connection, schema migrations, seed mechanism, or persistent workspace/source/chunk records. Deliver this foundation **after API bootstrap and before the first retrieval task**.

PostgreSQL keyword search is not automatically BM25: native full-text ranking uses `ts_rank`/`ts_rank_cd`. The chosen lexical baseline must be named and scored truthfully. A separate BM25-capable PostgreSQL extension may be evaluated later but is not silently introduced here.

## C. Current Repository State

Starting evidence rechecked in the working tree on 2026-11-20, with completion verification on 2026-11-21:

- Architecture reconciliation already made PostgreSQL + pgvector authoritative and archived the original OpenSearch proposal. The dated implementation plan remains a reference; this task does not rewrite it.
- The existing Workbench catalog contains `PgvectorEmbeddingRetriever` and `InMemoryBM25Retriever` display labels; neither is permission to execute an algorithm or select a data store.
- The real construction validator on port 8010 and FastAPI discovery bootstrap on port 8011 already exist. The bootstrap initially had no persistence dependency; claiming no Workbench backend existed would be obsolete.
- `apps/workbench/api/{application,config,contracts,services,boundary}.py` own the existing health/capability/error contracts. Core Haystack 3.5.0 provides reusable framework APIs but no application registry tables.
- At task start, no Workbench Compose database service, migration or persistent application store existed. Those additions and the actual PostgreSQL verification are recorded below rather than inferred from class labels.
- The earlier memory-only RAG task was stopped before retrieval implementation. Native PostgreSQL FTS is the selected first persisted lexical primitive; the canonical contract now reserves `postgres-keyword-v1` and `postgres_ts_rank_cd` for the subsequent HTTP slice. `bm25-v1` remains reserved for genuine BM25 and is not advertised.

## D. Goal

A reproducible local PostgreSQL instance with pgvector, versioned migrations, and a backend persistence adapter can store and retrieve workspace-scoped source/chunk records across application and database restarts. The same database holds the future vector representation; a deterministic synthetic-vector smoke test proves pgvector reads/writes without claiming that real embeddings already exist.

## E. Scope

1. Add a pinned, reproducible **development** PostgreSQL + pgvector service configuration, persistent volume, health check, explicit migration command, restricted loopback exposure and no committed credentials.
2. Add a schema migration mechanism and initial schema with `workspaces`, `sources`, `source_versions` and `chunks` (or equivalent justified existing Haystack-compatible table layout). Persist `workspace_id`, `source_id`, `version_id`, `chunk_id`, title, content, source/chunk metadata and activation state. Define composite keys/foreign keys and indexes that prevent cross-workspace reference mistakes.
3. Enable and verify the `vector` extension; support **nullable** embeddings for lexical-only content. Pin the active embedding profile and vector dimension **only after the canonical profile is verified**. Reject dimensional mismatches explicitly. An unset embedding is not an embedding failure for a lexical-only record.
4. Provide persistent lexical-search support through PostgreSQL `tsvector` + GIN and `ts_rank_cd` (or the equivalent documented `PgvectorKeywordRetriever` capability); persist indexable text in the database rather than a Python in-memory store. Agree on and test the exact text-search language configuration, including identifiers and non-English tokens.
5. Evaluate the existing `pgvector-haystack` integration (`PgvectorDocumentStore`, `PgvectorKeywordRetriever`, `PgvectorEmbeddingRetriever`) against the pinned Haystack 3.5.0 runtime and schema/tenant requirements. **Reuse it if compatible and safe**; otherwise implement only the smallest app-owned SQL/Haystack adapter needed and record why the integration cannot be used without violating isolation or migration control. Avoid duplicate document tables or duplicate writers.
6. Implement a narrowly scoped persistence port, connection/session lifecycle, bounded pooling/timeouts, parameterized queries, transaction management and truthful readiness dependency status. Keep database SDK imports inside the infrastructure adapter.
7. Provide an **explicit** idempotent development seed command using 5–10 non-sensitive deterministic passages. Do not seed live data implicitly on every server startup. Include a second workspace in negative-test fixtures; public API access remains restricted to server-resolved development authorization context.
8. Add unit, migration and container-backed integration tests, a restart smoke, and a database operations Markdown runbook. No real embedding inference is required.

## F. Non-Goals

No Ollama/TEI provider, GPU inference, HNSW performance claim, hybrid retrieval, reranking, document upload, Delta Detector, TPM limiter, distributed workers, production RBAC, or arbitrary graph execution. No OpenSearch, no `InMemoryDocumentStore` as a Live data source, and no assumption that PostgreSQL native FTS implements BM25. Do not introduce `pg_search`/ParadeDB or other search extensions without a separately reviewed need, deployment/licensing decision and task scope update.

## G. Architecture / Boundaries

Affected: [x] Port/interface/contract, [x] Persistence/vector store, [x] Security/governance, [x] Observability/evidence, [x] Infrastructure/CI/CD, [x] Documentation; [ ] Domain/core except minimal stable record contracts, [ ] Retrieval/RAG beyond storage-ready primitives, [ ] Agent runtime. Application services depend on provider-neutral persistence interfaces; database connector and optional Haystack Pgvector integration remain behind the persistence adapter. The HTTP API never executes arbitrary SQL received from clients. The backend/DB schema, not mutable React state, is authoritative for workspace/source/version ownership.

```text
Workbench UI -> FastAPI -> application search/document services -> persistence port
                                                              -> PostgreSQL/pgvector adapter
                                                              -> PostgreSQL durable volume
```

## H. Contracts / Interfaces / Data Model

Selected foundation: immutable image digest for PostgreSQL 17.10 + pgvector 0.8.2, Alembic 1.20.1 revision `0001` with reviewed SQL/checksum, Psycopg 3.3.9 + pool 3.3.3, Python pgvector 0.5.1. `pgvector-haystack` 8.2.1 is evaluated only in a separate compatibility environment; the application uses the narrow SQL adapter because integration-owned flat tables/DDL do not satisfy the scoped migration contract.

No semantic model profile has been verified or fixed in a vector-column type. The nullable dimensionless `vector` column references a dimension registry. Only a development synthetic 3-dimensional profile is initially enabled for storage tests; a separate disposable test verifies full 2560-dimensional storage without claiming model inference or ANN support. No HNSW/IVFFlat index is created.

- Persist `Workspace`, `Source`, `SourceVersion` and `Chunk` records (names may follow existing app conventions), including `workspace_id`, `source_id`, `version_id`, `chunk_id`, `content`, `title`, optional `page`, content/profile hashes where relevant, and a single active version per source or an explicitly documented equivalent.
- `embedding` is nullable and annotated by `embedding_profile_id` and validated `dimensions`; semantic results MUST NOT be advertised until populated with compatible vectors.
- Persistence methods must include server-resolved workspace context for list/get/write/search and return stable typed failures for missing/unauthorized workspace, unavailable database, invalid embedding dimension and migration incompatibility.
- `GET /api/v1/health/ready` must become 503 when the database or required schema is unavailable; `GET /api/v1/capabilities` must not advertise lexical/vector execution merely because the extension exists.
- All source/chunk writes must be transactional; seed identities are deterministic and are scoped by workspace. Per-source active-version publication must not expose partial chunks.
- `score_type` of PostgreSQL native full-text retrieval is `postgres_ts_rank_cd`, **not** `bm25_raw`; this task prepares the storage/score contract, with the HTTP search endpoint implemented in `TASK-RAG-001`.
- The initial candidate vector size (e.g. the earlier Qwen full dimension of 2560) is **not proof of the running TEI profile**. Verify actual model/profile/dimension before fixing a vector-column migration. If using 2560-dimension full-precision `vector`, note that pgvector HNSW/IVFFlat indexes on `vector` are limited to 2,000 dimensions; acceptable first-slice options are exact vector search or an explicitly benchmarked `halfvec(2560)` expression ANN index. Never silently truncate to 2000/1536 dimensions.

## I. Repository Files / Components Impacted

Expected additions/updates, subject to existing project conventions discovered in `TASK-ARCH-001` and `TASK-API-001`:

- `apps/workbench/api/` persistence adapter, connection settings, seed command and tests.
- `apps/workbench/api/migrations/` or a documented conventional migration directory within the app; schema revisions are reviewed and reversible.
- A root-level or dedicated `apps/workbench/` Compose YAML containing **only** infrastructure required for the local task, plus a development environment example with placeholders only.
- `apps/workbench/api/` readiness composition/capability registration.
- `apps/workbench/web/README.md` and a concise PostgreSQL runbook under `docs-website/docs/`.
- Isolated Hatch dependency/tooling configuration, reproducible storage/compatibility probe scripts, release note and evidence files. The canonical runtime contract is reconciled with the selected native-FTS semantics; project routing documents point to implemented persistence.

MUST NOT modify `haystack/` framework internals, UI fixture text/preview replay, existing graph import/export, unrelated documents, or the user-authored implementation plan beyond the separate architecture reconciliation task.

## J. Implementation Requirements

- MUST pin and record PostgreSQL, pgvector, migration tool and selected Haystack integration versions with a compatibility smoke test; do not assume documentation for a different Haystack version guarantees API compatibility.
- MUST use PostgreSQL as the **only Live document corpus** from the first retrieval implementation onward; seed documents must survive API and database restarts.
- MUST use migrations to create/alter schema; never `DROP`/recreate persistent tables on service initialization. Demo seed is explicit, idempotent and must refuse to overwrite non-demo data.
- MUST validate migration head, extension availability, workspace-scoped FKs, and actual committed rows before readiness/capability advertisement.
- MUST use actual PostgreSQL-backed lexical ranking. Do not relabel `ts_rank_cd` as BM25, and do not attach `InMemoryBM25Retriever` to `PgvectorDocumentStore`.
- MUST keep `workspace_id` out of untrusted filter-overwrite paths; every read/write is scoped by authenticated/server-resolved workspace. For dev, scope to a single explicit authorized context and deny other IDs.
- MUST verify embedding dimensions for both storage and retrieval; do not create a 2560-dimensional `vector_cosine_ops` HNSW index that exceeds pgvector's supported indexed vector dimensions.
- MUST NOT claim persistent data safety, workspace security or ANN performance without corresponding integration tests.

## K. Security / Governance / Observability

Credentials resolved at runtime from environment/secret references, never embedded in Compose source, fixtures, task files, logs, client bundles or exception bodies. App DB role should not be a superuser and should not have schema migration privileges by default. Limit network exposure to loopback for dev. Use prepared/parameterized SQL. Validate tenant references using database constraints and server-resolved context; add negative cross-workspace tests (including guessed source IDs) without calling a dev-only resolver production-grade authorization. Log `trace_id`, database operation, safe workspace/source IDs, elapsed time and error classification; never log documents, embeddings, connection strings or secrets. Define seed retention/cleanup rules and protect migrations against destructive changes.

## L. Testing / Evaluation / Runtime Verification

Run via the repository's Hatch policy; target the actual new app paths instead of non-existent generic `src tests` directories. Required evidence:

- Static/contract tests for configuration, parameterized repository operations, invalid dimension, schema/contract alignment and adapter compatibility.
- Fresh-instance migrations, repeat migrations, rollback on a disposable DB, incompatible-schema rejection and schema/extension readiness failures.
- Real PostgreSQL + pgvector smoke: insert non-sensitive chunks, verify DB rows, query PostgreSQL FTS and scores, insert an explicit synthetic vector of the **configured dimension**, query nearest neighbors by cosine distance, reject wrong dimensions.
- Kill/restart API, then PostgreSQL container **without deleting the volume**; confirm the same workspace/source/chunk IDs, content and lexical retrieval remain available, without automatic re-seed.
- Cross-workspace read/search attempts, duplicate seed command, mid-transaction failure and canceled/failed connection recovery. Confirm no partial publication or cross-workspace records.
- Focused `ruff`/`pytest -q`, exact migration commands, container health, `EXPLAIN`/index evidence and redacted connection-status traces. No result may be marked PASS before the tests actually run.

## M. Acceptance Criteria

- [x] Pinned PostgreSQL + pgvector container starts; `SELECT extname FROM pg_extension WHERE extname = 'vector'` returns the installed extension, and migration state matches expected head.
- [x] Required workspace/source/version/chunk records have enforced keys, foreign keys and a workspace-scoped retrieval path; an explicit dev seed inserts 5–10 deterministic documents.
- [x] PostgreSQL keyword search returns ranked persisted chunks with a documented `postgres_ts_rank_cd` score and `workspace_id` filter; no Live path uses `InMemoryDocumentStore`.
- [x] A configured-dimensional synthetic vector is persisted and retrieved using pgvector distance; a dimension mismatch fails with a controlled error. No unverified ANN index is declared working.
- [x] After API and DB restart without wiping the persistent volume, seeded IDs and content match the pre-restart state exactly and search still works.
- [x] Foreign-workspace access, unavailable DB, wrong schema, duplicate seed and mid-transaction failures are covered and fail closed.
- [x] App/DB adapter tests, migrations, static checks and startup/runbook commands are recorded with real outputs.

## N. Documentation / Migration / Compatibility / Rollback

Initial persistent schema is versioned and created by migrations. Record minimum image/extension versions, selected embedding dimension policy, language configuration, disk volume semantics, seed entrypoint, DB backup and schema rollback instructions. `TASK-ARCH-001` must update older OpenSearch-first claims in the historical plan without erasing their rationale. Later ingestion extends the same tables; later dense/hybrid stages use the same pgvector store and profile dimension policy. Reverting the API code must **not** delete the volume or drop tables. Schema rollback must use reviewed migration steps and backups; automated rollback must not discard customer data.

## O. Mandatory Completion Checklist

- [x] PostgreSQL and pgvector versions, data model, schema migrations and semantic boundaries reviewed.
- [x] Explicit idempotent seed and safe reset semantics verified against real DB.
- [x] Persistent restart test, vector dimension test, real lexical ranking and negative security paths pass.
- [x] No duplicate persistence path, implicit in-memory Live fallback or unverified provider claims.
- [x] Evidence attached: migration outputs, SQL smoke, test logs, readiness, trace IDs and docs.
- [x] `TASK-RAG-001` is enabled only after this task passes its acceptance gate; change status to COMPLETE only with recorded evidence.

### Completion evidence — 2026-11-21

Implemented ownership:
- `apps/workbench/postgres/compose.yaml`, `.env.example`, `create-dev-env.ps1`, `use-dev-env.ps1`: isolated Docker PostgreSQL/pgvector, loopback port 55432, named persistent volume and runtime-only generated credentials. Actual `.env` and backups are ignored.
- `apps/workbench/api/migrations/`, `db_migrations.py`, `db_admin.py`: explicit Alembic `0001`, checksummed up/down SQL, advisory migration locking, exact-head/extension checks and guarded disposable-only rollback. Restricted application login is provisioned separately from the administrator.
- `persistence.py`, `postgres.py`: neutral records/context/errors and app-owned async PostgreSQL adapter. Composite FKs, forced RLS, per-transaction scope, bounded pooling/timeouts, atomic active-version publication, actual FTS ranking and exact compatible-profile vector queries.
- `db_seed.py`, `fixtures/development-corpus.json`: explicit atomic seed of eight development sources. Restart never seeds; unchanged repeat returns zero; changed/non-demo data is refused.
- `database_dependency.py`, API composition/config/contracts/entrypoint and `openapi.json`: safe database dependency state, SecretStr settings, owned pool lifecycle and Windows-compatible event-loop setup. A ready database and a qualified executor are both required for overall readiness; neither the extension nor an injected executor without PostgreSQL can enable a profile.
- New persistence, migration, configuration and helper tests plus updated HTTP contract tests under `apps/workbench/api/tests/`; isolated Hatch runtime/test/compatibility environments in root `pyproject.toml`.
- `scripts/workbench_pgvector_compatibility.py`, `scripts/workbench_storage_smoke.py`: reproducible integration qualification and persistent fingerprint/restart probes.
- [Operations runbook](../docs-website/docs/architecture/postgresql-foundation.md), API/UI READMEs, canonical contract, project routing docs and sidebar; release note `workbench-postgresql-foundation-213771aa8b24f06a.yaml`. Haystack core, frontend preview/fixtures, graph serialization and the dated user-authored implementation plan were not changed by this task.

Reuse and integration decision:
- Reused the existing API composition, `rag-api-v1.0` correlation/error/capability models and Hatch tooling.
- Tested Haystack **3.5.0** with `pgvector-haystack` **8.2.1** against a real disposable database: two documents written; keyword and synthetic cosine results matched expected source; implicit initialization under the restricted application role was refused.
- The integration's flat ID-primary-key table/implicit DDL cannot provide the migration-owned composite source/version schema without duplicate storage or invasive overrides. The single app-owned SQL adapter is therefore selected; no second document table or copied BM25 implementation exists. [Compatibility evidence](evidence/pgvector-compatibility-2026-11-21.json).

Actual commands and outcomes:

| Verification | Observed result |
| --- | --- |
| `hatch --version` | Hatch 1.18.2 |
| `docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml up -d --wait` | Dedicated `rag-workbench-postgres-1` healthy; PostgreSQL 17.10, pgvector image 0.8.2, pinned immutable digest from the runbook |
| `hatch run workbench-api:db-bootstrap` | `application_role_provisioned`; app role is non-superuser, not table owner and has no schema DDL privilege |
| `hatch run workbench-api:db-migrate` / `db-status` | Revision/expected revision `0001`, compatible true, extension version `0.8.2`; repeat migration succeeds |
| `hatch run workbench-api:db-seed` twice | Eight sources inserted, then zero inserted; committed IDs/content unchanged |
| `hatch run workbench-api:test -o log_cli=false --junitxml=tasks/evidence/postgresql-tests-2026-11-21.xml` with explicit test DSNs | **105 passed, 0 skipped**, including **19 real container-backed cases**, final run 7.17 seconds; [JUnit](evidence/postgresql-tests-2026-11-21.xml) |
| `hatch run workbench-api:check` | All checks passed; 25 Python files formatted |
| `hatch run workbench-api:types` | No issues in 25 source files |
| Ruff for both probe scripts | Passed |
| Compatibility probe in `workbench-db-compat` | Passed against pinned library/integration; no model inference |
| Storage probe baseline / after API restart / after database restart | Eight chunks and all source/chunk IDs identical; all three phases have SHA-256 `cc5f32c55c7c0b48870aff3b8aaa83b38f0b014ad20d0bcfaa423a819aadc296` |
| Database stopped while API running | Liveness 200, overall readiness 503, dependency `unavailable`, profiles empty; after restart dependency recovered to ready without re-seeding |
| `pg_dump -Fc`, copy to ignored backup directory, `pg_restore --single-transaction` into a fresh owned disposable database | Migration compatible and same eight rows/content fingerprint; disposable restore database removed afterward |
| Documentation | MDX/GFM compilation for 10 Markdown files, 68 local links and six typed/JSON examples passed; both READMEs and the operations runbook passed Prettier; Git whitespace and release-note YAML checks passed |
| Runtime credential scan | 5,245 tracked/unignored text files checked; no generated credential value found; `.env` and dump paths confirmed ignored |

Persistent/restart/restore, real query scores/durations, trace IDs, index definitions and EXPLAIN outputs are in [storage evidence](evidence/postgresql-restart-2026-11-21.json). The eight-row diagnostic plan chooses the workspace B-tree index; the GIN index is present. This is index/SQL evidence, not a GIN throughput or ANN performance claim.

Tests include fresh/repeated/up/down migrations on owned throwaway databases, checksum/head/extension/RLS drift, application privilege refusal, cross-workspace guessed IDs and FKs, Unicode/identifier lexical terms, NULL embeddings, configured synthetic 3/2560 vectors and dimension rejection, non-demo/modified/duplicate seed, injected mid-publication SQL failure, actual blocked-query cancellation and terminated-backend recovery. Test fixtures share the application's event loop; a fixture-loop mismatch was corrected before the final recovery checks. Temporary test databases were cleaned up. A regression check also proves CRLF/LF checkouts preserve the same migration checksum while changed SQL is rejected.

Intentional contract reconciliation: the first planned PostgreSQL-native HTTP profile is `postgres-keyword-v1` with `postgres_ts_rank_cd`; `bm25-v1`/`bm25_raw` remain reserved for genuine BM25. A typed validator rejects mismatched profile/score combinations. The previous memory-only retrieval task must be reconciled with this foundation and canonical request/error fields before it proceeds. This task does not implement HTTP search or frontend integration.

Limitations: development-only context is not production authentication/RBAC; no TEI/model inference, qualified semantic profile, ANN index, hybrid/RRF or ingestion workflow. Overall API readiness is still 503 while profiles are empty, even when `dependencies.database.status` is ready. The Starlette TestClient transport emits one non-failing httpx deprecation warning. Full upstream Haystack tests, browser tests and full Docusaurus build were not run; relevant application and document checks are recorded instead. No volume or main database was deleted. Persistent backup/log access, retention and deletion remain deployment-owner responsibilities.
