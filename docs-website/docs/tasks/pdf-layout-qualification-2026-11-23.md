---
title: PDF text-layer qualification, 2026-11-23
---

# PDF text-layer qualification, 2026-11-23

**Follow-up:** the two-column refusal below records parser r1. Parser `docling-pdf-r2` now passes that case with selective native-cell recovery and successful live numerical-completeness verification. See the [two-column follow-up](pdf-two-column-numeric-integrity-2026-11-23.md). Historical metrics and limitations below retain their original scope.

The updated [CHUNK-003 task](../../../tasks/TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md) separates bounded text/table parsing (Gate A), immutable original assets/evidence (Gate B, CONTENT-001), and OCR/visual semantics (Gate C, CONTENT-002/003/005). This record qualifies the local text-layer subset. Gate B is **not implemented**; Gate C is **not tested or advertised**. The task must not be marked wholly complete on this evidence.

## Implementation and compatibility

Existing PDF worker, Windows Job Object/POSIX quotas, pinned asset manifest, provider-neutral models and HybridChunker adapter were extended. The shared format registry, resolver, `PreparedChunk`, native admission, multipart route, durable jobs and PostgreSQL transaction remain the owners. No additional parser/router/writer, applied migration, upstream Haystack change, blob store or Preview evidence was introduced.

The app Hatch environment declares Docling 2.151.1, docling-core 2.108.0, docling-ibm-models 4.0.4, docling-parse 7.27.0, CPU Torch 2.15.0, transformers 5.24.0, pypdfium2 5.15.2, pypdf 7.1.1 and psutil 7.2.2. Docling's installed package license is MIT. The [Heron model card](https://huggingface.co/docling-project/docling-layout-heron) declares Apache-2.0; the [Docling models card](https://huggingface.co/docling-project/docling-models) declares CDLA-Permissive-2.0 and Apache-2.0. Model licenses are separate from package licenses. Model revisions and five actual file hashes are fixed in `pdf_asset_manifest.json`; no runtime model download occurs.

Use `hatch run workbench-api:pdf-setup --download`, `--from-directory PATH` or `--verify-only`. Missing packages/assets disable PDF capability. The worker rehashes weights/configs before loading them. Its environment omits database credentials; OCR, remote services and external plugins are disabled, and Python socket operations fail closed. This is an owned resource-bounded local child, not a general OS network/container sandbox.

PDF ceilings: 8 MiB input, 32 pages, 180 seconds parser wall time, 640 CPU seconds, 6 GiB process memory, 1,048,576 extracted characters, 32,768 cells, one concurrent parser. HTTP PDF work has 210 seconds; the shared multipart cap is 8 MiB + 64 KiB while each TXT/Markdown/Python file remains limited to 1 MiB. Dense files can time out below 32 pages. Coordinates are top-left unrotated zero-origin MediaBox points; rotation/crop transformations are refused rather than guessed.

The default is `page_layout` / `pdf-page-layout-r1`, 768 ordinary `o200k_base` tokens and zero overlap, with row-aware tables. Comparison profiles are 512/64 and 768/64. `HybridChunker` explicitly uses `MarkdownTableSerializer`; its default triplet serializer would not prove complete physical rows. Original excerpts and retrieval text are separately hashed. No Markdown file is created. Table source spans cover the source block and expose that scope explicitly; row/cell locators identify each child's original evidence. Default false cell-header flags are omitted from compact metadata and recover through `PdfCell` defaults. The independently configured native Qwen guard counts the complete prefixed embedding input; no embeddings or model-driven chunking are claimed.

## Real running-server proof

The input was an explicitly labelled first-page excerpt of the public [California WARN report example](https://github.com/jsvine/pdfplumber/blob/stable/examples/pdfs/ca-warn-report.pdf). It retains actual report facts, not generated probe text. The uploaded file is `california-warn-report-page-1.pdf`. The full public original has 16 pages; this success does **not** qualify all 16 pages.

At `127.0.0.1:8011`, with Workbench `4173`, actual HTTP upload created source `a20591465c984c3bb85f10b047b6d0ca`, initial version `e3440648d4ef460cb758759c7a7e7566`, and six durable chunks. All 36 body rows and seven columns were retained. Independent Qwen token recount matched every chunk and its counter revision. HTTP chunk IDs/content hashes matched SQL. `TaylorMade` returned page 1 and its actual `Carlsbad / 64` row using raw `postgres_ts_rank_cd`.

Idempotency replay kept version/chunk identity. Corrupt PDF and the real two-page excerpt with ambiguous continuation headers failed with HTTP 400 (`PDF_CORRUPT`, `TABLE_STRUCTURE_UNCERTAIN`), preserving the active version. A PDF-title metadata-only update created version `da9c3f19f04b48b590f11b8d4dcfa816`, superseding the initial version without changing the report facts. There is exactly one active version for this source.

Two actual PostgreSQL/API restart cycles preserved source/version/chunk hashes, search, independent counts and the same Docker volume mounts. The initial 13 sources/33 chunks remain; final storage has 14 sources, 15 versions and 45 chunks, of which 39 chunks are active. Old PDF-version chunks are retained. Read-only app-role SQL snapshots checked all unrelated rows, not only totals.

The visible Workbench Live result after the final restart showed the same active version, page and chunk `0dd3f62231fff9056658bb46eef4d9516236c9051adc832f08599a0306e4b65d`, score `0.10000000149011612`. The browser tab was left open. Screenshot, AX state, four live-phase JSON records, failed-attempt intents and mount checks are under the local evidence directory below.

## Controlled extraction and retrieval comparison

Eleven reproducible non-sensitive fixtures cover 1/5/20 pages, two columns, numeric units, long tables, page-separated tables, captions, English, Russian, Ukrainian and mixed text+figure. Separate fixtures cover scans, encryption and malformed bytes. Ten positive inputs extracted; the two-column case was explicitly refused as `PDF_LAYOUT_UNCERTAIN`. It remains in the denominator as two missed evidence queries. Table audit compared every cell against independent generated truth: **69 body rows, all columns exact**, plus the separate manually inspected real report.

There are 25 labelled evidence queries, including captions, within-table multiple-row conjunction and a cross-page conjunction. These are retrieval tests, not answer-generation/numerical-reasoning evaluation. The existing simple-language PostgreSQL FTS and `ts_rank_cd` were executed read-only over a JSON corpus CTE, with a common 4,096-token result budget, top 10 maximum and no embeddings. Query timings cover that SQL comparison, not production GIN latency or end-to-end UI latency.

| Policy | Children | Recall@5 | Recall@10 | Correct source/page evidence coverage | Parse+split p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Page 512/64 | 186 | 0.48 | 0.84 | 0.84 | 20.98 s |
| Page 768/0 | 185 | 0.52 | 0.88 | 0.88 | 20.97 s |
| Page 768/64 | 185 | 0.52 | 0.88 | 0.88 | 20.99 s |
| Whole page control | 34 | 0.56 | 0.88 | 0.88 | 20.93 s |
| Plain recursive 768/0 | 12 | 0.48 | 0.80 | 0.80 | 20.94 s |

Recall means the admitted top-k contains the expected source, page and independently labelled evidence text. Page-evidence coverage uses all queries, counting no-result/parser failures as zero. Whole-page controls may exceed a child target and are comparison controls only. The plain control intentionally lacks page boundaries and assigns only the first source page, exposing its citation limitation. Page context is useful here; the whole-page control has higher Recall@5, so universal superiority of the selected child policy is not claimed. The cross-page conjunction misses under the current lexical AND query; this does not establish analytical QA support.

For 768/0, adjacent multiset token IoU is 0.338 and repeated-token share 0.541; plain recursive gives 0.479/0.906. These measure intersections of token-ID counts in adjacent children within a document; common language/header tokens count, so this is not an estimate of duplicated facts. Extraction resource maxima across accepted fixtures: approximately 1.73 GiB peak process memory and 67.52 CPU seconds. The 20-page fixture parsed in 20.93 seconds. Existing hashed extraction snapshots were explicitly reused for later metric/oracle runs; original parser times were retained rather than invented. Individual SQL query p95 values are recorded in `report.json` (about 2–3 ms on this small corpus).

## Failures found and boundaries

- The Windows venv launcher spawned an extra interpreter and conflicted with the one-process job quota. The worker now launches the reviewed base interpreter with controlled Hatch paths before receiving bytes.
- HybridChunker metadata uses generic `DocItem` objects. Testing subclass identity silently failed to recognize tables; checking the observed table label fixes the adapter.
- The real report's second page incorrectly labels a first data row containing dates as column headers. The conservative header-role guard refuses it; no guessed cross-page header inheritance was added.
- The full dense 16-page report exhausted the 180-second parsing budget. That attempt is a measured refusal, not a claimed success. The earlier experimental fast-table attempt also failed; production uses the reviewed accurate mode.
- Real seven-column tables exposed the 16 KiB per-chunk metadata limit. Omitting typed default-false flags fixed the demonstrated case without deleting cells or widening the limit.
- A detected logo exposed tuple-valued visual metadata during persistence. JSON-mode serialization fixes it, with an actual mixed-figure HTTP/PostgreSQL regression test.
- The current image detector does not prove complete visual coverage. Every accepted document reports incomplete visual processing and unverified detection, including documents with zero detected regions. Pictures do not become graph edges, chart values or asset references. Image-only scans fail `NO_EXTRACTABLE_TEXT`; original asset byte/RLS/restart tests remain **NOT TESTED** until CONTENT-001 exists.

Poppler renders were inspected for the real table, numeric-unit table, mixed diagram and two-column input. System font fallback warnings on the public PDF were visible; the report text/table grid was readable and manually compared. This does not qualify arbitrary font/layout combinations.

## Checks and evidence

Commands ran through Hatch 1.18.2. The full API/validator regression passed **949 tests**, zero skips; after final immutable PDF metadata handling and the additional tightened-cell-budget case, all **26 PDF tests** passed again. Ruff application/script checks and mypy pass. Frontend typecheck, format check, **270 tests**, and production build pass; existing dependency directive warnings remain. Upstream Haystack's full library suite was not run: no library code changed.

Reproduction from the repository root:

```powershell
hatch run workbench-api:check
hatch run workbench-api:types
# Explicit disposable test credentials only; never reset the application database.
hatch run workbench-api:python -m pytest -q -o addopts='' -o log_cli=false apps/workbench/api/tests apps/workbench/validator/tests
hatch run workbench-api:python -m scripts.workbench_pdf_qualification
```

The qualification command requires an explicit local app DSN and performs read-only SQL comparison. Generated files and complete local evidence are in `tasks/evidence/pdf-layout-2026-11-22/`; the folder date records when work began. `scripts/workbench_pdf_probe.py` performs the live phases (`upload`, `after-restart`, `update`, `after-update-restart`) and refuses to overwrite existing phase evidence. Running its upload phase adds one scoped source, so inspect its input/intent before another run.

Remaining work is Gate B integration with the common immutable asset/element/representation contracts after CONTENT-001, followed by separately qualified OCR and visual-semantic successors. No applied SQL, volume reset, unsupported visual capability or fake original-source citation is part of Gate A.
