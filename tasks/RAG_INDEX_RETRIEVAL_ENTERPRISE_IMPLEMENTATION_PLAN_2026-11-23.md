# RAG Index, Retrieval and Enterprise Roadmap — Implementation Plan

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** Architecture and ordered task specification; not proof of deployment  
**Scope:** Workbench backend retrieval, original evidence, search index lifecycle, scalable sources and enterprise readiness  
**Repository source snapshot:** 1aa9b2654df0f490781b2a09a5809e111c1f6651

## Executive decision

Keep **PostgreSQL + pgvector** as the authoritative data substrate, separate document/source version and raw original evidence from derived searchable representations, and build additional search execution modes **as explicit, versioned, provider-neutral capabilities**. Current PostgreSQL native FTS and exact vector primitive are not equivalent to real Qwen embeddings, BM25, ANN, hybrid retrieval or a production-tenant system. No silent in-memory corpus, unverified model vectors, generic file-to-Markdown loss, fake citations or cross-tenant access.

The roadmap prioritizes:
1. Persist workspace corpus/index revision at publication rather than hashing all active chunks per query.
2. Qualify the real local text embedding model and versioned profile, backfill vectors durably and expose truthful exact dense retrieval.
3. Add HNSW/halfvec ANN **only after** quality and tenant-filter benchmarks, then use RRF for explicit hybrid profiles.
4. Benchmark genuine PostgreSQL BM25 now, but **do not automatically replace FTS**; deployment follows a separate GO decision and license approval.
5. Keep original PDF/diagram/Mermaid evidence through existing CONTENT-001..005 and add a Live Workbench evidence viewer.
6. Expand through multiworkspace authorization, tenant quotas, queue-driven bulk ingestion, delta reuse, observability and index/asset disaster recovery.
7. Evaluate Microsoft MarkItDown as an optional **derived Markdown representation**, never as replacement for originals or universally superior to Docling.

## 1. Verified starting point

| Concern | Existing implementation | What is NOT yet delivered |
| --- | --- | --- |
| Data | [0001 initial schema](../apps/workbench/api/migrations/0001_initial.up.sql), [0002 jobs](../apps/workbench/api/migrations/0002_ingestion_jobs.up.sql), PostgresPersistence, source/version/Chunk, FORCE RLS; bounded synchronous TXT/Markdown/Python ingestion | Multiworkspace identity/roles, async source jobs, source evidence asset lifecycle |
| Lexical | [PostgresLexicalRetriever](../apps/workbench/api/lexical.py) via Haystack, generated tsvector, GIN and ts_rank_cd; profile postgres-fts-baseline-r1 | Genuine BM25, tiered lexicon and large-corpus query optimization |
| Corpus revision | [_corpus_snapshot](../apps/workbench/api/postgres.py) hashes active chunk/doc metadata for each lexical snapshot | Persisted constant-cost generation and active profile index manifest |
| Vector | Chunk.embedding nullable, embedding_profiles table and [vector_search](../apps/workbench/api/postgres.py) exact cosine | Qualified Qwen inference in ingestion, full backfill, Live Dense profile, HNSW index |
| Workbench | Live keyword profile, Preview and constructor validator; [DocumentsView](../apps/workbench/web/src/views/DocumentsView.tsx) remains fixture-only in inspected source | Dense/Hybrid approved graphs, original evidence browser and live document-management UI |
| Document parsing | Parser registry, qualified TXT/MD/Python; Docling PDF source worker and table/page chunking code; PDF qualification evolves independently | OCR/vision, Mermaid graph, complete original asset evidence architecture |
| Local setup | PG17.10/pgvector0.8.2 pinned container; API local TEI/Qwen target contract | Multi-host deployment, workload SLOs, production RBAC and DR drills |

**Important implementation caution:** the source code continues evolving. Every task must redo Section C inspection before work. A Python class or migration existing is not proof that an endpoint, model or capability has passed runtime tests.

## 2. Target index model and data flows

```text
Untrusted source bytes / connector
  -> verified format + parser / OCR / visual / Mermaid adapters
  -> structured elements + original immutable assets (CONTENT-001)
  -> multiple typed representations and chunking profiles
  -> versioned Chunk metadata + ContentRepresentation and EvidenceReference
  -> lexical text index (PostgreSQL tsvector/GIN)
  -> embedding job and qualified Qwen embedding profile -> full vectors in pgvector
  -> optional qualified ANN physical index (HNSW / halfvec)
  -> immutable source/index generation with active profile pointer

Query -> FastAPI server-authorized workspace -> approved profile registry
   -> native FTS or true BM25 (if approved), exact Dense or ANN
   -> explicit RRF Hybrid if supported
   -> Evidence Resolver (CONTENT-005) -> original PDF/page/diagram/Mermaid
   -> Workbench results with actual source, generation, score and trace
```

**Version dimensions must not be conflated:** SourceVersion identifies immutable uploaded content; ProcessingProfile records parse/normalize/chunk rules; EmbeddingProfile pins model digest/tokenizer/dimensions/instruction; IndexGeneration is the committed searchable snapshot; RetrievalProfile pins search algorithm/index generation/candidate_k/top_k/rrf_k/score semantics. A model update creates a new semantic generation, not an in-place vector identity change.

**Snapshot performance fix:** current _corpus_snapshot() loads/hashes active metadata for each query. INDEX-001 moves this O(number_of_active_chunks) fingerprint to a transactional publication-time manifest, with search loading a constant-cost committed generation and consistent SQL snapshot. Make query-time page/range/source link query not re-hash every chunk. Preserve replay/idempotent unchanged semantics and fallback to explicit last-good profile if new generation is unready.

**Data tiering:** PostgreSQL stores source/version/element metadata, text chunks, provenance links, vector rows, search generations, jobs and RLS. AssetStorePort stores exact original PDF/Office/diagram files or crops and optional derived Markdown. Do not store base64 images inside Chunk.metadata or regard Markdown as canonical bytes.

## 3. Delivery sequence, gates and dependencies

| Order | Task | Gate / outcome |
| ---: | --- | --- |
| 1 | [INDEX-001](TASK-RAG-INDEX-001-persisted-revision-and-consistent-search-snapshots.md) | Search uses persistent committed corpus generation instead of query-time O(N) digest scan |
| 2 | [PROFILE-001](TASK-RAG-PROFILE-001-versioned-retrieval-and-processing-profile-registry.md) | Lexical/Dense/Hybrid and optional BM25 IDs are immutable, qualified and discoverable |
| 3 | [EMBED-001](TASK-RAG-EMBED-001-qualify-local-qwen-embedding-provider.md) | Real TEI/Qwen model/dimension/tokenizer, finite vectors and budget measured |
| 3a | **[TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md)** | One shared 0.92 desired throughput / 0.95 rolling hard admission governor, adapted from pinned previous project with explicit rights and real model qualification |
| 4 | [EMBED-002](TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md) | Durable embedding backfill, coverage, idempotent writes and model-generation pin |
| 5 | [DENSE-001](TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md) | Actual query embed + Haystack + exact cosine SQL and honest Live results |
| 6 | [ANN-001](TASK-RAG-ANN-001-hnsw-halfvec-index-and-tenant-recall-gates.md) | HNSW expression with validated dimension and tenant-filter recall vs exact oracle |
| 7 | [HYBRID-001](TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md) | Approved Haystack lexical+dense RRF, no raw-score mixing, provenance intact |
| Parallel decision | [BM25-001](TASK-RAG-BM25-001-bm25-extension-feasibility-and-quality-gate.md) | A/B benchmark with real BM25, deployment/license assessment and GO/NO-GO |
| Conditional | [BM25-002](TASK-RAG-BM25-002-conditional-postgresql-bm25-search-profile.md) | Only after benchmark GO; additive BM25 profile, never hidden FTS replacement |
| Parallel decision | [CONVERT-001](TASK-RAG-CONVERT-001-microsoft-markitdown-evaluation-and-safe-conversion-adapter.md) | Per-format MarkItDown vs Docling/native GO/NO-GO |
| Evidence foundation | [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) | Exact original assets, structured elements and typed representations |
| Evidence producers | [CONTENT-002](TASK-RAG-CONTENT-002-scanned-pdf-ocr-and-layout.md), [CONTENT-003](TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md), [CONTENT-004](TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md) | Qualified OCR, diagrams/chart data and Mermaid structures with verifiable original refs |
| Evidence consumer | [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) | Authorized original/page/crop/source-range resolution and trust-state verification |
| UI consumer | [EVIDENCE-001](TASK-RAG-EVIDENCE-001-live-original-evidence-and-diagram-viewer.md) | Real PDF/image/Mermaid evidence pane in Live Workbench, no invented sources |
| Enterprise security | [SCALE-001](TASK-RAG-SCALE-001-multiworkspace-identity-authorization-and-tenanted-retrieval.md) | Authenticated multiworkspace, RLS and quota/role isolation |
| Enterprise throughput | [SCALE-002](TASK-RAG-SCALE-002-durable-asynchronous-ingestion-and-tenant-backpressure.md) | Real durable queued uploads/workers/backpressure and per-tenant fairness |
| Efficiency | [DELTA-001](TASK-RAG-DELTA-001-incremental-reindexing-and-embedding-vector-reuse.md) | Safe per-chunk vector reuse only on matching input/model/profile and tenant |
| Operating model | [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) | Cross-stage redacted traces, quality and cost/latency regression dashboard |
| Recovery | [OPS-002](TASK-RAG-OPS-002-index-promotion-backup-and-disaster-recovery.md) | Shadow generations, atomically qualified promotion, DB+asset restore and rollback |

INDEX-001 and PROFILE-001 must not depend on BM25 or production ANN. BM25 is a separate decision gate, so Dense/RRF work is not blocked by a search extension legal review. Evidence content work can progress in parallel with vector work, but original assets must be available before any citation claims.

## 3a. Pinned related-project reuse: embedding capacity, source deltas, chunking

**Donor source pin:** `VibeInAMajor/enterprise-ai-development-pipeline` commit `955fd049949d3fc462d555be14774e4b255aa15c`; [source catalog](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/tree/955fd049949d3fc462d555be14774e4b255aa15c). This source is **not** already integrated into Workbench and has a separate [PolyForm Strict/Authorized Evaluation license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md). Obtain/document rights for literal code copying, or independently implement compatible algorithms based on the behavior/test contracts. No Qdrant, Root/SQLite generation runtime or Azure SDK is to be copied into our PostgreSQL application.

| Donor implementation and exact file | Reuse owner / decision |
| --- | --- |
| [EmbeddingDispatchController](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_dispatch.py) `reserve/finish/_wait_needed/_pacing_rates` | [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md); preserve arrival reservations, cancellation, 429 cooldown; add independent hard 0.95 ceiling |
| [EmbeddingCapacityPolicy](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_capacity.py) / [EmbeddingCapacityWindows](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_capacity_windows.py) | [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) capacity policy and saturated/unknown completed-window metrics |
| [TEIEmbeddingProvider](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/providers/tei_embeddings.py) and [EmbeddingProvider protocol](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embeddings.py) | [EMBED-001](TASK-RAG-EMBED-001-qualify-local-qwen-embedding-provider.md); adapt to actual local TEI endpoint, query/document instruction, model digest, finite vector and usage provenance |
| [EmbeddingPreparation](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/semantic_embedding_preparation.py) and [bounded execution windows](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_execution.py) | [EMBED-002](TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md) durable PostgreSQL-safe embedding batches and late paid-result recovery |
| [plan_chunk_delta](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/chunk_delta.py) and [DocumentDeltaLookup](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/rag_reference/cache/document_delta_lookup.py) | [DELTA-001](TASK-RAG-DELTA-001-incremental-reindexing-and-embedding-vector-reuse.md); multiset occurrence matching and direct source-version lookup, translated to Postgres/hashes |
| [StructuralChunker](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/chunking.py) and [JSON structural splitting](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/json_structural_chunking.py) | [CHUNK-004](TASK-RAG-CHUNK-004-policy-benchmark-and-tiered-enrichment.md); compare against existing completed [CHUNK-001](completed/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md) before adapting only improved boundaries |
| [Embedding TPM smoothing audit](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tasks/TASK-M39-030-embedding-TPM-smoothing-audit.md) and [test_rag_chunk_delta_runtime.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_rag_chunk_delta_runtime.py) | Borrow quality/fault test scenarios but execute native Workbench Hatch/PostgreSQL tests for a real PASS |

**Exact TPM design:** first qualify **sustainable** local `Q_TPM`, not a fictional cloud quota. Desired admission pacing is `0.92 * Q_TPM`; the independent rolling-60-second **hard estimated/reserved arrival cap** is `0.95 * Q_TPM`; enforce RPM/bursts/max_in_flight separately. The donor default utilization is 0.85 (`EmbeddingCapacityPolicy`) / 0.9 (`TEIProfile`), and donor rolling reservation uses full safe tpm unless specifically changed. Simply changing the target ratio does **NOT** implement our hard 0.95 cap. The donor TEI provider commonly reports tokenizer-counted `usage_tokens`; this is not necessarily native provider-billed usage. Keep `provider_reported`, `tokenizer_counted_proxy` and `actual_usage_unknown` distinct. Quota ownership must be shared across query/ingestion and, before multi-worker mode, across processes. The target is a measurable **saturated backlog** performance setpoint, not an SLA without a benchmark.

**Delta integrity:** unchanged whole-source uploads are already supported; chunk-level vector reuse is separate and requires matching actual embedding input (including heading/context/instruction), tokenizer/model/profile digest, workspace ownership, and proof that the vector exists. Identical text occurrences retain distinct source/version/line/page/asset identity. Do not substitute donor Qdrant physical point identity into Postgres.

## 4. Microsoft Markdown converter: independent research decision

Microsoft [MarkItDown](https://github.com/microsoft/markitdown) is a lightweight Python conversion utility for LLM analysis of PDF, DOCX, PPTX, XLSX, HTML and more; output often preserves headings/lists and ordinary tables. Conversion convenience does **not** imply that Markdown is a better storage format for a RAG database. It is another text/string projection, whereas PostgreSQL already indexes chunk TEXT via tsvector and can hold vectors/metadata.

MarkItDown can be attractive for **simple Office-to-text pipelines** because it requires fewer format-specific extractors and emits uniform Markdown. But for high-fidelity PDF page citations, merged tables, diagrams, layout, numerical charts and original links, our Docling and CONTENT-001 structured-element paths are the stronger design candidates. Original bytes remain canonical; markdown should be a derived representation with converter hash/provenance and warnings.

**Privacy and cost caveat:** MarkItDown core supports offline format-specific conversion; plugins and Azure Document Intelligence/Content Understanding are distinct capabilities. The OCR plugin uses an LLM Vision client and may omit OCR silently when not configured, so a failed/absent vision adapter must not be advertised as an OCR success. MarkItDown README warns conversion uses the current process privileges, so run isolated and avoid optional network helpers by default. Azure layout Markdown may embed HTML tables and figure elements; text-only Markdown cannot be assumed to fully encode their geometry. Assess source retention, cloud egress, request pricing and licensing before any provider-specific deployment.

Comparison gate (CONVERT-001): >=12 representative files across formats, >=40 labeled evidence queries, table/cell/page fidelity, image/diagram loss, structured source maps, retrieval Recall/MRR, converter CPU/RAM/latency, bytes/index cost and safe no-network failures. **No blanket MarkItDown adoption before GO.**

Sources: https://github.com/microsoft/markitdown ; https://github.com/microsoft/markitdown/blob/main/packages/markitdown-ocr/README.md ; https://learn.microsoft.com/azure/ai-services/document-intelligence/prebuilt/layout ; https://docling-project.github.io/docling/concepts/chunking/

## 5. Real embedding, Dense, ANN and Hybrid decisions

The current target is a local Qwen3-Embedding-4B model through a qualified TEI embedding adapter; model card states **up to 2560 dimensions**, but the running endpoint must be probed for digest, dimensions, normalization, prefix/task kind, native tokenizer and max batch. Use a provider-neutral EmbeddingPort for both query and document inputs, and a bounded durable job for each source/version/processing/embedding profile.

Dense baseline should first use **exact cosine** against stored compatible vectors. Only after that reference is correct should HNSW be promoted. Standard pgvector HNSW on vector supports <=2000 dimensions; at 2560 use an approved halfvec(2560) expression index while retaining full-precision vectors for exact rerank or use a separately measured MRL dimension profile. Never silently truncate vectors. ANN RLS/tenant filtering and index post-filter behavior can reduce recall; benchmark with rare-workspace fixtures, hnsw.iterative_scan, ef_search and exact-oracle comparisons. See https://github.com/pgvector/pgvector#filtering and https://github.com/pgvector/pgvector#half-precision-indexing .

Hybrid uses explicitly selected **Reciprocal Rank Fusion** (e.g., RRF score = sum(1/(k+rank_i))) over unique chunk/source-version identities. PostgreSQL ts_rank_cd and cosine distance MUST NOT be linearly added; genuine BM25 is optional behind independent profile and licensing gate. RRF default k, candidate_k/top_k, selected source generation and ranking tie order are versioned.

## 6. BM25 decision: evaluate now, do not switch automatically

Native FTS with tsvector/GIN/ts_rank_cd is already running and its score_type is postgres_ts_rank_cd. Genuine BM25 can be attractive for long/broad keyword corpora, but a tiny eight-document synthetic test is not a business justification for a new extension. ParadeDB pg_search is a relevant PostgreSQL BM25 candidate and currently documents AGPL-3 packaging in PGXN; commercial compliance/deployment and Postgres 17 binary compatibility require explicit review. Benchmarks should measure precision, MRR, lexical exact/identifier quality, multilingual behavior, resource use, tenant filtering and storage overhead.

**Policy:** BM25-001 begins now as a comparative decision experiment; BM25-002 remains BLOCKED until demonstrable gain and legal/runtime approval. If negative, keep FTS; Dense and Hybrid continue independently. Do not use Haystack InMemoryBM25Retriever with PostgreSQL store or mislabel ts_rank_cd as bm25_raw. Source: https://pgxn.org/dist/pg_search/ .

## 7. Enterprise nonfunctional gates

**Performance:** saved source/index generations remove per-query O(number_of_chunks) hashes. For 100k/1M representative chunks measure p50/p95 query latency, SQL planned rows/index scans, index build time, ANN exact-vs-approx recall, worker throughput, model tokens/sec, database/index disk and asset store growth. No arbitrary SLO is claimed from a small seed.

**Security:** verify identity and membership before workspace/source/vector/asset access. RLS is essential but not a complete authorization system. Separate development loopback mode and audited remote mode. Test source/evidence ID guesses, vector ANN post-filter, cached embeddings, job ownership, and remote local-file reveal. Never log raw source text, OCR/VLM outputs, embedding vectors or model tokens.

**Fidelity:** exact originals are immutable; derived Markdown/visual descriptions are versioned and labeled as such. The Evidence Resolver must never turn model-inferred arrows/chart values into verified facts. Chunking/embedding/delta reindex must preserve original page/line/bbox anchors or explicitly fail.

**Reliability:** only committed generations are executable. Worker/API/DB/asset-store failures cannot create fake successful indexing, half-published source versions or silent fallback to Preview. Backup and disaster recovery must restore SQL+original assets together and verify byte hashes and generation identity.

**Observability:** safe trace IDs, job/source/version/profile/index generation, measured per-stage timing, embedding token counts, queue lag, coverage, retrieval/citation quality, ANN recall and capability state; no synthetic node timings or fake completion.

## 8. Completion policy

These Markdown documents are **blueprints**, not implemented code. A task becomes COMPLETE only with real unit, integration, Postgres, runtime/model and appropriate browser evidence captured in its A–O checklist. The implementation order and existing SOURCE/INDEX/PROFILE contracts must be revalidated against the live repository at implementation start; if the source has materially changed, revise task Section C/I/J first, preserving previous architecture decisions and rollback.

Only implement exactly what the approved task calls for; avoid parallel duplicate stores, accidental schema migrations, provider SDK imports into domain core, milestone-coded variable names and arbitrary graph execution.
