---
title: Document processing configuration
description: Operator-owned token splitting, sentence language and independent native-token admission.
---

# Document processing configuration

**Created:** 2026-11-22\
**Updated:** 2026-11-22\
**Qualification:** COMPLETE for the local configured ingestion path; full application, offline-resource, native-counter and live/restart checks passed.

The API reads one operator-owned document-processing configuration at startup. It maps to the existing immutable chunk profile and real Haystack 3.5.0 `RecursiveDocumentSplitter`; there is no second splitter engine or request-selected strategy. The [configuration task](../../../tasks/TASK-CONFIG-001-document-splitting-and-default-language.md) records the pre-implementation audit and acceptance gates. [Durable ingestion](durable-text-ingestion.md) owns upload/publication/replay semantics.

## Source and precedence

The [Workbench editor](#edit-configuration-in-workbench) manages this same selected operator file. It does not add a database copy or change the precedence below.

Normal startup calls `ApiSettings.from_env()`. Effective values follow this order:

1. Strict typed defaults fill omitted settings.
2. The selected YAML file overlays them. By default this is checked-in [`apps/workbench/document_processing.yaml`](../../../apps/workbench/document_processing.yaml); `WORKBENCH_DOCUMENT_PROCESSING_CONFIG` selects another bounded local file. Relative paths resolve against the repository root.
3. Optional `WORKBENCH_DEFAULT_LANGUAGE` overrides both `default_language` and nested `sentence_splitter_params.language` together.

The selected file must exist and validate; an absent or invalid file produces `INVALID_DOCUMENT_PROCESSING_CONFIGURATION`, without silently reverting to a different policy. YAML is limited to 64 KiB, bounded depth/node count and the `document_processing` root; duplicate keys, aliases/anchors, merge keys, unknown fields, custom tags and implicit type coercions are refused. Language settings must agree after precedence resolves.

Direct programmatic `ApiSettings()` uses typed defaults without reading operator files. Its native guard defaults disabled with no asset path, keeping isolated components/tests constructible. **Normal startup uses the shipped YAML, which enables the native guard.** Neither construction path downloads assets. Configuration is process-scoped, with no per-workspace/request override or hot reload. Restart the API after changing it. This default language affects document sentence segmentation only, not UI text or generated-answer locale.

The shipped profile is:

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
  native_model_guard:
    enabled: true
    max_tokens: 32768
    local_asset_directory: .cache/workbench-chunking/qwen3-embedding-4b
    prefix: ""
    suffix: ""
    include_heading_path: false
```

`split_length` is an integer 1–8192; overlap is an integer from zero to strictly below length. The unit is always `token` and encoding is the reviewed `o200k_base`. Separators are an ordered nonempty unique allowlist of literal structural boundaries and the special `sentence` sentinel. Arbitrary regular expressions are not accepted; the pinned Haystack implementation escapes each non-sentence separator internally before splitting. Its constructor docstring still describes regex treatment; the adapter passes original literals to avoid double escaping. All effective constructor values, including `keep_white_spaces`, come from this policy. Haystack recursive concatenation preserves original inter-sentence whitespace even when that flag is false; the flag is not a source-text stripping option.

English (`en`) is the configured sentence default. Explicit Russian (`ru`) uses the verified Russian resource. Other configured languages, including Ukrainian for sentence segmentation, are refused until separately qualified. This changes the active ingestion policy from the earlier locale-unqualified structural baseline; that historical internal EN/RU/UK fallback qualification remains recorded. No automatic language detection occurs. An operator may deliberately omit `sentence` from the separator list; this explicit token policy records `language_policy: configured_structural_boundaries`, distinct from a missing-resource fallback. Shipped sentence mode records `configured_sentence_language`. Missing required EN/RU models refuse readiness/processing; there is no silent word/character or structural fallback for the configured sentence profile.

For an explicit Russian deployment:

```powershell
$env:WORKBENCH_DEFAULT_LANGUAGE = 'ru'
. ./apps/workbench/postgres/use-dev-env.ps1
hatch run workbench-api:serve
```

To select an operator-reviewed file instead, set `WORKBENCH_DOCUMENT_PROCESSING_CONFIG` before starting the service. The development workspace remains server-authorized; settings cannot grant a new workspace or alter SQL scope.

## Provision assets explicitly

The app-only Hatch dependencies pin NLTK 3.10.4, tiktoken 0.14.0 and tokenizers 0.23.3. Install/package dependencies during environment preparation; ingestion and startup never fetch missing packages or data. The current application has no container image whose build is claimed here.

Explicit online setup downloads only the reviewed official Punkt ZIP and `o200k_base` encoding, validating fixed hashes. Add an operator-selected existing Qwen tokenizer directory to copy only its three reviewed JSON files:

```powershell
hatch run workbench-api:chunking-setup --qwen-from-directory 'A:/AI/TEI/qwen3-4b'
hatch run workbench-api:chunking-setup --verify-only
```

The example source path is a local operator choice, not a product default. No Qwen model weights, Hub downloads or inference are involved. Normal destination is ignored `.cache/workbench-chunking`, with eight allowlisted EN/RU Punkt files, the encoding and `qwen3-embedding-4b/{tokenizer.json,tokenizer_config.json,config.json}`. Every requested payload verifies before destination writes; extra files and weights are not copied. Missing or altered native assets leave the configured guard unavailable rather than substituting tiktoken.

For offline deployment, transport an already provisioned asset tree and approved native JSON files through the operator's normal packaging process. Import them into a fresh target without network access:

```powershell
hatch run workbench-api:chunking-setup --from-directory 'C:/offline-bundle/chunking' --qwen-from-directory 'C:/offline-bundle/qwen' --destination '.cache/workbench-chunking'
hatch run workbench-api:chunking-setup --verify-only
```

`--destination` is a provisioning target, not a runtime configuration override; core runtime resources remain at the repository cache. `--verify-only` changes no destination files. If its native subdirectory is absent, output explicitly reports `native_counter.state: absent`; this does not qualify a shipped guard-enabled API. When present, its package/assets/configuration are verified too. A clean package environment still needs its pinned dependencies provisioned beforehand; these commands do not promise offline package installation.

Punkt is pinned to NLTK data commit `4f15a3d89eefe9748ec1c05be495d91289197155`, ZIP SHA256 `e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106`; encoding SHA256 is `446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`. Runtime also verifies individual EN/RU aggregate table hashes. Fresh-process tests start without ambient NLTK paths and block socket/download paths while preparing real English and Russian chunks from a copied tree.

## Independent native-token admission

`o200k_base` determines chunk size/overlap; it is not the Qwen-native tokenizer. The existing `LocalQwenTokenCounter` verifies `Qwen/Qwen3-Embedding-4B` revision `5cf2132abc99cad020ac570b19d031efec650f2b` and three JSON digests. It applies serialized NFC and one suffix token 151643, without guessing from config EOS 151645. This qualifies local token counting, not served TEI/inference parity.

The optional `native_model_guard` counts the exact configured embedding-input composition: prefix, optional heading path, content and suffix; the counter owns special markers. The shipped operator policy enables it with budget 32768, empty prefix/suffix and no heading path. This is an operator admission ceiling, not a second chunk-size target or a throughput guarantee. Overflow returns `MODEL_TOKEN_LIMIT_EXCEEDED` and publishes no replacement; chunks are neither truncated nor silently rechunked. Readiness fails if an enabled exact counter cannot qualify.

Document detail now exposes the safe `document_processing` snapshot and `default_language`; chunk metadata exposes both token lengths/counter identity and effective sentence whitespace policy. Public metadata omits local asset directories and raw affix text.

## Identity, migration and rollback

Configured preparation uses profile revision `text-token-r2`. Effective length/overlap/unit/encoding/separators/language/whitespace policy and verified resource/native-counter identities determine the processing fingerprint. Configuration source labels and exact file-byte SHA remain provenance metadata, excluded from that fingerprint; comments or an equivalent selected file do not trigger reindexing. Local directories and affix contents are excluded from exposed manifests; affix hashes retain identity without leaking text. Upload body fields remain unchanged and cannot override processing policy.

Existing stored versions are immutable and keep their original processing metadata. Changing a file/environment setting does not rewrite old chunks. Explicitly re-ingest with a new key and guarded source version to publish a new processing revision; byte-identical content is unchanged only when the current processing fingerprint also matches. Same-key terminal replay continues to return its original result even after configuration changes.

Rollback restores the previous approved configuration and restarts the API. Re-ingest affected sources only when their stored index must use that policy; do not downgrade the database, seed or remove its volume. Keep historical PARSE/CHUNK/RAG-002/EVAL evidence separate from this configuration qualification. The completed qualification below includes eight focused setup cases with actual local native-asset copying and fresh offline EN/RU processes.

## Executed local qualification

The [854-test backend run](../../../tasks/evidence/config-2026-11-22/backend-tests.xml) passed with zero skips in 78.28 seconds, including six actual PostgreSQL/native-Qwen HTTP cases, eight offline setup tests and isolated process-crash recovery. Ruff/format and mypy passed for 64 application files; setup and HTTP collector scripts also passed their checks. The frontend passed 259 tests, type checking, formatting and build, with existing nonfatal third-party `use client` warnings. No production UI was changed. The final [independent artifact/SQL audit](../../../tasks/evidence/config-2026-11-22/evidence-audit.json) passed; its [69-file source manifest](../../../tasks/evidence/config-2026-11-22/source-hash-manifest.json) binds the reviewed implementation. Four configured credential values, seven new chunk bodies and two original synthetic upload bodies had zero matches in the scanned text artifacts.

Normal startup used the shipped English sentence/500/50/native-enabled policy. [Before](../../../tasks/evidence/config-2026-11-22/before.json), [after](../../../tasks/evidence/config-2026-11-22/after.json) and [restart verification](../../../tasks/evidence/config-2026-11-22/verify.json) record two real synthetic uploads producing seven new chunks: ten prior sources/fifteen active chunks became twelve sources/twenty-two chunks, with all prior ten source rows, ten version rows, fifteen chunk rows and two job rows unchanged. API restart and terminal same-key replay preserved identities/counts without further publication. All seven new SQL chunks were independently recounted. One chunk measured 500 `o200k_base` tokens and 578 Qwen-native tokens, demonstrating why the limits are separate. The browser showed Live/Completed for uploaded content with actual source/version identity; [captured image](../../../tasks/evidence/config-2026-11-22/live-search.jpg). This qualifies local development behavior, not remote deployment, semantic inference or a throughput SLA.

The collector is an explicit operator action:

```powershell
hatch run workbench-api:python -m scripts.workbench_processing_smoke before
# Publishes exactly two synthetic documents; refuses an existing after.json:
hatch run workbench-api:python -m scripts.workbench_processing_smoke after
# After the operator has restarted only the API; replays recorded keys:
hatch run workbench-api:python -m scripts.workbench_processing_smoke verify
```

`before` also refuses existing evidence. No collector phase migrates, seeds, provisions assets or restarts services. Post-commit `ingestion_processing_completed` events expose bounded effective profile, workspace/job/trace, chunk count and native-counter identity without raw content, affixes or local paths.

### Test artifact isolation and historical limitation

Ordinary stability tests now write under pytest `tmp_path`. Persist current-policy measurements only when explicitly requested:

```powershell
$env:WORKBENCH_TEST_EVIDENCE_DIRECTORY = 'tasks/evidence/config-2026-11-22'
hatch run workbench-api:python -m pytest -q apps/workbench/api/tests/test_ingestion_stability.py
```

Unset this variable for ordinary runs. [Current stability evidence](../../../tasks/evidence/config-2026-11-22/stability.json) is separate from earlier qualification. During the first combined run, the previous test's hard-coded output path overwrote the ignored historical `ingestion-2026-11-22/stability.json` with a current-policy report before this issue was found. The original raw report could not be recovered. [initial-stability.json](../../../tasks/evidence/config-2026-11-22/initial-stability.json) preserves that overwritten current run, not the original report. Other historical artifacts were untouched; old documented RAG-002 statistics retain their historical scope but no longer have their original stability JSON available for independent replay. Two test-harness failures from the first 840-pass run were corrected before the final 854-pass result.

Full upstream Haystack tests and a Docusaurus build were not run. There is no application container build; fresh network-blocked processes prove offline use of already provisioned dependencies/assets, not offline dependency installation or a container deployment.

## Edit configuration in Workbench

Select the wrench-icon **Configuration** entry directly below **Runs**, or open `/#configuration`. The YAML loads immediately, with no Operator access screen, key, login, session or Lock action. The separate Application-wide badge and shield were removed at the user's request on 2026-11-22. The configuration still applies to the application, as explained by the page description and API scope.

The on-demand CodeMirror editor supports YAML syntax, line numbers, two-space indentation, undo and virtualized scrolling. Tab indents; Escape followed by Tab leaves the editor. Validate and Save use the existing bounded server parser/schema/profile rules. YAML is capped at 64 KiB UTF-8. Unsafe tags, aliases, duplicate/merge keys, excessive nesting and unsupported settings are refused. Safe diagnostics show available coordinates/setting paths without parser snippets.

### Local access boundary

This is the existing local, loopback-only Workbench deployment. It has no account/role authentication for configuration, by explicit user decision. The client uses the same-origin API proxy without cookies or credentials and automatically sends the non-secret `X-Workbench-Request: configuration` intent header. The server requires that header and enforces the existing trusted-host/origin rules; writes also require an approved Origin and JSON. Foreign browser origins cannot pass the custom-header preflight. This is request-intent/CSRF protection, not an operator identity or a production public authorization system. No key provisioning command, operator environment variable or session endpoint is used.

### Saving, activation and recovery

The selected operator YAML remains the only persisted source; no browser-local or database copy becomes authoritative. A missing selected file is an explicitly unsaved starter from canonical defaults with the deployment's native-asset reference retained. Save validates independently, compares the loaded raw-byte revision under a cross-process lock, backs up the prior revision and atomically replaces a flushed same-directory temporary file. Conflicts and failures retain the draft. Reload and in-app navigation require a discard dialog; browser refresh warns about dirty work. Duplicate pending saves are disabled. A timeout is unconfirmed: reload before retrying.

Save reports `active` only when effective settings already match the running snapshot; otherwise `requires_restart`. Restart lets existing settings/ingestion composition consume the saved source. Existing indexed versions and terminal replay retain their original policy; re-ingestion is deliberate. Deployment language overrides remain explicit.

The API accepts no browser-selected configuration path or environment edits. Native tokenizer directories are deployment-managed even while their guard is disabled. Known configured credentials and credential URI/API-key patterns are rejected in raw text and decoded schema strings; keep all secrets outside this nonsecret YAML, including comments/affixes. Arbitrary unknown secrets cannot be classified automatically.

Ten prior nonsecret revisions remain in `.cache/workbench-configuration/<source-identity>/config-<sha256>.yaml`. Restore a reviewed revision by pasting it into the editor, validating and saving against the current revision, then restarting when required. If a source cannot be read safely, stop the API and restore a reviewed backup directly. Manual file edits must coordinate with API writers or stop the API first; cooperative locks do not serialize arbitrary external editors. No database downgrade, seed or automatic reindex is involved. Multi-host/network-filesystem semantics are outside this local contract.

Audit events contain operation, local application actor, revision/outcome, UTC timestamp and trace correlation, without YAML, credentials, raw affixes or paths. See the [completed UI task](../../../tasks/TASK-UI-CONFIG-001-yaml-configuration-editor.md) for automated tests, desktop/mobile browser evidence, conflict handling and real API restart verification. Live verification restored the original configuration and preserved the existing corpus; it qualifies the local deployment.
