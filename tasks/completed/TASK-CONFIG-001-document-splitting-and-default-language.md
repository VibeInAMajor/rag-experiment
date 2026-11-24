# TASK-CONFIG-001 — Externalize Haystack recursive splitting configuration and default to English

**Created:** 2026-11-21\
**Updated:** 2026-11-24  
**Status:** COMPLETE — configured splitting/default language/native admission qualified locally\
**Related task:** [TASK-RAG-CHUNK-001](TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md) (configuration integration; avoid duplicating its strategy-routing implementation).

## A. Title
Externalize `RecursiveDocumentSplitter` settings and use English as the default sentence-segmentation language.

## B. Context / Problem
Recursive chunking must use configurable, explicitly token-measured settings rather than hard-coded values. The approved initial profile is 500 tokens with 50 tokens of overlap, while NLTK-backed sentence splitting uses English by default. Do not confuse tiktoken's `o200k_base` with the native Qwen3-Embedding-4B tokenizer.

## C. Current Repository State

**Pre-implementation source audit recorded 2026-11-22 before CONFIG code edits.** Current checkout HEAD, verified during the follow-up audit, is `719d57f4a06804813306a5bc13ecadd1eb3aa6cc`; `deb9fb63dde97f68db6dd856d1fc2a13a2af2255` is the earlier PARSE/CHUNK/RAG-002/EVAL implementation base, not a new CONFIG commit. Concurrent completed-task archival is preserved. Only this task document was edited for J1; no new configuration wiring is claimed by this audit.

| Existing owner | Inspected current behavior / gap |
| --- | --- |
| `apps/workbench/configuration/config.py` | Strict `ApiSettings`/`from_env()` currently map host/port/revision/origins, DB DSN and local-source root. No external document-processing YAML or splitter environment mapping exists yet. Ingestion timeout is 30 seconds; no language setting exists here. |
| `apps/workbench/chunking/chunking_profiles.py` | Single immutable `ChunkingProfile`/`DocumentFeatures`/resolver: 500/50 token, `o200k_base`, sentence separator order, en default feature language; EN/RU sentence resources, UK structural fallback. `structural_token_profile()` explicitly has no sentence language. Current profile validation admits only reviewed separator profiles, not arbitrary regex strings. |
| `apps/workbench/chunking/chunking_adapters.py` | Existing `_splitter()` constructs the real `RecursiveDocumentSplitter` using profile length/overlap/unit/encoding/separators, but `keep_white_spaces=True` and injected EN/RU `SentenceSplitter` construction are literal. Verified local resources prevent Haystack warm-up network fetches. Reuse this adapter and its exact-source/Unicode safety checks. |
| `haystack/components/preprocessors/recursive_splitter.py` | Repository Haystack 3.5.0 source supports actual constructor `split_length`, `split_overlap`, `split_unit`, `separators`, `sentence_splitter_params`, `tokenizer_encoding`. `sentence` delegates to `SentenceSplitter`; actual `_chunk_text()` source escapes other separators with `re.escape` (lines383–388), despite a stale constructor docstring claiming regex treatment. Pass literal values without double escaping. Do not duplicate its engine or use unsupported Qwen encoding names. |
| `apps/workbench/chunking/chunking.py` | Existing `ChunkingInput`, `prepare_chunks(...)`, immutable prepared metadata/fingerprint and independent `ModelTokenAdmission.embedding_input()`/counter overflow refusal. Default model admission is optional here. This is the reusable integration boundary. |
| `apps/workbench/ingestion/ingestion.py` / `application.py` | RAG-002 currently selects `structural_token_profile()` for unknown upload locale, persists `txt-markdown-structural-v1`/`unqualified_source_locale`, and does not configure native Qwen admission. Switching to configured English sentences is an intentional processing-policy change, not already-wired behavior; same-key terminal replay must stay immutable. |
| `scripts/workbench_chunking_setup.py` | Explicit online provisioning currently downloads two pinned official blobs and writes eight EN/RU Punkt table files plus encoding under ignored `.cache/workbench-chunking`. Runtime verifies package and asset hashes with no download. Setup currently has no offline bundle/import mode; clean offline provisioning requires qualification. |
| `pyproject.toml`, `apps/workbench/api/tests/test_chunking*.py`, `test_model_token_counter.py`, `test_configuration.py`, `test_ingestion*.py` | Detached app pins NLTK 3.10.4, tiktoken 0.14.0, tokenizers 0.23.3; existing suites exercise profile/resource provenance, real local counter, ingestion/jobs/replay. Preserve these owners and regressions. No application container build exists to pretend has been changed. |

**Asset identities:** Punkt ZIP is pinned to NLTK data commit `4f15a3d89eefe9748ec1c05be495d91289197155`, SHA256 `e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106`; `o200k_base.tiktoken` SHA256 is `446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`. Runtime aggregate EN/RU table hashes are `f14317bd8ce7813da0d903f3e90d3d997f102ba6f5ccaa13858558773a53c2ac` / `ad0208e0ce225c2dc8e04a99e301b299a0acba15f3e50aaac54f9c43e8409ba1`.

**Native counter:** `apps/workbench/embedding/model_token_counter.py` implements `LocalQwenTokenCounter(Path)` for `Qwen/Qwen3-Embedding-4B`, revision `5cf2132abc99cad020ac570b19d031efec650f2b`, three exact JSON digests, `tokenizers==0.23.3`, NFC and serialized suffix token 151643; no weights, downloads, inference or TEI parity. Previously user-selected assets are at `A:/AI/TEI/qwen3-4b`; that is an operator path, never a product default. Existing overflow is explicit `MODEL_TOKEN_LIMIT_EXCEEDED` with no truncation/rechunking. Root must decide configured admission enablement/budget and YAML/env precedence before implementation; this audit does not invent either.
## D. Goal
Make the active recursive splitting profile configurable, with working defaults of 500/50 measured in `o200k_base` tokens and `sentence_splitter_params.language: en`; preserve native Qwen tokenizer validation as an independent safeguard.

## E. Scope
- Reuse the existing configuration and chunk-profile routing contracts.
- Parameterize all approved Haystack settings listed in Section H.
- Provide deterministic initialization and dependency provisioning for NLTK and tiktoken.
- Check token counts separately with the native Qwen3-Embedding-4B tokenizer at the existing integration boundary.
- Add tests, logs/trace metadata, and operator documentation.

## F. Non-Goals
- Replacing Haystack, using LangChain as production chunker, or interpreting its 100-character example as a product default.
- Automatic language detection, unverified multilingual sentence segmentation, or automatic switching to word/character splitting.
- Replacing `o200k_base` with an unsupported encoding name for Qwen.
- Duplicating strategy routing, profile registry, or native Qwen safeguards owned by `TASK-RAG-CHUNK-001`.

## G. Architecture / Boundaries
- [x] Application / orchestration
- [x] Retrieval / RAG
- [x] Observability / evidence
- [x] Infrastructure / CI/CD
- [x] Documentation
- [ ] Domain / core — only if an existing neutral configuration contract requires it
- [ ] Provider adapter — native Qwen tokenizer integration remains in its existing implementation boundary

Configuration and profile validation belong to the existing settings/profile layer; Haystack-specific construction belongs at the existing chunking integration boundary. Model-specific token measurement remains separate. Dependencies must point inward; no milestone/task identifiers in code variables, classes, methods or settings keys.

## H. Contracts / Interfaces / Data Model
**Approved logical YAML profile** (adapt nesting to existing repository conventions, do not create competing keys):

```yaml
document_processing:
  default_language: en
  recursive_splitter:
    split_length: 500
    split_overlap: 50
    split_unit: token
    tokenizer_encoding: o200k_base
    separators:
      - "\n\n"
      - sentence
      - "\n"
      - " "
    sentence_splitter_params:
      language: en
      keep_white_spaces: true
```

The effective splitter construction MUST be equivalent to:

```python
from haystack.components.preprocessors import RecursiveDocumentSplitter

splitter = RecursiveDocumentSplitter(
    split_length=500,
    split_overlap=50,
    split_unit="token",
    tokenizer_encoding="o200k_base",
    separators=["\n\n", "sentence", "\n", " "],
    sentence_splitter_params={"language": "en", "keep_white_spaces": True},
)
```

The snippet is **reference behavior**, not an instruction to hard-code the values. `default_language: en` must be mapped to the existing language contract; it MUST NOT silently change unrelated UI or LLM response locale. The sentence splitter language must default to `en`; Russian explicitly uses `ru` only if requested and validated. Other languages require a verified sentence-segmentation strategy and test fixtures before being enabled.

Validation: `split_length` positive integer; `0 <= split_overlap < split_length`; `split_unit` MUST be `token` for this approved profile; known usable `tokenizer_encoding`; separators are an ordered nonempty list of supported strings; valid `sentence_splitter_params`, including language support. Reject unsupported values with explicit errors, never with silent fallback to `word`/`char`.

**Two distinct token counts:** `o200k_base` provides actual token counts for that **OpenAI encoding**, but it does **not** provide exact Qwen3-Embedding-4B token counts. Keep the existing Qwen-native tokenizer verification/limit check independent, observable, and configurable at the appropriate existing boundary; define handling of excessive native counts (e.g., reject or controlled rechunking) in the related strategy contract, without silently changing the approved 500/50 profile.

## I. Repository Files / Components Impacted

| Exact path | Existing responsibility / intended extension |
| --- | --- |
| `apps/workbench/configuration/config.py`, `apps/workbench/configuration/document_processing.py`, `apps/workbench/document_processing.yaml` | Strict document-processing settings, selected YAML/default/env precedence and mapping to the existing chunk profile. |
| `apps/workbench/chunking/chunking_profiles.py` | Extend existing immutable profile fields/validation and resource/language resolution; preserve one registry/router. |
| `apps/workbench/chunking/chunking_adapters.py` | Map every approved configured field into actual pinned Haystack construction, preserving offline resource verification and source-safe validation. |
| `apps/workbench/chunking/chunking.py` | Existing counter admission, processing fingerprint and provenance boundary. |
| `apps/workbench/embedding/model_token_counter.py` | Existing hash-pinned local native counter; configuration must reuse rather than duplicate it. |
| `apps/workbench/ingestion/ingestion.py`, `apps/workbench/api/application.py` | Wire settings into ready/execution and versioned ingestion policy; same-key replay must remain deployment-policy-independent. |
| `scripts/workbench_chunking_setup.py`, `pyproject.toml` | Explicit trusted resource provisioning and app-only pinned dependencies/Hatch commands. Qualify clean offline resource reuse, not ingestion downloads. |
| `apps/workbench/configuration/tests/test_configuration.py`, `test_chunking_profiles.py`, `test_chunking_adapters.py`, `test_chunking.py`, `test_model_token_counter.py`, `test_ingestion.py`, `test_ingestion_routes.py`, `test_ingestion_stability.py`, `test_chunking_setup.py` | Focused precedence/default/language/assets/native-overflow tests and existing full ingestion regressions; add narrow dedicated config/resource tests where justified. |
| `apps/workbench/api/README.md`, `docs-website/docs/architecture/durable-text-ingestion.md`, `content-aware-chunking-strategy.md`, `rag-runtime-contract.md`, `docs-website/PROJECT_MAP.md` | Current operator reference, precedence/effective policy, re-ingestion/rollback and historical-versus-current distinction. |
| `tasks/TASK-CONFIG-001-document-splitting-and-default-language.md`, `releasenotes/notes/` | Audit/evidence/completion record and one scoped user-facing release note. |

Preserve unrelated retrieval, vectors, workspace authorization, UI and existing historical evidence. No live DB operations are part of this audit. The original pre-implementation audit above remains distinct from the subsequently selected implementation paths in this section.
### Selected integration contract after J1 audit

The root selected strict typed defaults < selected YAML (`apps/workbench/document_processing.yaml` by default, or `WORKBENCH_DOCUMENT_PROCESSING_CONFIG`) < `WORKBENCH_DEFAULT_LANGUAGE`, which synchronizes both language fields. Normal API startup uses `ApiSettings.from_env()` and the shipped operator YAML; direct `ApiSettings()` remains constructible with typed native guard disabled/no directory. The shipped YAML enables the independent native guard at 32768 tokens, empty prefix/suffix, no heading path, stable `.cache/workbench-chunking/qwen3-embedding-4b` directory resolved against repository root. This is trusted server policy, with no request/workspace override.

The implementation reuses `text-token-r2`, strict configured `en`/`ru` sentence resources, and ingestion revision `txt-markdown-configured-v2` with `language_policy=configured_sentence_language`. Existing structural/UK internal policy records retain their historical scope; this configured ingestion policy intentionally supersedes it for new processing. Runtime and final acceptance have now passed as recorded in Section L; the pre-implementation audit remains historical. See the [operator reference](../../docs-website/docs/architecture/document-processing-configuration.md).

### Final implemented owners

The pre-code C/I audit above records the initial state. The implementation now resides in `apps/workbench/configuration/document_processing.py`, `apps/workbench/document_processing.yaml`, existing `config.py`/`chunking_profiles.py`/`chunking_adapters.py`/`chunking.py`/`ingestion.py`/`application.py`, and additive `contracts.py`/`ingestion_http.py`/`openapi.json` metadata. Existing model counting remains in `model_token_counter.py`. Tests include `test_document_processing.py`, `test_document_processing_ingestion.py`, `test_chunking_setup.py`, focused chunk/config/ingestion regressions and the actual process-crash test. Operator provisioning extends `scripts/workbench_chunking_setup.py`; `scripts/workbench_processing_smoke.py` collects actual HTTP/SQL rollout/replay evidence. No new splitter/router, inference adapter or production upload UI was introduced.
## J. Implementation Requirements
1. MUST inspect real repository code and tests, then populate Section C and I with evidence before changing code.
2. MUST reuse existing profile and settings contracts; MUST NOT introduce duplicate routing or configuration systems.
3. MUST externalize every setting shown in Section H; no operational parameter may be overwritten by a literal in production code.
4. MUST use actual `RecursiveDocumentSplitter` API parameters available in the pinned Haystack version.
5. MUST preserve approved initial values `500`, `50`, `token`, `o200k_base`, ordered separators, `language: en`, and `keep_white_spaces: true`.
6. MUST explicitly include compatible NLTK, tiktoken and required language-model/tokenizer data in reproducible application build/startup provisioning; fail clearly if unavailable rather than downloading unpredictably during document ingestion.
7. MUST NOT replace token-based limits with words, characters, or LangChain's illustrative 100-character profile.
8. MUST distinguish tiktoken counting from Qwen-native counting; keep the latter as a separate safety/quality check.
9. MUST document configuration precedence and workspace isolation following existing conventions.
10. MUST NOT introduce identifiers tied to task IDs or milestones into public/code naming.

## K. Security / Governance / Observability
No secret values in config or traces. Log/trace the effective profile ID (if present), split length, overlap, units, encoding, sentence language, chunk counts, and native-token overflow events, with correlation to ingestion/workspace without leaking document text. Keep workspace isolation; ensure NLTK resources are provisioned from trusted, pinned dependencies and not fetched during ingestion. Bound resource usage.

## L. Testing / Evaluation / Runtime Verification
- **Unit:** default values, overrides, config precedence, invalid split length, overlap boundary, unsupported unit/encoding/language, separator ordering, and missing NLTK/tiktoken assets.
- **Integration:** run the actual pinned Haystack splitter on stable English fixtures; verify its configured token-measurement behavior, overlap and boundary changes, preservation of provenance, and no silent fallback.
- **Language:** English `en` as default, explicit Russian `ru` with tokenizer resources, and unsupported-language fail-closed behavior; include punctuation/abbreviations/multiline cases.
- **Qwen:** independently count emitted chunks with the native Qwen3-Embedding-4B tokenizer; verify Qwen limits/overflow paths and confirm tiktoken and native counts are not assumed identical.
- **Environment:** clean container/startup with offline preprovisioned NLTK resources; test missing-resource diagnosis.
- **Regression/multi-workspace:** preserve existing ingestion behavior except approved profile changes, ensure no configuration leakage.
- **Baseline:** run configured application checks with Hatch and explicit disposable test DSNs; never use generic nonexistent `src tests` paths:

```powershell
hatch run workbench-api:check
hatch run workbench-api:types
hatch run workbench-api:test
hatch run workbench-api:python -m ruff check scripts/workbench_chunking_setup.py
hatch run workbench-api:python -m mypy --explicit-package-bases --follow-imports=silent scripts/workbench_chunking_setup.py
hatch run workbench-api:python -m pytest -q apps/workbench/chunking/tests/test_chunking_setup.py
```

Focused offline setup qualification currently passed eight cases, including actual native JSON copying using the explicit local test asset environment. The two fresh EN/RU child processes block sockets, NLTK downloads and URL-backed tiktoken lookup, start with no ambient NLTK path, and use only copied approved assets. This proves an isolated startup/runtime path with dependencies already provisioned, not an unimplemented application container build or offline dependency installation. Final combined/live evidence passed: 854 backend tests, zero skips, plus the local HTTP/browser/restart qualification below.

### Executed local acceptance — 2026-11-22

- [Backend JUnit](../evidence/config-2026-11-22/backend-tests.xml) / [log](../evidence/config-2026-11-22/backend-tests.log): **854 passed, zero skips, 78.28 seconds**, including six actual PostgreSQL/native-Qwen HTTP configuration cases, eight offline setup cases and actual isolated process-crash recovery. [Ruff/format](../evidence/config-2026-11-22/backend-quality.txt) and [mypy](../evidence/config-2026-11-22/backend-types.txt) passed for **64 application files**; both collector/setup scripts also passed Ruff/format/mypy.
- The frontend passed **259 tests**, TypeScript checking, formatting and build; existing third-party `use client` build warnings remain nonfatal. No production UI was changed.
- [Before snapshot](../evidence/config-2026-11-22/before.json), [two real uploads](../evidence/config-2026-11-22/after.json), and [restart/replay verification](../evidence/config-2026-11-22/verify.json) record normal startup with shipped English/500/50/native-enabled policy. Ten prior sources/fifteen active chunks became twelve sources/twenty-two active chunks; all prior ten source rows, ten version rows, fifteen chunk rows and two job rows remained unchanged. API restart and same-key replay preserved the new jobs/versions/counts with no further DB change. All seven SQL chunks were independently recounted; an actual 500-o200k chunk counted 578 native Qwen tokens, confirming separate budgets.
- The existing browser returned **Live / Completed** for the uploaded TXT marker with actual source/version identity; [captured browser image](../evidence/config-2026-11-22/live-search.jpg). This is local development proof, not a remote deployment or embedding-inference claim.

The guarded collector uses `hatch run workbench-api:python -m scripts.workbench_processing_smoke before`, then `after` for exactly two synthetic uploads, and `verify` after operator-controlled API restart. `before` and `after` refuse to overwrite existing evidence; `verify` replays the recorded keys without new publication. The collector does not migrate, seed, provision assets or restart services.

Configured profiles can explicitly omit the `sentence` separator; this intentional token policy records `configured_structural_boundaries`, rather than pretending missing sentence assets caused a fallback. Normal shipped sentence mode records `configured_sentence_language`; legacy explicit-profile seams retain `unqualified_source_locale`. Post-commit `ingestion_processing_completed` events record bounded profile/workspace/job/trace/count/native identity without bodies, raw affixes or paths. Effective settings and native admission affect processing identity; configuration source/file SHA remain provenance metadata and are excluded from the fingerprint, so comments or selecting an equivalent file do not force reindexing.

The final [independent artifact/SQL audit](../evidence/config-2026-11-22/evidence-audit.json) passed, with current rows matching verify.json exactly and a [69-file source manifest](../evidence/config-2026-11-22/source-hash-manifest.json). Four configured credentials, seven new chunk bodies and two original synthetic upload bodies had zero matches in the scanned text artifacts. Safe document-processing metadata is exposed through detail/chunk DTOs without directories or raw affixes.

### Evidence limitation discovered and corrected

The first combined run passed 840 tests and exposed two test-harness failures, subsequently corrected before the final 854-test pass. It also revealed that the pre-existing stability test always wrote `tasks/evidence/ingestion-2026-11-22/stability.json`, overwriting that earlier ignored local artifact with a current-policy run. The original raw report could not be recovered. The overwritten current report was copied to [initial-stability.json](../evidence/config-2026-11-22/initial-stability.json); it is **not** the original RAG-002 report. Other historical artifacts were untouched. Earlier documented RAG-002 measurements remain historical statements whose original stability JSON is no longer available for independent replay.

The stability test now defaults to pytest `tmp_path`. Durable output requires an explicit evidence directory; final current-policy output is [stability.json](../evidence/config-2026-11-22/stability.json):

```powershell
$env:WORKBENCH_TEST_EVIDENCE_DIRECTORY = 'tasks/evidence/config-2026-11-22'
hatch run workbench-api:python -m pytest -q apps/workbench/api/tests/test_ingestion_stability.py
```

Unset that variable for ordinary disposable test runs. The default no longer overwrites historic evidence. Full upstream Haystack tests and a Docusaurus build were not run; no application container build exists. Fresh network-blocked process tests qualify already provisioned dependencies/assets, not offline package installation or an invented container image.
## M. Acceptance Criteria
- [x] Actual repository paths, pinned Haystack version, and related task's contracts verified and documented.
- [x] All listed recursive splitter parameters are set by the existing configuration layer.
- [x] Default effective profile is exactly 500 tokens / 50 token overlap measured with `o200k_base`, using the separator order above.
- [x] `sentence_splitter_params.language` defaults to `en`, and explicit supported overrides behave deterministically.
- [x] NLTK, its required language data, and tiktoken are reproducibly provisioned; a clean offline runtime passes smoke tests.
- [x] Invalid/missing settings or resources fail explicitly; no silent word/char fallback occurs.
- [x] Native Qwen token count is validated independently, and overflow behavior is covered by tests.
- [x] No duplicated strategy routing/registry or code names using task IDs are introduced.
- [x] Tests, diagnostics, documentation and rollout evidence are recorded.

## N. Documentation / Migration / Compatibility / Rollback

The [operator configuration reference](../../docs-website/docs/architecture/document-processing-configuration.md) owns actual precedence, schema, asset commands and re-ingestion/rollback behavior. The generated release note is `releasenotes/notes/configurable-document-processing-453e6b4161b9c871.yaml`. Earlier acceptance reports retain their original recorded scope. The overwritten historical stability artifact exception is disclosed in Section L; complete raw historical evidence preservation is not claimed. This successor has its own final runtime record.

Update the current user/operator configuration reference and example profiles. Explicitly state that changing chunking may require re-ingestion/reindexing, with an indexing-profile version or equivalent existing mechanism. Rollback by restoring the previous approved configuration and rebuilding affected indices as required; do not claim that switching a configuration instantly changes already indexed chunks. Cross-link the related `TASK-RAG-CHUNK-001` without duplicating responsibilities.

## O. Mandatory Completion Checklist
- [x] Repository audit and task evidence recorded.
- [x] Configuration mapping and validation implemented with no duplicate subsystem.
- [x] Dependencies and NLTK resources reproducible.
- [x] Native Qwen safeguard independently verified.
- [x] All applicable unit, integration, failure-path, and smoke tests pass.
- [x] Logs/traces avoid secrets and preserve workspace boundaries.
- [x] Documentation, migration/reindex and rollback steps validated.
- [x] Acceptance criteria checked with evidence and task status updated.

## References
- Haystack RecursiveDocumentSplitter: https://docs.haystack.deepset.ai/docs/recursivesplitter
- Haystack PreProcessors API: https://docs.haystack.deepset.ai/reference/preprocessors-api
- Qwen3-Embedding-4B: https://huggingface.co/Qwen/Qwen3-Embedding-4B
- Related task: `TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md`
