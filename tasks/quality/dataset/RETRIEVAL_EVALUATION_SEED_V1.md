# Source-pinned retrieval evaluation seed v1

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** DRAFT — source-grounded candidate queries; human review, original-byte SHA256, actual ingest, independent adjudication and sealed holdout pending. **Not qualified gold.**  
**Source snapshot:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Owner:** [DATASET-001](../TASK-RAG-DATASET-001-independent-evidence-gold-set.md)

This is an actual starter dataset distinct from the original 52-case synthetic fixture: eight real architecture/runbook Markdown files from the repository, 36 answerable candidate queries (18 tuning, 18 review-split), 12 candidate no-answer queries (six each), EN/RU/UK. The review split is visible in this file and therefore NOT a blind holdout. These sources/labels are project-derived and assistant-authored; human independence is not claimed. The final independently reviewed dataset, external/authorized real documents, code/PDF/table cohorts, multi-facet annotation, SHA256 and reviewer-controlled sealed holdout remain DATASET-001 deliverables. No performance results are claimed.

## Corpus manifest (originals, not generated documents)

Load the **entire exact original bytes** of each listed Markdown file from its pinned commit, verify Git blob identity and record original SHA256, license and byte count before ingestion. Do not concatenate the split corpora: each has separate eligible sources. Use the existing supported Markdown ingestion, not pre-chunked fixture injection for E2E. Do not ingest this manifest, labels, expected facts, task documents or reviewer notes. Source/version labels below are evaluation aliases, not fabricated persisted IDs; map actual API-assigned IDs and original line spans. Git blob SHA is not original-byte SHA256. Preserve original text and line numbers; links in corpus are plain content, not instructions to fetch other files.

| Source alias | Pinned original | Git blob SHA | Split | Family |
| --- | --- | --- | --- | --- |
| DENSE | [live-dense-search.md](https://github.com/VibeInAMajor/rag-experiment/blob/d6cba6580e308fbb37266b779dce5b6880309a44/docs-website/docs/architecture/live-dense-search.md) | `8ae48e1c0a85a96c7b8218b0442f324df060d44f` | tuning | dense runtime |
| PROFILE | [profile-registry.md](https://github.com/VibeInAMajor/rag-experiment/blob/d6cba6580e308fbb37266b779dce5b6880309a44/docs-website/docs/architecture/profile-registry.md) | `46d1611e908420b7eab1f84d71f9050673bceb4b` | tuning | profile governance |
| EMBED | [durable-embedding-ingestion.md](https://github.com/VibeInAMajor/rag-experiment/blob/d6cba6580e308fbb37266b779dce5b6880309a44/docs-website/docs/architecture/durable-embedding-ingestion.md) | `04eb7e1ac09af1895a193faaa344d0126f747535` | tuning | embedding lifecycle |
| LEX | [postgres-lexical-search.md](https://github.com/VibeInAMajor/rag-experiment/blob/d6cba6580e308fbb37266b779dce5b6880309a44/docs-website/docs/architecture/postgres-lexical-search.md) | `c2a5bf94f24b6415a3d790652b0e14e3c161fde3` | tuning | lexical API |
| INDEX | [persisted-index-generations.md](https://github.com/VibeInAMajor/rag-experiment/blob/d6cba6580e308fbb37266b779dce5b6880309a44/docs-website/docs/architecture/persisted-index-generations.md) | `a2b0ca7b18c276f878afd133271a45058f1d5342` | review-split | generation operations |
| REVEAL | [local-source-reveal.md](https://github.com/VibeInAMajor/rag-experiment/blob/d6cba6580e308fbb37266b779dce5b6880309a44/docs-website/docs/architecture/local-source-reveal.md) | `b86d6f015d208f26b004b14d91e2169e18ff26ba` | review-split | native reveal |
| CONFIG | [document-processing-configuration.md](https://github.com/VibeInAMajor/rag-experiment/blob/d6cba6580e308fbb37266b779dce5b6880309a44/docs-website/docs/architecture/document-processing-configuration.md) | `18e2a51966a4b05412489a71104f9ee21e9c1f2c` | review-split | configuration |
| UPLOAD | [durable-text-ingestion.md](https://github.com/VibeInAMajor/rag-experiment/blob/d6cba6580e308fbb37266b779dce5b6880309a44/docs-website/docs/architecture/durable-text-ingestion.md) | `a82a014654893fa60eea243e2cf2b35f6c64a8f4` | review-split | upload lifecycle |

## Candidate answerable cases

All rows have review_status=UNREVIEWED. Evidence anchors are candidate required facts with source alias and 1-based source line(s); semicolon separates multiple documents and comma separates distinct ranges. Reviewers must verify anchor completeness, label alternatives/support/hard negatives and assign facet IDs/grades (3 primary, 1 support, 0 explicit nonrelevant; unjudged unknown). Expected facts are semantic labels, not exact-string answers. Multi-document cases require all mandatory facets, even if multiple passages are necessary; no automatic equivalence based solely on text similarity.

| Query ID | Language | Intent | Query | Candidate evidence anchors | Expected facts |
| --- | --- | --- | --- | --- | --- |
| T01 | EN | identifier | Which exact Dense profile revision and score direction are exposed? | DENSE:16,31 | postgres-dense-exact-r1; raw cosine distance smaller first |
| T02 | RU | failure | Почему при истёкшей калибровке нельзя вернуть успешный пустой Dense результат? | DENSE:16,33 | current capacity required; unavailable 503; no fixture fallback |
| T03 | UK | security | Чи можна передати вектор або URL моделі в запиті пошуку? | DENSE:29 | no; server resolves workspace and policy |
| T04 | EN | multi-facet | How are inference time and adapter wall time different? | DENSE:31 | adapter includes preparation, admission, HTTP, attestation; not kernel time |
| T05 | RU | version | Что происходит при изменении лимита уже опубликованного профиля? | PROFILE:14,18 | new immutable revision; rollout separate |
| T06 | UK | exact | Які два ліміти має реєстр профілів щодо YAML та кількості визначень? | PROFILE:16 | 64 KiB; 32 revision definitions |
| T07 | EN | negation | Does an active label or browser graph alone make a profile executable? | PROFILE:24,26 | no; actual readiness and qualified workspace |
| T08 | RU | failure | Как клиент реагирует на 409 после изменения профиля? | PROFILE:47 | refresh discovery; cancel invalidated work; explicit selection |
| T09 | UK | multi-facet | Які ключі визначають повторне використання вектора та чи можливе воно між workspace? | EMBED:20 | workspace, fingerprint, processing digest, formatted input SHA256; no cross-workspace reuse |
| T10 | EN | causal | Why can an old worker not attach a late paid result to a new version? | EMBED:18 | lease owner, active source/version and content rechecked |
| T11 | RU | numerical | Каковы целевой коэффициент и независимый жёсткий предел admission? | EMBED:30 | 0.92 Q_TPM; 0.95 Q_TPM rolling 60 seconds |
| T12 | UK | failure | Що стається з capacity charge після скасованого вже надісланого запиту? | EMBED:26 | retained; not treated as unsent |
| T13 | EN | exact | What lexical score type is returned and what is a legitimate zero-hit response? | LEX:55 | postgres_ts_rank_cd; HTTP 200 results empty |
| T14 | RU | configuration | Какой порт и адрес использует локальный lexical API? | LEX:24 | 127.0.0.1:8011 |
| T15 | UK | numeric | Які допустимі межі довжини query та top_k у lexical API? | LEX:53 | 1–4096 Unicode code points; integer 1–50 |
| T16 | EN | multi-document | Why does a successful embedding backfill not itself expose Live Dense? | EMBED:10,24; DENSE:16; PROFILE:24 | coverage; active rollout; model and current capacity qualification |
| T17 | RU | multi-document | Как отличаются score semantics точного dense и FTS? | DENSE:31; LEX:55; PROFILE:24 | cosine lower; ts_rank_cd higher; no mixing |
| T18 | EN | hard-negative | What happens to lexical search when embedding model fails? | EMBED:8; LEX:11 | lexical remains available; no embedding dependency |
| R01 | EN | transaction | What must commit atomically when a source changes? | INDEX:16 | version activation, manifest advancement, terminal job; failed transaction publishes neither |
| R02 | RU | identifier | Какой уровень изоляции использован для чтения manifest и hits? | INDEX:18 | read-only REPEATABLE READ |
| R03 | UK | failure | Чи запускається reconciliation під час кожного HTTP-запиту? | INDEX:48 | no; offline admin, 120s statement/5s lock ceiling |
| R04 | EN | version | What does repair change and what data must stay unchanged? | INDEX:55 | one reconciliation generation; no source/version/chunk/vector changes |
| R05 | RU | security | Почему удалённый API не может открыть Explorer на компьютере браузера? | REVEAL:9 | same-machine Windows capability; selects file on API host |
| R06 | UK | identifier | Які умови потрібні для reveal POST та чи можна надіслати шлях з браузера? | REVEAL:44 | allowed Origin, loopback Host, JSON; no browser path/query/extra fields |
| R07 | EN | hard-negative | Does successful Explorer dispatch prove the user read the file? | REVEAL:44 | no; dispatch accepted only |
| R08 | RU | numeric | Каковы предел размера локального оригинала и deadline проверки SHA? | REVEAL:56 | 512 MiB regular local file; five seconds |
| R09 | UK | configuration | Який порядок пріоритетів налаштувань document processing? | CONFIG:18-24 | typed defaults, selected YAML, optional WORKBENCH_DEFAULT_LANGUAGE override both fields |
| R10 | EN | negation | What happens if the selected YAML is invalid or missing? | CONFIG:24 | INVALID_DOCUMENT_PROCESSING_CONFIGURATION; no silent fallback |
| R11 | RU | causal | Что произойдёт при отсутствии native tokenizer assets? | CONFIG:80 | guard unavailable; no tiktoken substitution |
| R12 | UK | version | Чи підтримується hot reload або зміна конфігурації для окремого запиту? | CONFIG:26 | no; process scoped; restart |
| R13 | EN | multi-facet | What limits apply to supported text/Python and qualified PDFs? | UPLOAD:37 | 1 MiB; PDF 8 MiB/32 pages; no OCR guarantee |
| R14 | RU | recovery | Как повторить upload после timeout, когда неизвестно, был ли commit? | UPLOAD:39,72 | same file/key; publication may have committed; replay returns original job snapshot |
| R15 | UK | failure | Що робить клієнт при 409 під час заміни версії файлу? | UPLOAD:41 | preserve selection/file/key, reload details, explicit new selection; no silent retry |
| R16 | EN | exact | Which hash includes an original UTF-8 BOM? | UPLOAD:80 | SourceVersion.content_hash SHA256 original bytes including BOM |
| R17 | RU | multi-document | Почему после замены документа нельзя продолжать использовать старый cursor? | INDEX:16,18; UPLOAD:82 | generation/revision changes; cursor bound to active corpus; 400 INVALID_CURSOR |
| R18 | UK | multi-document | Чи гарантує indexed text доступ до оригінального PDF і що насправді робить локальне reveal? | UPLOAD:43; REVEAL:7,9 | indexed chunks not original bytes; selects registered file on same API host; not remote asset |

## Candidate no-answer cases

These are candidate absent-evidence queries, not independently verified absences. Reviewer checks the full eligible corpus (including examples and all original text) before assigning answerable=false; an unavailable service is not no-answer. Never retrieve or invent a real secret; expected safe outcome after verified absence is insufficient evidence.

| Query ID | Split | Language | Query |
| --- | --- | --- | --- |
| TN01 | tuning | EN | What was the TLS certificate expiry date for the production payment gateway? |
| TN02 | tuning | RU | Каков пароль администратора PostgreSQL в рабочей среде? |
| TN03 | tuning | UK | Який номер рахунку клієнта для оплати ліцензії? |
| TN04 | tuning | EN | What is the exact GPU kernel-only p99 for every future embedding query? |
| TN05 | tuning | RU | Какой идентификатор заказа на покупку офисных кресел? |
| TN06 | tuning | UK | Яка затверджена дата релізу enterprise ANN у production? |
| RN01 | review-split | EN | What is the serial number of the office printer? |
| RN02 | review-split | RU | Какое имя и телефон дежурного сотрудника в ночную смену? |
| RN03 | review-split | UK | Який IBAN постачальника обладнання? |
| RN04 | review-split | EN | Which exact SHA256 digest belongs to an unspecified customer PDF never registered in this corpus? |
| RN05 | review-split | RU | Какова согласованная цена годовой подписки на сторонний CRM? |
| RN06 | review-split | UK | Який номер договору оренди дата-центру? |

## Freeze and review

- This is a starter, not a release set. Keep original synthetic fixture as regression. Validate duplicate and paraphrase families across splits, source overlap and policy contradictions; reassign/remove leakage before freeze. Review-split is for dry-run only; reserve a genuinely reviewer-controlled unseen final holdout.
- A reviewer checks each original anchor and expected fact, adjudicates supporting/alternative evidence, validates no-answer and grades. Record review version, reviewer role and disagreement, no fabricated review. Add independently sourced authorized small documents, actual PDF/text tables, Python and code/config examples; predeclare 300+ answerable / 100+ negative and cohort sample requirements under DATASET-001.
- Export a versioned executable fixture only through existing evaluator schema evolution and tests. This Markdown is the starter corpus/query manifest, not a drop-in JSON fixture or proof of execution. Freeze SHA256 and source-to-chunk mapping for each actual run. No labels or answers in searchable corpus or model tuning input for held-out cases.
