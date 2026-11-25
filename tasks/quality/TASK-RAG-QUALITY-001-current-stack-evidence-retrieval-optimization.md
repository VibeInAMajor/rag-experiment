# TASK-RAG-QUALITY-001 — Reproduce and improve primary-evidence retrieval using the qualified current stack

**Created:** 2026-11-24  
**Updated:** 2026-11-25  
**Status:** COMPLETE — diagnostic `INSUFFICIENT_WITH_CURRENT_STACK`; all eight OPEN arms and the preserved 52-case replay executed; 156 local and 108 backend tests passed without skips. Release qualification remains blocked; no working profile was promoted.

**Priority:** P0  
**Dependencies:** [DENSE-001](../../tasks/completed/TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md), completed EMBED-001/002, INDEX-001, PROFILE-001, CHUNK-001/002, CONFIG-001, RAG-002; [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md) for reviewed dataset; [TPM-001](../../tasks/TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) valid current local admission.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44; continuation base fde9fbe

**Implementation commits:** `9955252728b3653deb0b5e63339c6ed7c8802ccf` (instruction-bound calibration), `a44c9f9048130c7dcf8081dcbf4f91e6d9a80645` (bounded Windows atomic replacement recovery)

**Target:** tasks/quality/TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Reproduce and improve primary-evidence retrieval using the qualified current stack

## B. Context / Problem

Correct exact SQL is not sufficient evidence quality. The baseline ranks support ahead of primary evidence and misses two primary labels at top five. Optimize only existing model/input/chunk policies before introducing new components.

## C. Current Repository State

[actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md): 102 active vectors, 52 queries (46 answerable and six no-answer), two relevant labels per answerable case; primary@1 31/46 (0.673913), primary@5 44/46 (0.956522), Recall@5 86/92 (0.934783), MRR@10 0.942029, nDCG@5 0.845519 (preserved embedding evidence); all six no-answer cases return neighbors. Exact SQL/HTTP agreement is demonstrated, independent production relevance is not. [embedding evaluator](../../scripts/workbench_embedding_evaluate.py) owns score_ranking/evaluate_query and fixed-span fixtures; [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py) owns real HTTP/SQL identity and latency checks but currently loads its fixed fixture. [DenseService / QueryEmbedder](../../apps/workbench/retrieval/dense.py) and [vector_search_snapshot](../../apps/workbench/postgres/postgres.py) now implement Live exact; [ProfileDefinition](../../apps/workbench/retrieval/profile_registry.py) supports declared future modes but only approved lexical/exact are executable. [EmbeddingProfile / prepare_embedding_request](../../apps/workbench/embedding/embedding.py), [embedding_candidate_input](../../apps/workbench/embedding/embedding_ingestion.py), [apps/workbench/document_processing.yaml](../../apps/workbench/document_processing.yaml) own input and chunk policy. Existing fixture max 100 queries and fixed chunk IDs do not support large reviewed facets/rechunking without bounded schema evolution.

## D. Goal

Recompute preserved baseline independently, then run paired exact and FTS baselines and bounded current-stack tuning on DATASET-001 approved tuning data; select minimal immutable candidate or report INSUFFICIENT_WITH_CURRENT_STACK with failure attribution. This is a diagnostic decision, not final release qualification.

## E. Scope

Baseline reproduction, real parsing/chunking and governed embedding of small reviewed originals, fixed query-instruction and existing chunk policy grid, independent source-span scoring, lexical control, measured latency and regression evidence.

**Runtime reliability amendment (2026-11-25):** two actual long-chunk attempts were refused by the existing governor after 125 and 246 completed HTTP/SQL pairs. An isolated exercise of its unchanged atomic ledger writer reproduced Windows `PermissionError` / `winerror=5` at `Path.replace` (6872 and 713 writes before failure). Include a narrow, bounded retry of the same fsynced temporary-file replacement for Windows access/sharing violations in the existing capacity owner. Preserve atomic publication, charged usage, shared lease and fail-closed quarantine for permanent failure. This does not add an application/API capability or alter ranking/admission policy. Restart all scored arms together on a new v2 execution snapshot; preserve v1 artifacts as interrupted/historical evidence.

## F. Non-Goals

No Hybrid/BM25 integration, cross-encoder, ANN, answerability or generation. No new model or arbitrary threshold, no large-file work. No rewriting immutable baseline or original fixture.

## G. Architecture / Boundaries

Evaluation reuses existing scorer and Live evaluator; ingestion uses existing qualified parsers/chunkers/worker; retrieval uses exact and FTS ports. DATASET-001 owns source labels; QUALITY-002 owns locked final gate. CHUNK-004 owns advanced chunk strategies, not duplicated here.

## H. Contracts / Interfaces / Data Model

Versioned dataset/fixture digest, original evidence facets/grades and source locators; immutable candidate profile/input/chunk revision; run manifests, per-case ranks and latency, status PASS/FAIL/BLOCKED/NOT_EVALUABLE. Distinguish primary hit, primary recall, relevant recall, first-any vs first-primary MRR and graded nDCG; with two relevant labels Recall@1 max 0.5. No-answer metrics separate. Map rechunked outputs back to source spans, count each facet once and report unjudged results.

## I. Repository Files / Components Impacted

**Execution amendment (2026-11-25):** DATASET-001's completed local handoff is recorded in [its actual report](../evidence/dataset-2026-11-24/report.md), despite older PROPOSED headers. Reuse the existing ignored `.local/evaluation-holdout/quality-check/rag_quality/` adapters and source-coverage scorer; preserve their original artifacts. Experiment code/raw predictions remain local; only sanitized reports/metrics and this task are repository deliverables. Existing capacity benchmark ownership may receive a backward-compatible internal instruction-profile qualification parameter, because a changed query instruction must have its own measured profile-bound admission rather than a copied fingerprint. No application, public API, UI, model-provider or CI capability change is authorized by this amendment.

The reliability amendment additionally touches `apps/workbench/embedding/embedding_capacity.py` and its existing `tests/test_embedding_capacity.py`, plus a focused bugfix release note. Do not introduce a second ledger writer or delete/reset real admission state. Local exception-only diagnostics/probes remain ignored. The bounded Windows retry must be tested for successful recovery, permanent failure with preserved old ledger and quarantine, and immediate refusal of unrelated errors before the new uniform experiment snapshot starts.

[embedding evaluator](../../scripts/workbench_embedding_evaluate.py), [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py), [52-case fixture](../../apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json), [EmbeddingProfile / prepare_embedding_request](../../apps/workbench/embedding/embedding.py), [embedding_candidate_input](../../apps/workbench/embedding/embedding_ingestion.py), [apps/workbench/document_processing.yaml](../../apps/workbench/document_processing.yaml), existing embedding/retrieval tests and qualified ingestion owners. Extend existing runner(s) without a competing scorer; preserve exact/lexical contracts and original 52-case fixture. No migrations or UI changes unless separately scoped.

## J. Implementation Requirements

**External-domain baseline requirement:** in addition to the preserved synthetic regression and repository-specific dataset, execute the [external multidisciplinary V1 protocol](dataset/EXTERNAL_EVALUATION_PROTOCOL_V1.md) on all admitted EN/RU/UK query variants after DATASET-001 review. Use actual corpus Markdown ingestion, real governed embeddings and existing HTTP/SQL evaluator; report separately by domain, query intent, language and family, including exact formulas/numbers/code and required facets. Do not treat translations as independent samples, tune on local held-out split or index answer keys. A failure in external evaluation must be explicitly attributed; no quality claim based solely on internal project documents.


1. Independently recompute all baseline metrics from preserved reports, including primary misses checksum-en and code-digest at rank six, hard-negative and six no-answer cases. Reproduce on disposable DB with actual model and exact HTTP/SQL; preserve 52-case regression fixture.
2. Use DATASET-001 agent-verified split; use only its tuning split for iterative decisions. Frozen local holdout remains untouched until QUALITY-002. Extend bounded loader/scorer for original spans, grade 0/1/3, facets, unjudged, explicit split, no-answer and provenance; maintain legacy fixture behavior.
3. Compare same reviewed originals under actual supported parsing/chunking, FTS and exact Dense; report pre-cut candidate coverage and final fixed token budget. Test one variable at a time: Qwen generic vs bounded technical/code instructions, supported chunk lengths 384/500/768 and 0/10/15% overlap where accepted, heading inclusion. Preserve query/document input contract and re-embed/requalify if fingerprint changes; no mismatched vector reuse.
4. Record per-case failures and paired group-level relevance, primary hit, all facets, nDCG, hard negatives, first-primary MRR, p50/p95/p99 embedding/SQL/HTTP, token cost, reembedding churn; compare identical final context budget and report clustered uncertainty. Do not infer answerability from cosine threshold.
5. Target Primary Evidence Hit@1 >=0.95, Primary Evidence Hit@5 >=0.98, relevant evidence Recall@5 >=0.95, graded nDCG@5 >=0.95, All Required Facets@5 >=0.95; critical adequately sized cohorts Primary@5 >=0.95. Predeclared p95 <=1.20x identical baseline load unless an explicitly approved cost/latency trade-off is recorded. Zero observed unauthorized/stale/wrong-profile/source-hash/citation integrity violations. These are proposed point targets, not achieved results. Use existing gold regression targets 44/46 primary@1 and 46/46 primary@5 only diagnostically. Record source-verified tuning results, not release holdout scores. Route exact-term failures to HYBRID/BM25, ranking failures to RERANK, evidence-selection errors to EVIDENCE-002, no-answer to ANSWERABILITY, structural errors to CHUNK-004. A measured NO-GO is valid task outcome; final gate remains blocked if insufficient.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No unreviewed tuning on final holdout; no provider change or new public capability.

## L. Testing / Evaluation / Runtime Verification

**Predeclared local comparison (2026-11-25):** OPEN V2 only (31 originals, 306 translated cases / 102 families), without reading ANSWER or Retrieval-R2 labels. Eight arms: existing 500/50 generic baseline; bounded global technical instruction; bounded global code instruction; 384/38 and 768/77 token policies; 500/0 and 500/75 overlap; existing heading-path input with equivalent native 8192-token admission. Change one semantic policy at a time; record integer overlap rounding and input/representation differences. Fixed candidate top-10 and fixed 2048 `o200k_base` source-content token prefix budget; no label-aware evidence selection. Use a fresh owned DB and real governed re-embedding per arm; new instruction fingerprints require separate fresh calibration/qualification. Baseline source/facet coverage remains sparse: unjudged results stay unknown, full graded nDCG/relevance recall are NOT_EVALUABLE unless exhaustively justified. Family-clustered uncertainty and language/domain/intent groups remain separate; no translation counted as independent sample. No candidate is promoted by this experiment.

Independent metric reference, source-span/facet mapping and unjudged semantics, profile drift, input/Unicode, wrong source/tenant/version, partial coverage, provider outage, ranking and latency regression.

The v1 scored baseline/short-chunk results are historical after the reliability fix. V2 must rerun all eight arms against identical patched owners; retain the original predeclared candidate grid, source/query split, selector and budget. Perform a real-filesystem isolated ledger stress replay before model experiments, and preserve the two pre-fix failures with exact OS category and cleanup evidence.

**Post-hoc diagnostic clarification (2026-11-25):** primary@1 counts a complete reviewed source facet, which can span multiple chunks. After predictions freeze, reuse `EvidenceCoverage` to check individual retrieved chunks and all known-positive-overlap chunks. Separate an available standalone primary below rank one, a standalone primary missing from candidates, and facts with no standalone ingested representation. This is failure attribution/source-metric feasibility, not a new selection target, reranking operation or label-aware context selection; retain the original selector, actual rankings and 2048-token prefixes.

**Concurrent-work isolation (2026-11-25):** backend source changes made by parallel work invalidated one technical-query attempt through the existing after-run hash guard. Preserve it without accepting scores. Resume the last two arms from a separate a44c9f9 source copy with all 96 recorded owner hashes identical, the unchanged 301-file Haystack tree and the same qualified tokenizer/sentence assets. Verify that the canonical model ledger is the same physical file and that its FileLock excludes acquisition through the alternate path; never fork the model admission namespace. Keep concurrent UI/API changes untouched. Record snapshot-scoped checks and the isolated resource-preflight refusal separately from accepted model results.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [x] External multidisciplinary protocol executed on the admitted OPEN V2 delivery with actual ingestion/model/ASGI HTTP/independent SQL. [Report](../evidence/quality-2026-11-25/report.md) and [metrics](../evidence/quality-2026-11-25/metrics.json) include all eight arms, domains, languages, intents and families. ASGI timing excludes browser/network RTT. Only source material was indexed; protected partitions were not evaluated.

- [x] Original 52-case regression preserved and actual metrics independently reproduced. Independent arithmetic and a fresh actual model/HTTP/SQL replay after the writer fix completed on 2026-11-25 under `.local/evaluation-holdout/quality-check/runs/current-stack-2026-11-25-v2/`; historical V1 artifacts are preserved. Primary@1 31/46, primary@5 44/46, Recall@5 86/92 and nDCG@5 0.845519 reproduced exactly; original misses and no-answer behavior remain visible.
- [x] Accepted automated OPEN source-span annotations, actual governed re-embedding, 306 paired questions per arm and a fixed 2048-token source-content prefix were evaluated. The report separates known-facet metrics from unjudged relevance. Full graded nDCG/relevance Recall are explicitly `NOT_EVALUABLE_SPARSE_QRELS`; independent human relevance qualification was not achieved.
- [x] Explicit `INSUFFICIENT_WITH_CURRENT_STACK` verdict recorded. Frozen selection chose `code-query`: P@1 68.97%, P@5 94.64%, AllFacets@5 86.21%, fixed-budget AllFacets 87.36%, HTTP p95 937 ms versus baseline 891 ms. Fixed-budget improvement is +1.15 percentage points with family-bootstrap 95% interval [-1.53; +4.21] points, not established production improvement. Per-case routing to RERANK, CHUNK-004, HYBRID/BM25, EVIDENCE-002 and ANSWERABILITY is in the evidence.
- [x] All 2448 accepted Dense API/SQL checks agree; 2448 paired FTS requests completed, all eight accepted temporary databases and both invalidated-attempt databases were removed. Protected input hashes and original fixture are unchanged; final holdout remains unused and the working database/profile was not modified or promoted. Integrity observations are scoped to this experiment, not a comprehensive security audit.

## N. Documentation / Migration / Compatibility / Rollback

Use tasks/evidence/ for actual reports; retain pinned old profile/generation and roll back explicitly. No original evidence overwrite. Current exact Live stays available; promotion requires fresh qualified profile and subsequent release gate.

The completed [diagnostic report](../evidence/quality-2026-11-25/report.md) records reproduction commands, source identity, calibration cost, token/chunk churn, confidence limits, refusal history and rollback. Local raw evidence and temporary tooling remain under `.local/evaluation-holdout/quality-check/`; only sanitized report/metrics are delivered. The runtime fix preserves ledger format and charged usage. Its isolated 10,000-write verification recovered four actual Windows access failures. Removing the bounded retry restores the previous failure risk; removing the optional calibration instruction restores the previous helper without changing the default fingerprint. No migration, new dependency, model or UI capability was introduced.

## O. Mandatory Completion Checklist

- [x] Reinspect source and dependencies; record reused owners and amended scope if needed. Scope amendments and the existing ingestion/scoring/capacity/HTTP/SQL owners are recorded above.
- [x] Run applicable unit, contract, integration, security, failure and regression tests. Final Hatch checks: 156 local tests and 108 scoped backend tests passed, zero skips; Ruff, formatting and mypy passed for the 154-file frozen Workbench tree, the benchmark and three reporting modules. Backend tests include disposable PostgreSQL, isolation/profile fences, permanent refusal/quarantine and Windows retry recovery. Full Haystack/frontend suites and concurrent production-load qualification were not run; this task did not change their capabilities.
- [x] Link actual commands and evidence, including blocked/unrun gates and limitations. [Report](../evidence/quality-2026-11-25/report.md) and [metrics](../evidence/quality-2026-11-25/metrics.json) contain actual commands, versions, exit codes, test counts and artifact hashes. The final exact-byte audit passed for both deliverables with zero configured-credential, credential-URL, vector-array or private-payload matches; its hashes are retained locally in `artifact-safety-audit.json`. Sparse labels, shared-source correlations, selection on OPEN and untouched final holdout explicitly limit the conclusions.
- [x] Verify immutable profile compatibility, data preservation and rollback. Default profile fingerprint matches the preserved actual replay; each changed query instruction received fresh profile-bound calibration and re-embedding. The isolated source copy shares the canonical physical model ledger and lock; no admission namespace was forked. Concurrent working-tree UI/API changes were preserved and are outside these snapshot-scoped results.
- [x] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates. Source commits are listed above. Changed owners: `scripts/workbench_embedding_capacity_benchmark.py`, `apps/workbench/embedding/embedding_capacity.py`, its existing `tests/test_embedding_capacity.py` and the focused Windows-lock release note; documentation changes are this task and the two evidence files. Completion is a measured diagnostic NO-GO, not release approval.
