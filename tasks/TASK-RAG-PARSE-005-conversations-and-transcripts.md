# TASK-RAG-PARSE-005 — Conversation, email, subtitles and transcript-aware boundaries

**Created:** 2026-11-21  
**Updated:** 2026-11-24  
**Status:** PROPOSED — blueprint, not implemented  
**Priority:** P2 — customer communications and time-aware knowledge  
**Dependencies:** TASK-RAG-PARSE-001, TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-DB-001  
**Repository snapshot reviewed:** `522c2cb38aff746e65a8f04ea48d88d3695fc5a9`  
**Target:** `tasks/TASK-RAG-PARSE-005-conversations-and-transcripts.md  
**Architecture:** [Content-aware chunking strategy](../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Introduce a **turn/speaker/timestamp/topic-boundary** document-element and chunking profile for EML/MSG email and SRT/WebVTT captions. Treat exported Slack/Teams threads, audio and video as separate source/ASR qualification gates, not automatically supported uploads.

## B. Context / Problem

Conversational sources cannot be chunked like a policy PDF without losing who said what and when. The supplied decision tree explicitly includes turn-based and topic-based splitting. Our original three chunking tasks covered prose, Python code and PDF but omitted conversation and timestamps. A distinct parser-and-policy task is needed to avoid attributing another speaker's statement or a transcript interval to the wrong person.

## C. Current Repository State

**Source audit refreshed 2026-11-23:** [RAG-002](completed/TASK-RAG-002-ingest-text-and-markdown.md) and [PARSE-001](completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md) are implemented, but [parser_registry.py](../apps/workbench/parsing/parser_registry.py) only catalogues the timed-transcript family and does not approve public EML/MSG/SRT/VTT ingestion. [ingestion_http.py](../apps/workbench/api/ingestion_http.py) already owns upload/job/details/chunks routes; this task must add bounded per-format parsers and metadata only. Do not confuse upstream `MSGToDocument` with a qualified Workbench pipeline.

| Actual source | Existing behavior | Gap |
| --- | --- | --- |
| [`haystack/components/converters/msg.py`](../../haystack/components/converters/msg.py) `MSGToDocument` | Outlook `.msg` primitive exists, optional dependency. | Not proven to preserve thread/attachments or user ACL without additional structure checks. |
| [`haystack/components/converters/multi_file_converter.py`](../../haystack/components/converters/multi_file_converter.py) | Does not include EML, MSG or subtitles in its class MIME set. | No universal conversation conversion path. |
| [`haystack/components/preprocessors/embedding_based_document_splitter.py`](../../haystack/components/preprocessors/embedding_based_document_splitter.py) | Embedding-based topic-shift splitting exists but requires a qualified embedder. | Initial speaker/turn segmentation must work without any model. |
| [`apps/workbench/persistence/models.py`](../apps/workbench/persistence/models.py) | `Chunk.metadata` can hold bounded speaker/time/thread provenance. | No time-aware UI/citation contract currently; ensure no invented speakers. |
| [`apps/workbench/retrieval/lexical.py`](../apps/workbench/retrieval/lexical.py) | PostgreSQL FTS over persisted chunks. | No diarization or entity extraction from lexical search. |

Upstream Docling lists email/WebVTT and audio/video processing; these are **upstream features** requiring pinned extras/runtime, not app capabilities. No media transcription or connector was verified in the repository.

## D. Goal

Valid `.eml`, `.msg`, `.srt` and `.vtt` inputs can be parsed into ordered messages/utterances, grouped into bounded chunks without breaking speaker/time references, committed with immutable provenance and retrieved with correct author and/or time citations. Missing speaker/time fields remain explicitly absent instead of fabricated. Media files remain unsupported until separately qualified.

## E. Scope

- `.eml`: bounded MIME parser, headers/body, quoted thread boundaries, attachment manifest only; no automatic attachment ingest.
- `.msg`: reviewed existing Haystack converter plus source-specific header/body and attachment metadata where extractable.
- `.srt`, `.vtt`: parse timed cues and speaker labels **only when present**, validate monotonic/correct time range; overlap or multi-speaker cues get explicit provenance.
- `conversation_turn`, `email_message`, `transcript_cue`, `topic_span` element kinds; chunk by turn/topic with bounded adjacent-utterance grouping, no inadvertent cross-speaker attribution.
- Preserve thread/message IDs, timestamps/timezone if known, role/author, cue time range, reply reference and source offsets as metadata.
- Use existing ingestion jobs, atomic PostgreSQL writer and lexical retrieval; cap attachment lists and reject malformed MIME/time cues.
- Advanced semantic topic detection remains **optional** until a qualified embedding adapter and quality benchmark exist.

## F. Non-Goals

No live Gmail/Slack/Teams API connector, email sending, external attachment fetches, ASR/diarization, OCR, MP3/WAV/MP4 ingestion, hallucinated speaker attribution, sentiment inference, PII classification claims, production messaging ACL beyond existing development scope or LLM transcript summaries.

## G. Architecture / Boundaries

### PARSE/CONTENT ownership contract — non-duplication gate

- **Ownership:** PARSE-005 alone extracts **mail message/turn/cue boundaries and timestamps**, preserving author/speaker evidence when present. It does not send email, call message APIs, transcribe audio, infer speakers or create a new chat/thread database. It uses the shared app [parsing.py](../apps/workbench/parsing/parsing.py), [chunking.py](../apps/workbench/chunking/chunking.py) and existing ingestion job/write path.
- **CONTENT-001:** [CONTENT-001](../TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) owns persisted element/representation/original attachment **asset metadata**. PARSE-005 may emit an attachment manifest (safe filename/MIME/count/hash if available) but must not implement upload/store of attachment bytes, `DocumentAsset` or a second source-table lifecycle.
- **CONTENT-002/003:** [CONTENT-002](../TASK-RAG-CONTENT-002-scanned-pdf-ocr-and-layout.md) is scanned-PDF OCR; [CONTENT-003](../TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md) is visual graph interpretation. Neither supplies ASR, diarization or video subtitle extraction. Media/ASR support is a **separate future task**; never accidentally claim it from a current transcript parser.
- **Evidence:** [CONTENT-005](../TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) provides securely resolved original email/time/line evidence after it exists. PARSE-005 only records truthful message IDs/time zones/cue offsets. Sender and speaker IDs are source data, not user identity/authorization.

**Qualification modes:** Gate P = format-specific parser/structured chunk + existing PostgreSQL lexical publication (this task); Gate E = durable byte/evidence/representation resolution (CONTENT-001/005 or specialty CONTENT adapter). Gate P may pass while Gate E is NOT_IMPLEMENTED, but Gate P must not claim original evidence or multimodal completeness. No new global parser registry, ContentRepresentation storage or EvidenceResolver is permitted in this task.

`PARSE-001 verified EML/MSG/SRT/VTT → safe message/cue parser → chronological typed elements → turn-aware policy (optional bounded topic merge) → shared ingestion/source-version job → PostgreSQL + pgvector → lexical results with truthful source/message/time metadata`. Authentication and retention must be decided by the server; message sender identities are **document data**, never user authorization.

## H. Contracts / Interfaces / Data Model

`ParsedElement` must support `message_id?`, `thread_id?`, `speaker_id?`, `source_author?`, `sent_at?`, `time_start_ms?`, `time_end_ms?`, `reply_to?`, `cue_number?`, `source_span?`, `language?`, and confidence of parser-supplied metadata only. A chunk may group adjacent turns but stores a list of constituent element IDs and source time intervals; it may not claim one speaker if multiple speakers contributed. Keep timestamps in a canonical UTC representation **only when a timezone exists**; preserve original offset/unknown timezone accurately. Define explicit `MISSING_SPEAKER`, `INVALID_TIMESTAMP`, `BROKEN_MIME`, `UNSUPPORTED_ATTACHMENT` warning/error codes.

## I. Repository Files / Components Impacted

- CREATE `apps/workbench/parsing/conversation.py` and `apps/workbench/parsing/tests/test_conversation_parsers.py` (or shared source-file equivalents).
- EXTEND `apps/workbench/parsing/parser_registry.py`, `apps/workbench/chunking/chunking.py` and task-created `ingestion.py` without second HTTP/DB path.
- EXTEND `apps/workbench/contracts/schemas.py`/`apps/workbench/api/openapi.json` and document detail projection **only if** new fields are actually supported.
- UPDATE `docs-website/docs/architecture/content-aware-chunking-strategy.md` and API README with provenance/PII/retention limitations.
- Do NOT change Haystack core, database migration `0001`, the PostgreSQL scoring contract or frontend Preview history.

## J. Implementation Requirements

### J0. Reconcile completed app owners and format-specific handoffs

1. Confirm current [parser registry](../apps/workbench/parsing/parser_registry.py), [parsing.py](../apps/workbench/parsing/parsing.py), [ingestion_http.py](../apps/workbench/api/ingestion_http.py), [chunking.py](../apps/workbench/chunking/chunking.py), [PostgreSQL publication](../apps/workbench/postgres/postgres_ingestion.py) and [actual contracts](../apps/workbench/contracts/schemas.py). The old blueprint predates completed RAG-002 and PARSE-001; do not reimplement their components.
2. Build a format/element/asset/evidence matrix and mark all unsupported extractions `NOT_QUALIFIED`; record original evidence status separately from parsed text.
3. Align this task's format-specific `ParsedElement` projection with CONTENT-001's long-lived `DocumentElement` contract **without building it here**. Confirm all source/span/line/page/time units are explicitly defined before using them as citations.

### J6. Format boundary regression and CONTENT handoff

Test MIME nested email, quoted replies, attachments as metadata-only, SRT/VTT overlapping cues and unknown speaker; prove exact speaker/time source attribution. Original email files/attachments are stored only if CONTENT-001 is implemented and authorized; otherwise declare original unavailable. ASR/diarization must remain explicitly unsupported.

### J1. Inspect and constrain message/media surface

Review `MSGToDocument` output and license/deps; build exact fixtures for EML multipart text/plain/html, nested MIME, quoted replies, attachment links, alternate body encodings. For SRT/VTT handle timestamps, cue order, speaker markers and missing speaker values. Define hard input bytes, messages/cues, attachment count, parse deadline and redaction policy.

### J2. Extract first-class turns/cues

Preserve authors/timestamps/thread boundaries with safe decoded body text; leave absent fields unset. Never cross confidential thread boundaries. Ensure HTML email is sanitized; ignore active remote resources. Sentences alone are not adequate turn boundaries.

### J3. Bounded conversational grouping

Group contiguous cues/turns within one thread by speaker/time window where validated. Topic-based merge is deterministic lexical/segment-based in this task; full embedding-based topic shifts are a separately gated profile. Keep original cue ranges for citations and avoid attributing a multi-speaker chunk to one person.

### J4. Shared ingestion and search

Use RAG-002 job/idempotency and version publication; no custom chat DB or unqualified ASR calls. Test exact phrase and speaker/clock context retrieval using actual PostgreSQL. Preserve old active version on invalid MIME/transcript or update failure.

### J5. Evidence and staged activation

Enable each file type separately after 10 curated sources and 10 gold queries per family, reporting speaker/timestamp citation accuracy, source coverage, PII/redaction outcomes, parse cost and FTS ranking. Only then advertise it in capability discovery. Explicitly defer `mbox`, Slack exports, audio/video ASR and diagrams to separately reviewed tasks.

## K. Security / Governance / Observability

Email bodies, transcript text and attachments frequently contain PII/secrets. Do not log or trace content, email addresses, recipient lists, attachment bodies or remote links by default. Never fetch attachments or run active MIME/HTML content. Respect workspace source ACL and retention. Define retention/deletion consent and secure temporary-file disposal before accepting real customer communications. Sender identity or transcript user IDs do not grant application access. Document all intentional redaction/exclusion transforms in a versioned profile.

## L. Testing / Evaluation / Runtime Verification

Valid/invalid MIME nesting, multipart, encoded header, HTML/script, quoted chain, missing sender/time, SRT overlaps, WebVTT cue parsing, absent speaker, timezone, huge transcript, multiple speakers, zero content, duplicate cue IDs, prompt-injection content, non-UTF8, unauthorized workspace, retry/restart/DB rollback; a negative fixture must never leak email PII to logs. Test real API and PostgreSQL and rerun TXT/MD lexical tests. Run app Hatch quality commands and record gate evidence.

## M. Acceptance Criteria

- [ ] Enabled EML/MSG/SRT/VTT each passes actual parse+upload+PostgreSQL+search E2E with correct time/author citations.
- [ ] 100% of golden speaker/cue/time/source attributions match actual input; unknown speaker remains unknown.
- [ ] No cross-thread/speaker false attribution, implicit attachment processing, remote fetch or unapproved ASR.
- [ ] At least 10 representative files and 10 labeled questions per enabled family; PII/no-leak and structural quality measured.
- [ ] Capabilities exclude Slack/Teams connectors and media until their own approval; failure paths do not alter active version.

- [ ] Reuses **completed** PARSE-001/RAG-002/chunking and current API; no duplicate format registry, HTTP upload handler, persistence adapter or version publication.
- [ ] Does **not** implement CONTENT-001 original asset storage/`DocumentElement` persistence or CONTENT-005 evidence resolution; the parser exports accurate source/element spans for later adapters.
- [ ] `EML/MSG/SRT/VTT` format-specific supported/unsupported visual/attachment/graph cases are labelled truthfully; no inferred OCR/VLM/Mermaid/ASR behavior advertised from parsing.

## N. Documentation / Migration / Compatibility / Rollback

Timestamp/turn/thread metadata can initially fit bounded JSONB; indexed conversation joins and deletion policies may require a separately reviewed migration. Existing lexical score and job responses must remain compatible. A media/audio connector is **not** permitted as an implicit parser swap. Rollback disables specific format profiles without deleting existing version records and active source snapshots.

## O. Mandatory Completion Checklist

- [ ] All new source paths and GitHub-relative links verified from the actual `tasks/` location.
- [ ] PARSE/CONTENT ownership boundaries exercised with fixture tests; no duplicate durable element/asset model.
- [ ] Existing SQL/API/upload/source-version test gates remain passing when new parser family is enabled.


- [ ] MIME/MSG/SRT/VTT parser adapters reused or qualified with explicit resource limits.
- [ ] Speaker/time/thread metadata and no-invented-provenance rules verified.
- [ ] PII, attachment, prompt-injection and remote resource cases tested.
- [ ] PostgreSQL/search and restart evidence attached; other formats unaffected.
- [ ] Documentation/capabilities represent only completed formats.
- [ ] All A–O acceptance items met before COMPLETE.
