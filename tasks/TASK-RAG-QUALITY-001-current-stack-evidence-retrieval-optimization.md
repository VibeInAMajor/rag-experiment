# TASK-RAG-QUALITY-001 — Improve primary-evidence retrieval quality with the already qualified stack

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** PROPOSED — P0 quality investigation and measurable optimization; **no 95% target has been achieved or qualified by this task**  
**Priority:** P0 — retrieval-quality gate before enterprise answer generation  
**Dependencies:** Completed EMBED-001, EMBED-002, INDEX-001, PROFILE-001, CHUNK-001, CHUNK-002, CONFIG-001, RAG-002; qualified PDF text-layer Gate A. Existing lexical evaluation is available.  
**Related, not implemented prerequisites for this task:** DENSE-001 (Live Dense HTTP), HYBRID-001 (RRF), ANN-001, OPS-001, CHUNK-004; future answerability/abstention and generation require separate approval.  
**Source reviewed:** `fed2febdbaba8ab954a986ca856a2a35e4f3f634`; persisted measured evidence dated 2026-11-24.  
**Task location:** `tasks/TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md`

## A. Title

Improve the quality, reproducibility and evidence ranking of **existing offline/evaluation-capable exact-cosine retrieval** by tuning qualified query/document preparation and existing chunking policies, without inventing new Live retrieval features.

## B. Context / Problem

The embedding ingestion work is technically reliable, but enterprise-quality evidence selection is not yet demonstrated. The current model is **Qwen3-Embedding-4B, 2560 dimensions**, with 102 eligible active evaluation chunks, 46 answerable queries and 6 no-answer queries. The synthetic test set and relevance labels were authored during the implementation session, not independently judged. Exact PostgreSQL cosine evaluation found high top-five coverage but repeatedly ranked *supporting evidence ahead of the direct answer*, and missed primary evidence in Top-5 for two cases. The current application does **not** implement Live Dense HTTP, hybrid fusion, reranking, an answer generator or a no-answer abstention decision.

The desired enterprise quality is around **95% or higher on meaningful, correctly defined metrics**, not 95% mechanically imposed on every @k number. With two relevant chunks per answerable case, **Recall@1 is mathematically capped at 50%**; requiring Recall@1 >= 95% would be invalid. The correct critical top-one measures are **Primary Evidence Hit@1** and graded **nDCG@1**, not raw Recall@1.

The task must determine (1) how much can be improved using **already available components**, (2) what observed blockers require separately scoped new features, and (3) whether a reproducible, independently labeled production-quality gate passes. Do not promise an improvement without actually executing paired runs.

## C. Current Repository State

**Source and ownership reinspection (2026-11-24):**

| Evidence / current component | Verified present behavior | Boundary or limitation |
| --- | --- | --- |
| [Measured report](evidence/embedding-2026-11-24/report.md), [before](evidence/embedding-2026-11-24/acceptance-quality-before.json), [after](evidence/embedding-2026-11-24/acceptance-quality-after.json) | Actual governed query embeddings and persisted exact cosine over one complete 102-chunk generation. Before/after relevance unchanged; provenance/tenant/version/profile/generation integrity passed. | Synthetic, agent-authored labels; no human-reviewed production-domain benchmark. |
| `scripts/workbench_embedding_evaluate.py` | Reuses existing fixture loader, original-span/source-hash checks, actual governed query embedding, exact PostgreSQL vector results, per-case Recall/Primary Recall/MRR/nDCG and grouped reports. `--run` requires explicit disposable test DB and capacity configuration. | Offline/evaluation path, **not** a user-facing Dense HTTP retrieval profile. Current fixture schema caps 100 queries; extending evaluator/fixture contract requires targeted tests. |
| `apps/workbench/embedding/embedding.py::EmbeddingProfile` and `prepare_embedding_request` | Qualified query format is `Instruct: {query_instruction}\nQuery: {query}`; default instruction is `Given a web search query, retrieve relevant passages that answer the query`. Profile has immutable fingerprint; document inputs are separately prepared. | Changing query instruction affects profile identity and must not silently pair incompatible vectors/generations or mutate the qualified default. |
| `apps/workbench/embedding/embedding_ingestion.py::embedding_candidate_input` | Reuses `ModelTokenAdmission`, effective chunking policy, exact provider input and stable source-independent cache input revision `durable-document-input-r2`. | Document-input policy and fingerprint changes can require re-embedding; unchanged-chunk reuse must be proven, not assumed. |
| `apps/workbench/document_processing.yaml`, `apps/workbench/configuration/document_processing.py`, `apps/workbench/chunking/chunking_profiles.py` | Existing configurable prose split length/overlap, separators, language policy, native token guard, optional heading-path inclusion; Python AST and qualified layout-aware text PDF processing already exist. | Reindexing a document can change chunk IDs, relevant-set denominators and cached vectors; compare candidates against original evidence/facets, not only old chunk IDs. |
| `apps/workbench/retrieval/lexical.py`, `apps/workbench/retrieval/profile_registry.py` | Live PostgreSQL lexical FTS exists; registry recognizes typed semantic/hybrid definitions but only approved lexical execution is active by default. | **Do not present configured profile schemas as deployed Dense/Hybrid functionality.** |
| [DENSE-001](TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md), [HYBRID-001](TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md), [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md), [CHUNK-004](TASK-RAG-CHUNK-004-policy-benchmark-and-tiered-enrichment.md) | Existing separate specifications own future HTTP dense, RRF hybrid, operations quality gates, chunking benchmarks. | These features are **PROPOSED**, not available for the current-stack optimization. Do not duplicate their production implementations. |
| `apps/workbench/embedding_profiles.yaml` and `apps/workbench/embedding/embedding_config.py` | Default configuration disabled, explicit qualification-only model composition; measured profile requires pinned local runtime and capacity admission. | No implicit production semantic capability or arbitrary provider switch. |
| `apps/workbench/persistence/models.py` and existing PostgreSQL embedding ports | Workspace-scoped storage/provenance with complete-generation safety. | Development workspace resolver is **not** production authentication. |

**Exact, reproducible measured baseline (46 answerable / 6 no-answer queries, each answerable case has two relevant labels):**

| Metric | @1 | @5 | @10 |
| --- | ---: | ---: | ---: |
| Relevant-chunk Recall | 0.445652 (41/92) | 0.934783 (86/92) | 1.000000 (92/92) |
| Primary Evidence Recall (one primary label per case) | 0.673913 (31/46) | 0.956522 (44/46) | 1.000000 (46/46) |
| MRR (first **any** relevant evidence) | 0.891304 | 0.942029 | 0.942029 |
| nDCG (grades 3=primary, 1=support, 0=other) | 0.704969 | 0.845519 | 0.863413 |

Additional findings from actual per-case reports:
- Rank one is **primary** in 31/46, **supporting** in 10/46, and **nonrelevant** in 5/46. First-any-relevant MRR is therefore not a substitute for primary-evidence ranking.
- `checksum-en` and `code-digest` have their primary evidence at **rank 6**, outside a Top-5 generator context.
- `control-marlin-en` puts a labeled hard negative first; `checksum-ru`, `clock-ru` and `region-en` rank a nonrelevant item first.
- The **four-query** code cohort reports Primary@1=0.50, Primary@5=0.75, nDCG@5=0.6981; these are alerts, **not** reliable general code-quality estimates.
- The 12 cross-language cases report Recall@5=0.9583 and Primary@5=1.0, but remain too small to establish deployment-wide multilingual accuracy.
- All six no-answer queries get nearest neighbors; no abstention decision exists. Unanswerable top cosine similarities overlap low-similarity answerable cases, so a naive single global threshold cannot be declared a qualified solution.
- A controlled ten-minute workload reports concurrent query p95 about **2047 ms**, but this is not a complete Live HTTP Dense latency SLA and does not prove concurrent Ollama generation capacity.

**Current gate:** source/audit evidence establishes a correct experimental baseline, **not enterprise-quality production readiness**. Verify the fixture, implementations and scoped test results again before modifying code.

## D. Goal

With **the already-qualified embedding adapter, exact PostgreSQL cosine retrieval, lexical FTS diagnostic baseline, documented chunking/configuration and existing scorer**, identify and implement only evidence-backed, minimal tuning that measurably improves the rank of **direct, sufficient, authorized evidence**. Produce:
1. a frozen independent gold set and unmodified baseline;
2. controlled paired candidate runs with cost, latency and relevance per cohort;
3. a best-qualified **current-stack** candidate or explicit `INSUFFICIENT_WITH_CURRENT_STACK` result;
4. a concrete handoff to DENSE-001/HYBRID-001/CHUNK-004 or a separately approved answerability/reranking task for remaining gaps.

Never replace missing evidence with a fabricated 95% claim.

## E. Scope

1. **Baseline reproduction and metric audit:** pin fixture/model/generation/source SHA/retrieved chunk identities and independently recompute report values, handling no-answer separately.
2. **Human-reviewed evaluation data:** retain the existing 52-case synthetic fixture as a regression set and add a separate, versioned, independently reviewed, leakage-controlled holdout of real-world-style authorized TXT/Markdown, Python/DevOps configuration and qualified text-layer PDF/table queries.
3. **Query-input optimization using existing model:** measure the default generic Qwen instruction vs bounded, task-oriented retrieval instructions and supported multilingual prompt variants, through the **same** `EmbeddingPort`, exact tokenizer/admission path and local TEI model.
4. **Existing document/chunk policy experiments:** controlled variants of allowed prose split size/overlap/separators, qualified Python AST and PDF layout policies, and existing `native_model_guard.include_heading_path` where proven compatible. Reuse existing chunkers, no speculative custom splitter.
5. **Current retrieval diagnostics:** exact cosine rank at @1/@5/@10 and budget-equivalent larger candidate pools (e.g., 20/50) **only as an offline diagnostic**; compare approved PostgreSQL FTS as a separate lexical baseline. No implicit Hybrid/RRF/semantic HTTP profile.
6. **Failure analysis and gated promotion:** diagnose query/primary/support/hard-negative and source-format error types; promote only an immutable configuration/profile through existing approved mechanisms and explicit compatibility proof; otherwise leave baseline active.

## F. Non-Goals

- No implementation of public Dense HTTP (DENSE-001), RRF/Hybrid (HYBRID-001), ANN/HNSW, reranker, answer-generation/LLM judge, semantic chunker, OCR or VLM.
- No new model, external model-provider dependency, GPU quota, cloud API, training/fine-tuning or unsafe direct vector modifications.
- No arbitrary embedding-dimension reduction, lowering of source integrity checks or score-direction misrepresentation.
- No production tenant authentication, broad UI redesign, application-wide migration or forced rollout of test changes.
- No assertion that metric improvements on an agent-authored synthetic fixture imply production correctness.

## G. Architecture / Boundaries

```text
Reviewed original documents + human-judged evidence facets
          |
          v
Existing parser + approved chunking profiles (isolated candidate generations)
          |
          v
Existing EmbeddingPort -> governed TEI adapter -> existing durable embedding cache/worker
          |
          v
Current PostgreSQL exact-cosine search (plus separate existing FTS control)
          |
          v
Current evaluate_query()/score_ranking()/integrity validators
          |
          v
Paired metric comparison + per-cohort failure analysis + quality decision
```

Affected layers: [x] evaluation, [x] app configuration, [x] chunking candidate policy, [x] embedding input preparation, [x] persistence read-only retrieval, [x] provenance/security, [x] telemetry. [ ] new provider adapter, [ ] new production search API, [ ] index backend migration, [ ] answer generation.

The evaluator and scoring owner remains `scripts/workbench_embedding_evaluate.py` and its existing tests. The parser/chunker and embedding contract owners remain under `apps/workbench/{parsing,chunking,embedding}/`. The source registry, original bytes, generations and full SQL search are authoritative. Use explicit provider-neutral query capability/policy where change is justified; do not build a competing retrieval runtime.

## H. Contracts / Interfaces / Data Model

- **ReviewedQuery:** `query_id, normalized_query_hash, language, intent, format, answerable, expected_evidence_facets[], authorized_source_versions[], required_primary_evidence_ids[], supporting_evidence_ids[], forbidden_evidence_ids[], review_status, reviewer_role, label_revision`. Human labels attach to **immutable original source spans/pages/blocks**; map to each candidate's chunk IDs for fair rechunking evaluation.
- **EvaluationCandidate:** `candidate_id, embedding_profile_fingerprint, model_digest, tokenizer_digest, query_instruction_hash, document_input_revision, chunk_policy_revision, generation, exact_search_settings, score_type, top_k, token_context_budget, dataset_digest`.
- **EvaluationRun:** per-query ranked IDs, relevance grades, primary rank, hard negatives, no-answer result, provenance checks, group/format/language, stage timings, provider-reported token use, cost/VRAM where measured; `status=PASS|FAIL|BLOCKED|NOT_EVALUABLE`.
- **Metric definitions:** `primary_hit@k` = fraction of answerable queries containing verified primary evidence within first k; `all_required_facets@k` = fraction containing every mandatory facet; `recall@k` is relevant-evidence fraction with declared denominator; `hit@k`, `MRR@k` (first any-relevant), `primary_MRR@k` (first primary), `nDCG@k` with existing grade/gain semantics; query-weighted macro and pooled micro are separate labels. Compute 95% confidence intervals by grouped/clustered bootstrap where meaningful.
- **No-answer metrics:** separately record `forced_neighbor_rate`, candidate false-accept/false-reject tradeoff and calibration curves. No runtime `abstained` claim until an approved answerability decision actually exists.
- **Compatibility:** if a query instruction, document preparation or chunking change modifies a full immutable embedding profile fingerprint, **do not** reuse mismatched stored vectors under that profile. Re-qualify/re-embed in isolated workspaces or prove an allowed, versioned query-only compatibility contract with tests; preserve old profile/generation and cache correctness.
- Existing fixed fixture's `EvaluationFixture.queries` cap 100 is insufficient for robust independent gold; version/extend fixture schema carefully and preserve old fixture loader and metric semantics.

## I. Repository Files / Components Impacted

**Inspect/reuse first:**
- [`scripts/workbench_embedding_evaluate.py`](../scripts/workbench_embedding_evaluate.py), `apps/workbench/embedding/tests/test_embedding_evaluation.py`.
- [`apps/workbench/embedding/embedding.py`](../apps/workbench/embedding/embedding.py) `EmbeddingProfile`, `prepare_embedding_request` and [`embedding_ingestion.py`](../apps/workbench/embedding/embedding_ingestion.py) `embedding_candidate_input`.
- [`apps/workbench/embedding/embedding_adapters.py`](../apps/workbench/embedding/embedding_adapters.py) `TeiEmbeddingAdapter` and existing governed capacity owner.
- [`apps/workbench/chunking/chunking_profiles.py`](../apps/workbench/chunking/chunking_profiles.py), [`apps/workbench/configuration/document_processing.py`](../apps/workbench/configuration/document_processing.py), [`apps/workbench/document_processing.yaml`](../apps/workbench/document_processing.yaml).
- [`apps/workbench/retrieval/lexical.py`](../apps/workbench/retrieval/lexical.py), `apps/workbench/postgres/`, `apps/workbench/persistence/models.py`.
- [`apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json`](../apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json), baseline JSON under [`tasks/evidence/embedding-2026-11-24/`](evidence/embedding-2026-11-24/report.md).

**Expected changes:** narrowly extend existing evaluator and tests; add reviewed gold fixtures under the existing embedding evaluation owner; add a dedicated evidence report under `tasks/evidence/`; only amend approved processing/profile configuration when independent quality and compatibility tests pass. Do not create a second search API, registry, scoring implementation or embedding orchestration layer.

**MUST NOT change:** `haystack/` upstream, applied migrations, existing immutable source/vector records, original 2026-11-24 evidence, current Live lexical ranking, existing default model profile or Preview fixtures without a separate explicitly scoped approval. Re-scope this file **before** any further layer is necessary.

## J. Implementation Requirements

**J1 — Reproduce baseline before tuning.**
- Independently compute 31/46 primary@1, 44/46 primary@5, 86/92 Recall@5, nDCG@5=0.845519, primary rank-six misses and the six no-answer cases from the preserved per-case JSON.
- Verify the exact evaluator's relevance semantics, all-eligible source set and 102-vector generation; pin original hashes/model revision/TEI deployment/fixture SHA. A baseline reproduction is `FAIL` if its inputs changed without versioning.
- Record **Primary@1 as 31/46**, not a misleading 67.4% without denominator. Do not use Recall@1 >=95%: its current upper bound is 50%.

**J2 — Create independent review-quality evidence.**
- Preserve the synthetic 52-case regression set unchanged.
- Target **at least 300 independently reviewed answerable queries and 100 explicit no-answer/adversarial queries**, with **at least 50 independently reviewed code/configuration** cases, **at least 40 qualified PDF/table** cases and **at least 30 answerable cases per supported EN/RU/UK language** (overlaps allowed and identified). If corpus/legal access prevents this, publish counts, confidence intervals and `BLOCKED` rather than treating synthetic fixtures as representative.
- Include exact identifiers, symbol names, typos, error codes, commands, version-specific instructions, negations, multi-facet queries, paraphrases, cross-language answers, near-duplicates, stale versions, cross-workspace decoys, hard negatives and unanswered prompts.
- Two reviewers should independently label high-impact cases; disagreements must be adjudicated and retained. Unjudged chunks are **not assumed nonrelevant**; incomplete pooling is a reported evidence risk.
- Hold out query families and source documents separately from tuning/training; no tuning on held-out cases, leaked paraphrases or cherry-picking failures.

**J3 — Diagnose within current stack (one variable at a time).**
- Audit exact Qwen `Instruct:/Query:` input bytes, normalization, max tokens and model/profile attestation; verify document input has the expected no-query-instruction path.
- Test a *small frozen grid* of predeclared query instructions: current generic web-search instruction; technical documentation direct-evidence instruction; code/configuration identifier instruction; optional multilingual instruction only if qualified. Do not dynamically choose based on untrusted workspace/query without approved profile routing.
- Isolate predeclared current-config chunking variants (e.g. approved 384/500/768 model/token-safe prose sizes with 0/10/15% overlap **only where accepted by the actual parser and native-token constraints**; supported AST/PDF profile variants; heading inclusion on/off). Re-embed and regenerate fully scoped candidates when required.
- Compare exact dense against existing lexical FTS **without** merging scores or claiming hybrid support. Larger candidate pools may diagnose primary-rank misses but are not a real reranker or an improvement to @1.
- Attribute cases to semantic intent, wrong language, duplicated context, code identifier miss, heading loss, splitting of a numeric/table row, source-version confusion, hard-negative semantic collision or unsupported visual evidence. Verify attribution against original source; no unsupported root-cause claims.

**J4 — Paired evaluation with independent safety/latency gates.**
- Use the *same* judged original-evidence facets and strict workspace/version/generation per variant. Rechunked candidate chunk IDs must be mapped back to source evidence and counted honestly, with explicit uncovered/ambiguous facets.
- Compare same top-k and same **final context-token budget**; report p50/p95/p99 query embedding and SQL separately, provider requests/tokens and time, GPU RSS/VRAM if available, index-generation cost and cache/reembedding churn.
- Produce per-case transitions (improved/regressed/unchanged), group-level metrics, query-family clustered uncertainty, and complete reproducible artifact manifests.
- No-answer score calibration can be studied offline; a cosine threshold alone MUST NOT be labeled production answerability.
- Preserve exact 2560-dimension/float normalization and score direction. Any security/provenance mismatch = immediate hard fail independent of recall gain.

**J5 — Production-relevant targets (aspirational until measured).**
- On **independent holdout**, desired point estimates: `Primary Evidence Hit@1 >= 0.95`, `Primary Evidence Hit@5 >= 0.98`, `Relevant Evidence Recall@5 >= 0.95`, `nDCG@5 >= 0.95`, `All Required Facets@5 >= 0.95`; group-level `Primary@5 >= 0.95` for every adequately sized critical format/language/code cohort. No significant degradation in other cohorts.
- On the **original 46-query diagnostic set**, 95% Primary@1 means **at least 44/46**, not 43/46. 98% Primary@5 means **46/46**. These are **diagnostic targets only**, not evidence of production readiness.
- Statistical release rule: report per-cohort uncertainty and sample counts; for high-risk enterprise activation, require a **95% confidence lower bound >=0.95** on selected critical success rates, or explicit risk-owner approval of a weaker validated gate. Never infer this from 46 cases. For nDCG report grouped bootstrap bounds without pretending a binary binomial interval applies.
- Required safety: **zero** wrong-tenant/stale-version/profile/generation/source-hash evidence in tested scenarios; no incorrect source/page citations among verified cases; no unbounded runtime or confidential-content logging. These are zero-observed-error acceptance tests, not proof of zero future risk.
- Operational non-regression: candidate query p95 <= baseline p95 * 1.20 under an identical shared-load profile (proposed budget, must be qualified); reject unmeasured cost/VRAM expansion.
- **Answerability production gate remains BLOCKED** until an approved runtime decision can distinguish insufficient evidence and safely abstain. Independently require false acceptance on no-answer cases <=5% and false abstention on answerable cases <=5% once implemented; these rates cannot be claimed from forced-neighbor output.

**J6 — Outcome classification and handoff.**
- If current components reach targets, document the single minimal, versioned policy change, perform isolated real TEI/PostgreSQL re-qualification, obtain approval, and only then plan Live activation under DENSE-001. Roll back to pinned baseline on any negative gate.
- If tuning fails 95% targets, preserve an honest `INSUFFICIENT_WITH_CURRENT_STACK` verdict, ranked failure cohorts and measured evidence. Specifically route exact-term/code misses to HYBRID-001, primary-evidence rank collisions to a separately approved reranking task, no-answer to answerability policy, long-context/chunk errors to CHUNK-004, and runtime semantic exposure to DENSE-001. Do not implement these missing components under this task.
- Task completion is a **reproducible experiment plus truthful decision**; the enterprise production acceptance is a **separate gate**, never an automatic result of completing the specification.

## K. Security / Governance / Observability

- Use disposable, authorized evaluation workspaces and private gold-label access; no real customer documents without explicit permission and documented retention.
- All vector and FTS reads MUST use server-derived `WorkspaceContext` and PostgreSQL RLS; enforce one eligible active version/model profile/generation for each ranking.
- Hard negatives, stale versions and foreign tenants must not be treated as just lower-relevance results when they breach authorization or provenance; such a breach fails the experiment.
- Never record query plaintext, source content, original asset paths, embeddings, model prompts, API secrets, TEI URLs containing credentials or sensitive labels in ordinary logs. Where gold text is necessary, store it in access-controlled fixtures, not operational traces.
- Report safe query IDs, digest, parser/chunker/model/profile revisions, cohort, relevance grades, counts, ranks, latency, token usage, workspace-scoped generation and failure codes. Retain paired output with controls against data leakage, high-cardinality production logging and prompt-injection.
- No automatic internet access, provider download, data exfiltration, unsafe code evaluation or GPU oversubscription to improve test scores.

## L. Testing / Evaluation / Runtime Verification

**Required regression and negative tests:**

1. Existing `score_ranking` and evaluator oracle tests, with independent reference metric calculations for two-relevant-label upper bounds, graded nDCG, first-primary vs first-any MRR and no-answer null semantics.
2. Same query across unchanged original source/version/generation; stale-version and wrong-workspace decoys; changed embedding profile fingerprint, wrong 2560 dimension, changed tokenizer/revision, malformed query instruction, provider unavailable, incomplete embedding coverage.
3. Query text formatting and token-count exactness for all candidate instructions, including EN/RU/UK Unicode and code symbols; no silent truncation.
4. Chunking/grid tests preserving original spans, PDF page and table-row provenance, Python symbols/line anchors, overlapping windows and local cache reuse rules.
5. Paired candidate/holdout ranking and label adjudication checks; no fixture duplication or train/test query-family leakage; scorer reports nullable unanswerable metrics correctly.
6. Throughput, p50/p95/p99 inference+SQL, shared GPU capacity, resource errors and complete generation readiness under controlled load.
7. Negative case `primary@1` decreases while MRR increases: ranking decision MUST not falsely claim success from MRR alone.
8. Baseline exact cosine and Live lexical regression; maintain current API capability truth, no public semantic profile and no Preview substitution.

**Commands (run only with approved environment, actual Hatch configuration and disposable database):**
- `hatch --version` as prerequisite.
- `hatch run workbench-api:python -m scripts.workbench_embedding_evaluate` for offline fixture validation; live `--run` only with approved test DSN, capacity configuration and qualified local model; record actual invocation, never use operator main DB.
- `hatch run workbench-api:test` (or documented targeted tests) plus the existing API check/types/format tasks. If frontend is not modified, UI build is `N/A — not in scope`; otherwise run its configured checks.
- All measured evidence must identify the executed runner, source/fixture/model/profile SHA, selected candidate and exact artifact output. **Do not mark tests PASS from this specification.**

## M. Acceptance Criteria

- [ ] Source ownership, available-vs-proposed capability matrix and baseline 2026-11-24 results are verified against current code and preserved artifacts.
- [ ] Baseline 46 answerable + six no-answer results independently recomputed, including 31/46 primary@1, 44/46 primary@5, 86/92 recall@5, primary rank-six misses, graded nDCG and first-any MRR caveat.
- [ ] Existing 52-case fixture is preserved unchanged and a separately reviewed holdout is published with explicit counts, labels, sampling, provenance and leakage controls (or marked BLOCKED with evidence).
- [ ] A bounded, reproducible one-variable-at-a-time candidate grid runs on **actual** persisted vectors and the qualified model, not fake similarity scores.
- [ ] Each candidate reports primary-hit@1/@5, recall@5/@10, nDCG@5/@10, first-primary MRR, exact evidence facets, hard negatives, no-answer diagnostics, latency/resource cost and supported cohorts.
- [ ] No unqualified feature is represented as implemented (Dense HTTP, Hybrid/RRF, ANN, reranking, answerability, answer generation or production tenancy).
- [ ] No integrity/authorization/profile/generation or original-source evidence regression.
- [ ] Final current-stack policy decision has measured before/after comparison, complete failure cases, uncertainty, rollout/rollback instructions and documented promotion approval; otherwise explicit `INSUFFICIENT_WITH_CURRENT_STACK` and exact successor-task handoff.
- [ ] Production activation remains blocked until independent holdout, safety, answerability, operational and runtime profile gates pass; no fabricated 95% result.
- [ ] Source-aware Markdown evidence report and checked task completion record reflect exact tests run and unrun.

## N. Documentation / Migration / Compatibility / Rollback

- Record all findings and run manifests under a new subfolder in `tasks/evidence/` using Markdown for narrative deliverables; structured JSON/CI evidence may be generated only as machine-readable runtime records, not replacement project documents.
- Do not overwrite `tasks/evidence/embedding-2026-11-24/` evidence. Publish current-stack ranking failure matrix, metrics, uncertainty, candidate comparison and explicit production-readiness status.
- If a candidate changes only experimental input policy, it must remain behind an immutable evaluation profile. A promoted input-format/profile change requires versioned capability compatibility, full coverage proof and any affected vector re-embedding; preserve previous vectors/cache/generation and exact lexical behavior.
- No applied SQL migration edit; no change to Live API DTO without a separate approved implementation task. Existing DENSE-001/HYBRID-001/OPS-001/CHUNK-004 remain owners of future production functionality.
- Rollback returns the active policy pointer to the last qualified revision; old active chunks, source versions, embedding mappings and index generation remain intact. Avoid deletion of original or source provenance on failed quality experiments.
- If project structure, qualified profile, model or evaluator changes materially, stop and update Sections C/I/H before implementation.

## O. Mandatory Completion Checklist

- [ ] Repository and evidence actually reread; no stale ownership path or misleading feature claim.
- [ ] All A–O scope and current-stack-vs-planned boundaries honored.
- [ ] Existing evaluator/embedding/chunker/FTS/persistence logic reused; no duplicate runtime, scoring implementation or API.
- [ ] Source hashes, dataset/label identity, model/profile/generation and exact query-input policy pinned.
- [ ] Synthetic baseline, independent reviewed holdout, no-answer/negative cases and paired measurement verified.
- [ ] Real tests and performance checks executed on disposable authorized resources; report exact commands, results, skipped and blocked gates.
- [ ] Enterprise 95% metric aspirations evaluated honestly; production confidence intervals and no-answer gate not misrepresented.
- [ ] Security/provenance/tenant/version/score direction untouched or regressions resolved.
- [ ] Operator instructions, limitations, follow-up dependency handoff and rollback documented.
- [ ] Changed source files, measured artifacts, tested configuration, issue findings and resulting commit recorded.
- [ ] This task may become COMPLETE only after the validated current-stack experiment and decision; **enterprise production approval is separate**.
