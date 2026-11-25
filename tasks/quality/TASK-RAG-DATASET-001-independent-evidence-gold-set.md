# TASK-RAG-DATASET-001 — Build and validate a local source-grounded retrieval evaluation dataset

**Created:** 2026-11-24  
**Updated:** 2026-11-26  
**Status:** COMPLETE_LOCAL — original delivery and OPEN baseline executed; later stress fixtures remain downstream work  
**Priority:** P0  
**Dependencies:** [DENSE-001](../../tasks/completed/TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md); existing qualified small-document ingestion and parsers; [TPM-001](../../tasks/TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) for later actual embedding. See [actual local delivery report](../evidence/dataset-2026-11-24/report.md); separate ranking-judgment completion belongs to [DATASET-002](TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md).  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-DATASET-001-independent-evidence-gold-set.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Build and validate a local source-grounded retrieval evaluation dataset

## B. Context / Problem

The 52-case fixture is synthetic and implementation-authored. It is a valuable regression oracle, not a representative independent gold set. A separate corpus and source-verified judgments are necessary to measure primary evidence and completeness without leakage.

## C. Current Repository State

[52-case fixture](../../apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json) and [embedding evaluator](../../scripts/workbench_embedding_evaluate.py) use fixed original UTF-8 chunk spans and capped fixture queries (100). [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py) maps development workspace, performs HTTP and independent SQL checks; it uses the existing fixture. [parser registry](../../apps/workbench/parsing/parser_registry.py) and [ingestion runbook](../../docs-website/docs/architecture/durable-text-ingestion.md) describe current file limits. [Source-pinned starter dataset](dataset/RETRIEVAL_EVALUATION_SEED_V1.md) is a new draft based on real repo documentation, not yet source-verified or a held-out split.

## D. Goal

Deliver a separately versioned agent-verified corpus, tuning split and locally frozen final holdout, immutable source/facet labels and reproducible validation manifest. Preserve the old fixture unchanged.

## E. Scope

Authorized small real docs, text/MD/Python and qualified text-layer PDF/table, embedded DevOps code/config examples when standalone formats unsupported; label source spans/page/table cells, multi-facet and no-answer, version/tenant decoys; review workflow, freeze and validation.

## F. Non-Goals

No synthetic data counted as real source-grounded evidence; no new parser, large upload, OCR or broad enterprise capacity. No claim of unseen holdout if candidates/labels exposed in repo.

## G. Architecture / Boundaries

Dataset manifest and gold labels remain separate from corpus originals and runtime telemetry. Existing parser/chunker and scoring owners consume immutable source identities; no labels added to searchable text, no model-generated truth without original-source verification.

## H. Contracts / Interfaces / Data Model

Corpus manifest: source_id, pinned origin/version/blob SHA + SHA256 original bytes, license/permission, language/format, family, workspace/version/active status, byte/page bounds. Query: id, split, language/intent/family, answerable, expected facts, required facet IDs with alternative evidence spans/pages, primary/support/explicit negatives, review state/adjudication. Unjudged is unknown; no-answer scoped to frozen authorized corpus. Dataset digest includes corpus, labels, split and rubric.

## I. Repository Files / Components Impacted

Starter under tasks/quality/dataset/; add reviewed corpus/manifest and fixture loader extensions under existing evaluation ownership, not a parallel scorer. Reuse [embedding evaluator](../../scripts/workbench_embedding_evaluate.py), [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py), [apps/workbench/embedding/tests/test_embedding_evaluation.py](../../apps/workbench/embedding/tests/test_embedding_evaluation.py), [apps/workbench/retrieval/tests/test_dense_evaluation.py](../../apps/workbench/retrieval/tests/test_dense_evaluation.py). Narrative artifacts Markdown; machine-readable runtime fixtures/manifests only where necessary for tests.

## J. Implementation Requirements

**Agent execution contract:** [Local holdout and reference answers](DATASET-001-AGENT-EXECUTION-AND-HOLDOUT.md). The coding agent MUST create actual local questions and answers, verify against originals, freeze the split and run available checks without requesting human reviewers, separate identities or security infrastructure. Local held-out means excluded from tuning by convention and evaluator input separation; it is not a security boundary or independent certification.

**External-domain corpus (2026-11-24):** [External multidisciplinary dataset V1](dataset/README.md) includes 31 actual externally sourced Markdown documents, 87 candidate answerable families/261 multilingual cases, 15 candidate no-answer families/45 cases, pinned manifests and localized answer keys. This complements the repo-specific seed and must be reviewed and admitted separately using the [external protocol](dataset/EXTERNAL_EVALUATION_PROTOCOL_V1.md). Do not index the question/answer files. The visible external set is open diagnostic material, not a held-out split. Extend the existing bounded evaluator to ingest only corpus files, map gold ranges to persisted source spans, join stable query IDs to reviewed answers, retain translation-family grouping and validate all documents/306 rows; review no-answer and alternatives. Prepare a local held-out split; no human-review or custody prerequisite applies.


1. Validate starter source Git blob IDs and pinned content, calculate SHA256 from original bytes, audit permission and source authority. Add authorized real documents with diverse topic/source families. Do not ingest the dataset label file, plan, answers or reviewer notes.
2. Aim for 100–300 small docs, 1k–5k active chunks and <50 MiB; first measure actual parser output. Include near-duplicates, contradictory versions, identifiers/error codes, negation, cross-language and multi-document facets. Target >=300 reviewed answerable and >=100 reviewed no-answer/adversarial cases across tuning + held-out; >=50 code/config, >=40 qualified PDF/table, >=30 answerable per EN/RU/UK; report overlaps. Treat these counts as planning targets; report actual counts, missing cohorts and uncertainty. Underpowered samples limit conclusions, not local development.
3. Split by source/document family and query family (including translations/paraphrases) before tuning. Starter review split is visible and not blind; reserve a local holdout with separate question/answer files and frozen hashes; exclude it from tuning inputs. Separate corpus availability for each split; no cross-split distractor leakage or duplicates. Use all eligible documents in that split for no-answer verification.
4. The coding agent checks every accepted case in a second source-grounded pass, including high-impact cases; reject unresolved disagreements and pool candidates without declaring unjudged chunks irrelevant. Source spans must support each required fact; preserve alternative evidence and hard negatives. Freeze query/corpus/review versions and record the automated verification method and actual results.
5. Validate unique IDs, file hashes, exact anchor matches, allowed version/workspace, source/facet completeness, query-family split isolation, no answer label ingestion, no-answer absence in authorized corpus, reproducible rebuild and actual small-file ingest/backfill provenance. Publish counts and missing cohorts. Keep starter unreviewed until review; no PASS from source pinning alone.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

### Additive stress fixtures (later quality consumers) — 2026-11-26

The [actual local delivery report](../evidence/dataset-2026-11-24/report.md) records COMPLETE_LOCAL; do not reopen or overwrite it for this amendment. For subsequent consumer tasks, the coding agent prepares additive, versioned hard-negative/contradiction, changed-definition, OOD, noise and source-fidelity fixtures as required by the [quality/content plan](RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md). Keep original-source qrels and answers separate from runtime inputs, freeze paired clean/perturbed query labels, distinguish active conflicts from stale/foreign negatives, and retain unknowns. Visual cases require qualified producer and original image/region gold; unavailable modalities remain NOT_EVALUABLE. The existing local holdout stays untouched during tuning; no reviewer or special storage prerequisite.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Local fixtures/labels retain source license, provenance and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

Gold labels remain evaluator-only; query/label text must not become searchable or leak into ranking prompts.

## L. Testing / Evaluation / Runtime Verification

Schema/anchor validation, mutated source hash, wrong page/version, missing facet, duplicate/paraphrase leakage, no-answer contradiction, ingestion cap refusal, existing fixture regression; actual supported ingestion spot checks.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] External V1 actual corpus and all 306 query/answer candidate IDs validated, agent-verified/admitted or excluded with reasons; executable existing evaluator adapter and source-range mapping verified.

- [ ] Immutable reviewed corpus and qrels with source evidence and digest.
- [ ] Agent verification recorded; local holdout frozen with actual sample/cohort counts and disclosed limitations.
- [ ] Gold labels never indexed; actual source/anchor validation and split leakage checks pass.
- [ ] No unsupported format or unreviewed seed presented as qualified gold.

- [ ] When a downstream stress suite is executed, its additive fixture revision, source checks and split/perturbation manifest are recorded; prior local delivery is preserved.

## N. Documentation / Migration / Compatibility / Rollback

Keep seed immutable; new corpus/label revisions are additive. Store local holdout under tasks/quality/holdout/ with a versioned manifest and exclude it from tuning and indexing. Roll back to prior dataset revision; never overwrite baseline.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.
