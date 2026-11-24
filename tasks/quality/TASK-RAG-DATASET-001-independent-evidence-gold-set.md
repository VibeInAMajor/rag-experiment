# TASK-RAG-DATASET-001 — Build and independently review a source-grounded retrieval evaluation dataset

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; no runtime tests executed  
**Priority:** P0  
**Dependencies:** [DENSE-001](../../tasks/completed/TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md); existing qualified small-document ingestion and parsers; [TPM-001](../../tasks/TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) for later actual embedding. Starter dataset exists but review and gold freeze are pending.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-DATASET-001-independent-evidence-gold-set.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Build and independently review a source-grounded retrieval evaluation dataset

## B. Context / Problem

The 52-case fixture is synthetic and implementation-authored. It is a valuable regression oracle, not a representative independent gold set. A separate corpus and independent judgments are necessary to measure primary evidence and completeness without leakage.

## C. Current Repository State

[52-case fixture](../../apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json) and [embedding evaluator](../../scripts/workbench_embedding_evaluate.py) use fixed original UTF-8 chunk spans and capped fixture queries (100). [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py) maps development workspace, performs HTTP and independent SQL checks; it uses the existing fixture. [parser registry](../../apps/workbench/parsing/parser_registry.py) and [ingestion runbook](../../docs-website/docs/architecture/durable-text-ingestion.md) describe current file limits. [Source-pinned starter dataset](dataset/RETRIEVAL_EVALUATION_SEED_V1.md) is a new draft based on real repo documentation, not independently human-reviewed or blind holdout.

## D. Goal

Deliver a separately versioned independently reviewed corpus, tuning split and reviewer-controlled final holdout, immutable source/facet labels and reproducible validation manifest. Preserve the old fixture unchanged.

## E. Scope

Authorized small real docs, text/MD/Python and qualified text-layer PDF/table, embedded DevOps code/config examples when standalone formats unsupported; label source spans/page/table cells, multi-facet and no-answer, version/tenant decoys; review workflow, freeze and validation.

## F. Non-Goals

No synthetic data counted as independently reviewed; no new parser, large upload, OCR or broad enterprise capacity. No claim of unseen holdout if candidates/labels exposed in repo.

## G. Architecture / Boundaries

Dataset manifest and gold labels remain separate from corpus originals and runtime telemetry. Existing parser/chunker and scoring owners consume immutable source identities; no labels added to searchable text, no model-generated truth as reviewer substitute.

## H. Contracts / Interfaces / Data Model

Corpus manifest: source_id, pinned origin/version/blob SHA + SHA256 original bytes, license/permission, language/format, family, workspace/version/active status, byte/page bounds. Query: id, split, language/intent/family, answerable, expected facts, required facet IDs with alternative evidence spans/pages, primary/support/explicit negatives, review state/adjudication. Unjudged is unknown; no-answer scoped to frozen authorized corpus. Dataset digest includes corpus, labels, split and rubric.

## I. Repository Files / Components Impacted

Starter under tasks/quality/dataset/; add reviewed corpus/manifest and fixture loader extensions under existing evaluation ownership, not a parallel scorer. Reuse [embedding evaluator](../../scripts/workbench_embedding_evaluate.py), [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py), [apps/workbench/embedding/tests/test_embedding_evaluation.py](../../apps/workbench/embedding/tests/test_embedding_evaluation.py), [apps/workbench/retrieval/tests/test_dense_evaluation.py](../../apps/workbench/retrieval/tests/test_dense_evaluation.py). Narrative artifacts Markdown; machine-readable runtime fixtures/manifests only where necessary for tests.

## J. Implementation Requirements

1. Validate starter source Git blob IDs and pinned content, calculate SHA256 from original bytes, audit permission and source authority. Add authorized real documents with diverse topic/source families. Do not ingest the dataset label file, plan, answers or reviewer notes.
2. Aim for 100–300 small docs, 1k–5k active chunks and <50 MiB; first measure actual parser output. Include near-duplicates, contradictory versions, identifiers/error codes, negation, cross-language and multi-document facets. Target >=300 reviewed answerable and >=100 reviewed no-answer/adversarial cases across tuning + held-out; >=50 code/config, >=40 qualified PDF/table, >=30 answerable per EN/RU/UK; report overlaps. Predeclare held-out minimums adequate for chosen confidence gates; increase sampling or mark BLOCKED if underpowered.
3. Split by source/document family and query family (including translations/paraphrases) before tuning. Starter review split is visible and not blind; reserve a final genuinely reviewer-controlled holdout with sealed labels and frozen hashes, inaccessible to tuning agents. Separate corpus availability for each split; no cross-split distractor leakage or duplicates. Use all eligible documents in that split for no-answer verification.
4. Two independent human reviewers label high-impact cases and adjudicate disagreements; review every accepted case, pool candidates from different methods without declaring unjudged chunks irrelevant. Source spans must support each required fact; preserve alternative evidence and hard negatives. Freeze query/corpus/review versions and collect safe reviewer roles, not fabricated identities.
5. Validate unique IDs, file hashes, exact anchor matches, allowed version/workspace, source/facet completeness, query-family split isolation, no answer label ingestion, no-answer absence in authorized corpus, reproducible rebuild and actual small-file ingest/backfill provenance. Publish counts and missing cohorts. Keep starter unreviewed until review; no PASS from source pinning alone.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

Gold labels remain access-controlled; query/label text must not become searchable or leak into ranking prompts.

## L. Testing / Evaluation / Runtime Verification

Schema/anchor validation, mutated source hash, wrong page/version, missing facet, duplicate/paraphrase leakage, no-answer contradiction, ingestion cap refusal, existing fixture regression; actual supported ingestion spot checks.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] Immutable reviewed corpus and qrels with source evidence and digest.
- [ ] Human review/adjudication recorded; independently controlled holdout frozen, with sample/cohort counts or explicit BLOCKED.
- [ ] Gold labels never indexed; actual source/anchor validation and split leakage checks pass.
- [ ] No unsupported format or unreviewed seed presented as qualified gold.

## N. Documentation / Migration / Compatibility / Rollback

Keep seed immutable; new corpus/label revisions are additive. Store restricted holdout labels outside candidate tuning workspace, with reviewed manifests and access procedures. Roll back to prior dataset revision; never overwrite baseline.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.
