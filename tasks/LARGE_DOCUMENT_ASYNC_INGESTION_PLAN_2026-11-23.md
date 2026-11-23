# Large-document asynchronous ingestion — source-audited implementation map

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — specifications, not running code  
**Source reviewed:** 44866bb7e7dc01993bbaefefdec1ab1985951cc7

## Verified source bottlenecks

- boundary.py::_upload_request and upload_transport.py::read_upload hold full multipart bytes in RAM; UploadInput.content repeats bytes.
- ingestion_http.py waits for service.ingest to publish, with 201/200 only; nonterminal jobs have no independent source-byte replay.
- postgres_ingestion.py::recover_ingestions marks abandoned jobs INTERRUPTED; it cannot resume an unavailable original.
- pdf_parser.py pipes whole input into a subprocess and pdf_worker.py loads BytesIO and converts whole file.
- pdf_models.py hard-limits 8 MiB/32 pages and 4096 blocks; one Docling conversion and 8 MiB result are independent limitations.
- postgres_ingestion.py limits active workspace corpus to 10,000 chunks and 50 MiB; a bigger document may fail at publication.
- pdf_worker.py explicitly uses Docling CPU with 4 threads, OCR off: the RTX 4090 does not automatically accelerate PDF parsing.
- web/src/api/client.ts and contracts.ts expect completed-only response, 240s upload timeout and hardcoded PDF caps.

## Target data flow

Browser actual transferred bytes
  -> bounded ASGI multipart stream
  -> tenant-owned immutable AssetStorePort staged PDF + SHA256 + disk quotas
  -> one PostgreSQL job plus queue/outbox transaction
  -> HTTP 202 and job status URL
  -> separate leased supervised workers + fairness/backpressure
  -> seekable PDF safety preflight
  -> Docling page_range window with scoped checkpoints and per-window budgets
  -> existing PDF layout/table-aware chunker
  -> hidden bounded chunk batches + generation manifest
  -> one guarded atomic source/index generation activation
  -> durable completed job and Live Documents refresh

## Atomic tasks, in dependency order

1. [TASK-RAG-INGEST-001 — Stream multipart input to immutable durable source staging](TASK-RAG-INGEST-001-streamed-asset-staging.md).
2. [TASK-RAG-INGEST-002 — Accept staged originals and durable jobs atomically before HTTP 202](TASK-RAG-INGEST-002-atomic-http-202-job-admission.md).
3. [TASK-RAG-INGEST-003 — Supervised leased workers with retry, fencing and per-tenant fairness](TASK-RAG-INGEST-003-leased-workers-and-tenant-backpressure.md).
4. [TASK-RAG-PDF-001 — Restartable seekable PDF page windows for 200 MiB and 1000 pages](TASK-RAG-PDF-001-bounded-page-window-processing.md).
5. [TASK-RAG-INGEST-004 — Batch staged chunks and atomically publish verified large-document index generation](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md).
6. [TASK-UI-004 — Live Documents 202, upload progress and durable processing status](TASK-UI-004-async-upload-and-job-tracking.md).
7. [TASK-RAG-OPS-003 — Release-gate 200 MiB and 1000-page ingestion on target server](TASK-RAG-OPS-003-large-pdf-1000-page-qualification.md).

Parent: [TASK-RAG-SCALE-002](TASK-RAG-SCALE-002-durable-asynchronous-ingestion-and-tenant-backpressure.md). Reuse CONTENT-001 AssetStorePort, INDEX-001 consistent generation, CHUNK-003 qualified PDF table/numeric processing, and existing UI-003 Live document behavior. Never introduce a duplicate source publisher.

## Deployment limits and measurable gates

Current 1 MiB text, 8 MiB PDF and 32-page limits are policy, not Qwen/PG/4090 limits. Keep them enabled until real qualification. Candidate tiers are 100 MiB/256 pages then 200 MiB/1000 pages. Separate original bytes/pages, per-window memory/CPU/seconds/characters/blocks/cells, scratch disk, per-workspace quotas and search-index capacity. A large compressed PDF may amplify memory far beyond its original file size.

HTTP asynchronous acceptance improves responsiveness and recovery; it does not automatically speed up CPU-intensive Docling. Test supported Docling GPU configurations and Ollama/VRAM contention instead of promising speed gains. Docling documentation lists Path input and 1-based page_range at https://docling-project.github.io/docling/reference/document_converter/ ; Starlette documents request streaming at https://starlette.dev/requests/ . Verify APIs on the pinned dependencies before implementation.

**Implementation state:** this commit only adds task specifications. There is no verified 200 MiB or 1000-page ingestion, no migration execution and no load benchmark.