# Current-stack evidence retrieval — 2026-11-25

**QUALITY-001: диагностический прогон завершён. Решение: `INSUFFICIENT_WITH_CURRENT_STACK`.** Лучший допустимый вариант по заранее закреплённому правилу — `code-query`. Изменение рабочего профиля и разрешение выпуска не выполнялись.

## Данные и границы

Использован только reviewed OPEN V2 из DATASET-001: 31 оригинал, 306 вопросов EN/RU/UK, 102 семейства, из них 87 ответных (261 перевод) и 15 без ответа (45 переводов). ANSWER и Retrieval-R2 не читались для оценки или настройки. Шесть файлов защищённой поставки проверены только по размеру/SHA-256 и остались неизменны. Оригиналы, source spans и старый 52-case fixture сохранены. Использованы принятые автоматические эталоны локального handoff; независимый человеческий benchmark не заявляется.

Все восемь вариантов прошли настоящую загрузку через ASGI HTTP, существующие parser/chunker, governed Qwen3-Embedding-4B/TEI и disposable PostgreSQL. HTTP здесь измеряется внутри ASGI, без браузера и сетевого RTT. Для каждой выдачи проверены независимый exact SQL, ID, порядок, расстояния и provenance. Все 2448 Dense проверок совпали; также выполнено 2448 FTS запросов. Все восемь временных БД удалены. Основная БД не использовалась для записи.

Штатный exact-профиль включался только в disposable БД для фактического API-прогона. Выбор диагностического варианта не переключает рабочий профиль.

Большие Markdown, не проходящие действующий лимит, преобразованы прежним source-only адаптером в TXT line windows; оригиналы и лимиты не менялись. Длина чанка влияет и на размеры этих представлений: это измерение поддерживаемой ingestion policy, а не изолированный эффект токенизации. Heading-вариант включает штатный native guard с тем же пределом 8192; возможные изменения границ учитываются в churn. Формат, количество views/chunks и статистика worker приведены в metrics.json.

## Парное сравнение

Один семантический параметр за вариант; 384/38 и 768/77 — округлённые 10% overlap, 500/0 и 500/75 — 0% и 15%. Новые query instructions получили собственные immutable fingerprints и свежую штатную калибровку, без копирования допуска generic. Модель, размерность 2560, exact-порт и top-10 одинаковы. Каждый вариант заново заполнен governed worker; внутрипрофильное повторное использование идентичных inputs учтено отдельно.

Контекст — префикс ранжированной выдачи с бюджетом 2048 `o200k_base` токенов оригинального содержимого. При первом переполнении отбор останавливается; пересортировки, пропуска неудобного чанка и доступа к labels при выборе нет. Это бюджет source content, без prompt/citation overhead; генератор не запускался.

Здесь P означает наличие хотя бы одного полностью покрытого обязательного факта источника, а All — всех обязательных фактов. Это диагностическая known-source метрика; она не заменяет исчерпывающую graded relevance. Неразмеченные результаты остаются unknown.

| Вариант | Views / chunks | P@1 | P@5 | All@5 | All@10 | All в 2048 | HTTP p95, мс | × baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| generic-baseline | 144 / 1080 | 67.43% | 94.25% | 85.06% | 88.89% | 86.21% | 891.0 | 1.000 |
| technical-query | 144 / 1080 | 65.90% | 92.72% | 83.91% | 89.66% | 86.21% | 828.0 | 0.929 |
| code-query | 144 / 1080 | 68.97% | 94.64% | 86.21% | 91.19% | 87.36% | 937.0 | 1.052 |
| short-chunks | 181 / 1176 | 68.58% | 92.34% | 83.14% | 88.51% | 86.21% | 906.0 | 1.017 |
| long-chunks | 68 / 1258 | 63.98% | 91.57% | 83.14% | 90.04% | 82.38% | 953.0 | 1.070 |
| no-overlap | 144 / 1076 | 68.58% | 93.49% | 82.38% | 87.74% | 83.91% | 875.0 | 0.982 |
| wider-overlap | 144 / 1085 | 68.20% | 93.87% | 83.91% | 88.89% | 85.44% | 875.0 | 0.982 |
| heading-input | 144 / 1080 | 65.52% | 94.64% | 85.06% | 90.42% | 86.97% | 985.0 | 1.105 |

У `code-query` All в фиксированном бюджете — 87.36%, family-bootstrap 95% interval [80.84%; 93.10%]. Парная разница с baseline — +1.15 п.п., интервал [-1.53; +4.21] п.п. Переводы сначала усреднены внутри семейства; 2000 resamples, seed 20261125. Семейства с общими источниками остаются зависимыми: эти интервалы диагностические, без поправки за выбор из восьми OPEN вариантов. Настройка и отбор используют одни tuning data; популяционная независимость и подтверждение production quality не заявляются.

Выбор закреплён до просмотра новых scores: полный integrity и p95 ≤1.20× baseline, затем All в бюджете, All@5, P@1 и порядок минимальных изменений. Выбран диагностический вариант; достижение release gates из этого не следует.
Вердикт ограничен этим корпусом и заранее заданными восемью настройками.

Временные интервалы `code-query`; direct SQL oracle выполняется отдельно от HTTP-запроса:

| Интервал, мс | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| fts_http_wall_ms | 32.00 | 47.00 | 47.00 |
| http_wall_ms | 797.00 | 937.00 | 985.00 |
| provider_inference_ms | 156.54 | 177.41 | 226.12 |
| query_embedding_wall_ms | 531.00 | 625.00 | 672.00 |
| sql_oracle_wall_ms | 32.00 | 62.00 | 63.00 |

## Стоимость подготовки и запросов

Provider-reported usage отделён от размера итогового контекста. Churn сравнивает оригинальные body spans с baseline; неизменность span не разрешает перенос vector между разными fingerprints/input policies. Spans учитывают каждое появление диапазона, включая совпадающие представления. `generated/reused` — фактические счётчики штатного worker внутри свежей БД.

| Вариант | Document tokens | Query tokens | Generated inputs / reused chunks | Новые / прежние spans |
| --- | ---: | ---: | ---: | ---: |
| generic-baseline | 197677 | 14242 | 1039 / 41 | 0 / 1080 |
| technical-query | 197677 | 16996 | 1039 / 41 | 0 / 1080 |
| code-query | 197677 | 17608 | 1039 / 41 | 0 / 1080 |
| short-chunks | 198429 | 14242 | 1135 / 41 | 392 / 784 |
| long-chunks | 196639 | 14242 | 1199 / 59 | 473 / 785 |
| no-overlap | 190829 | 14242 | 1035 / 41 | 132 / 944 |
| wider-overlap | 201497 | 14242 | 1044 / 41 | 141 / 944 |
| heading-input | 216632 | 14242 | 1077 / 3 | 0 / 1080 |

Отдельная калибровочная нагрузка (не входит в стоимость поиска):

| Допуск | Sustainable TPM | Screen tokens | Sustained tokens |
| --- | ---: | ---: | ---: |
| capacity-code-query.json | 655360 | 574464 | 2605056 |
| capacity-generic.json | 622592 | 523776 | 2473984 |
| capacity-technical-query.json | 622592 | 522240 | 2457600 |

## FTS-контроль на тех же вопросах

Существующий FTS использует полный исходный вопрос без переписывания; это native `postgres_ts_rank_cd`, без BM25 или fusion. Пустая выдача сама по себе не является решением об отсутствии ответа. Полная детализация по группам остаётся в metrics.json.

| Вариант | FTS P@5 | FTS All@5 | NA с соседями / 45 | FTS HTTP p95, мс |
| --- | ---: | ---: | ---: | ---: |
| generic-baseline | 0.00% | 0.00% | 0 / 45 | 47.0 |
| technical-query | 0.00% | 0.00% | 0 / 45 | 47.0 |
| code-query | 0.00% | 0.00% | 0 / 45 | 47.0 |
| short-chunks | 0.00% | 0.00% | 0 / 45 | 47.0 |
| long-chunks | 0.00% | 0.00% | 0 / 45 | 47.0 |
| no-overlap | 0.00% | 0.00% | 0 / 45 | 47.0 |
| wider-overlap | 0.00% | 0.00% | 0 / 45 | 47.0 |
| heading-input | 0.00% | 0.00% | 0 / 45 | 47.0 |

## Языки, домены, намерения и семейства

Ниже baseline → `code-query`. Полные mean/95% intervals для каждого варианта, языка/домена/намерения, family macro и парных разниц находятся в [metrics.json](metrics.json).

| Группа | Ответных строк / семейств | P@5 baseline → best | All@5 baseline → best | All в бюджете baseline → best |
| --- | ---: | ---: | ---: | ---: |
| language:en | 87 / 87 | 95.40% → 95.40% | 85.06% → 86.21% | 87.36% → 88.51% |
| domain:ART | 24 / 8 | 91.67% → 95.83% | 70.83% → 70.83% | 70.83% → 66.67% |
| intent:procedure | 6 / 2 | 66.67% → 83.33% | 33.33% → 50.00% | 33.33% → 33.33% |
| language:uk | 87 / 87 | 91.95% → 94.25% | 82.76% → 85.06% | 83.91% → 83.91% |
| domain:LIT | 60 / 20 | 91.67% → 91.67% | 85.00% → 86.67% | 83.33% → 86.67% |
| intent:concept | 12 / 4 | 75.00% → 75.00% | 75.00% → 75.00% | 75.00% → 75.00% |
| domain:K8S | 57 / 19 | 91.23% → 91.23% | 78.95% → 78.95% | 80.70% → 82.46% |
| intent:multi-facet | 15 / 5 | 86.67% → 86.67% | 80.00% → 80.00% | 86.67% → 86.67% |
| language:ru | 87 / 87 | 95.40% → 94.25% | 87.36% → 87.36% | 87.36% → 89.66% |
| domain:MATH | 42 / 14 | 100.00% → 100.00% | 88.10% → 90.48% | 88.10% → 92.86% |
| intent:comparison | 30 / 10 | 96.67% → 100.00% | 93.33% → 96.67% | 90.00% → 96.67% |
| domain:CS | 42 / 14 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:configuration | 9 / 3 | 66.67% → 66.67% | 66.67% → 66.67% | 66.67% → 66.67% |
| domain:AZ | 36 / 12 | 91.67% → 91.67% | 83.33% → 86.11% | 91.67% → 88.89% |
| intent:definition | 15 / 5 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:negation | 12 / 4 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:code | 12 / 4 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:numeric | 9 / 3 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:interpretation | 15 / 5 | 93.33% → 93.33% | 93.33% → 93.33% | 93.33% → 93.33% |
| intent:troubleshooting | 6 / 2 | 100.00% → 100.00% | 50.00% → 50.00% | 50.00% → 83.33% |
| intent:multi-document | 21 / 7 | 100.00% → 95.24% | 33.33% → 42.86% | 47.62% → 52.38% |
| intent:causal | 30 / 10 | 100.00% → 100.00% | 100.00% → 96.67% | 100.00% → 93.33% |
| intent:hierarchy | 3 / 1 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:failure | 3 / 1 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:cross-language | 9 / 3 | 66.67% → 66.67% | 66.67% → 66.67% | 66.67% → 66.67% |
| intent:factual | 18 / 6 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:formula | 15 / 5 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:character | 6 / 2 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:identifier | 3 / 1 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| intent:numerical | 9 / 3 | 100.00% → 100.00% | 66.67% → 66.67% | 66.67% → 66.67% |
| intent:notation | 3 / 1 | 100.00% → 100.00% | 100.00% → 100.00% | 100.00% → 100.00% |

## Post-hoc достижимость primary@1

После заморозки predictions прежний `EvidenceCoverage` отдельно проверяет каждый кандидат и известные positive-overlap chunks корпуса. Полный факт из объединения нескольких чанков отличается от одного самостоятельного чанка с полным фактом. Это диагностика источника ошибки, без изменения ranking, контекста или правила выбора. Неразмеченные альтернативы остаются unknown; ceiling относится к известным source spans.

| Вариант | Нет цельного факта в одном чанке | Цельный факт вне top-10 | Цельный факт ниже rank 1 |
| --- | ---: | ---: | ---: |
| generic-baseline | 15 | 3 | 67 |
| technical-query | 15 | 3 | 71 |
| code-query | 15 | 3 | 63 |
| short-chunks | 18 | 6 | 58 |
| long-chunks | 15 | 3 | 76 |
| no-overlap | 12 | 3 | 67 |
| wider-overlap | 15 | 3 | 65 |
| heading-input | 15 | 6 | 69 |

## Ограничения и следующие владельцы

Плановые P@1 ≥95%, P@5 ≥98% и All@5 ≥95% проверяются по известным фактам. Полные graded nDCG@5 и relevant Recall@5 — `NOT_EVALUABLE_SPARSE_QRELS`: неполная разметка не превращена в grade 0. Измерены known facet coverage, first-complete-fact MRR, explicit-negative-only/mixed overlaps и unjudged counts. Полный релизный gate остаётся незакрытым независимо от point estimates.

Все 45 безответных запросов обрабатываются отдельно. Принудительные Dense-соседи не являются false acceptance: генерации/abstention нет. Это handoff в ANSWERABILITY. FTS сохраняет conjunctive `plainto_tsquery('simple', полный вопрос)`; пустые ответы не доказывают неисправность индекса. Отдельный буквальный FTS-контроль DATASET-001 (10/10) не повторялся; текущие 2448 полнотекстовых вопросов и их результаты сохранены без переписывания queries.

Ошибки primary@1 и известного покрытия у `code-query` разложены по query ID без публикации текста. Строка с полным конечным контекстом тоже включена, если полный primary-факт расположен ниже rank 1. Pure-negative/mixed overlaps сохранены отдельно для каждого затронутого запроса:

- RERANK: required evidence available in candidates but not top five: **13** строк.
- RERANK: complete single-candidate primary available below rank one: **46** строк.
- EVIDENCE-002: required evidence exceeds ranked context prefix: **2** строк.
- HYBRID/BM25 or CHUNK-004 diagnostic: evidence absent from candidate window; attribution unresolved: **23** строк.
- CHUNK-004: no single ingested chunk covers a complete known primary facet: **8** строк.

Маршрутизация описывает наблюдаемое место потери. Отсутствие фактов в top-10 само по себе не устанавливает причину: нужно различить lexical candidate recall ([HYBRID/BM25](../../quality/TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md)) и структурную подготовку ([CHUNK-004](../../TASK-RAG-CHUNK-004-policy-benchmark-and-tiered-enrichment.md)). Наличие в top-10, но не top-5 — [RERANK qualification](../../quality/TASK-RAG-RERANK-001-local-semantic-reranker-qualification.md) / [integration](../../quality/TASK-RAG-RERANK-002-qualified-reranking-integration.md); потеря в фиксированном префиксе — [EVIDENCE-002](../../quality/TASK-RAG-EVIDENCE-002-bounded-context-and-required-facet-coverage.md). No-answer передан в [ANSWERABILITY](../../quality/TASK-RAG-ANSWERABILITY-001-insufficient-evidence-and-abstention.md). Перечень всех ошибок и метрик каждой строки включён в metrics.json; raw predictions/mappings остаются локально.

## Сохранённая регрессия и проверки

Независимая арифметика по исходным labels и новый реальный 52-case model/HTTP/SQL replay воспроизвели primary@1 31/46, primary@5 44/46, Recall@5 86/92, first-any MRR@10 0.942029, first-primary MRR@10 0.804348 и nDCG@5 0.845519. `checksum-en` и `code-digest` снова имеют primary на позиции 6. `control-marlin-en` даёт hard negative на позиции 1. Все 6 no-answer возвращают 10 соседей. Это отдельная исходная синтетическая регрессия, не OPEN scores.

Выполнены реальные replay, matrix и проверки через Hatch 1.18.2. Ниже использованные команды из корня репозитория; replay и вся матрица V2 выполнялись после исправления Windows writer, с заново измеренными допусками. Перед повторением необходимо получить свежий допуск; имена output должны быть новыми:

```powershell
hatch --version
$qualityRoot = Join-Path (Get-Location).Path '.local/evaluation-holdout/quality-check'
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + $qualityRoot
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
$env:WORKBENCH_TEST_ADMIN_DSN = $env:WORKBENCH_DB_ADMIN_DSN
$env:WORKBENCH_TEST_APP_DSN = $env:WORKBENCH_DB_DSN
$runRoot = Join-Path $qualityRoot 'runs/current-stack-2026-11-25-v2'
hatch -e workbench-api run python -m scripts.workbench_embedding_capacity_benchmark --calibrate --output $runRoot/capacity-generic.json
hatch -e workbench-api run python -m scripts.workbench_dense_evaluate --run --model-directory A:/AI/TEI/qwen3-4b --capacity-config $runRoot/capacity-generic.json --output $runRoot/legacy-runtime.json
hatch -e workbench-api run python -m rag_quality.current_stack_run --output $runRoot --resume
# После обнаружения параллельных изменений: проверенный локальный снимок a44c9f9.
$repositoryRoot = (Get-Location).Path
$snapshotRoot = Join-Path $repositoryRoot '.local/evaluation-holdout/runtime-a44'
$snapshotQuality = Join-Path $snapshotRoot '.local/evaluation-holdout/quality-check'
$env:PYTHONPATH = $snapshotRoot + [IO.Path]::PathSeparator + $snapshotQuality
$env:MYPYPATH = $snapshotQuality
hatch -e workbench-api run python -P -m rag_quality.current_stack_run --output $runRoot --resume
hatch -e workbench-api run python -P -m rag_quality.run_frozen_checks --output $runRoot
hatch -e workbench-api run python -P -m rag_quality.current_stack_publish --root $runRoot --output (Join-Path $repositoryRoot 'tasks/evidence/quality-2026-11-25')
hatch -e workbench-api run python -P -m rag_quality.current_stack_artifact_audit --directory (Join-Path $repositoryRoot 'tasks/evidence/quality-2026-11-25') --output (Join-Path $runRoot 'artifact-safety-audit.json')
```

Локальные проверки: 156 passed, включая запрет некорректной публикации и корректность primary-rank handoff. Scoped backend suite: 108 passed без skips, включая 5 новых failure-contract cases и disposable DB tests. В начальном историческом запуске два DB tests были skipped без явных DSN. Первый прямой запуск pytest без PYTHONPATH завершился ImportError; исправлена только команда окружения. Ruff/check, formatting и configured mypy/types — PASS; дополнительные scoped mypy для изменённого benchmark и локальных модулей — PASS. Полный Haystack suite и frontend проверки не запускались: эта задача не меняет UI/core. Параллельные изменения рабочего дерева не включены в проверенный снимок. Concurrent production load и release holdout не измерялись.

В историческом V1 две попытки `long-chunks` остановились после 125 и 246 HTTP/SQL пар с `503 NOT_QUALIFIED` и persistent quarantine. Исходный OS exception не прошёл HTTP boundary; отдельный stress неизменённого writer воспроизвёл `PermissionError/WinError 5` именно при атомарном `Path.replace` после 6872 и 713 записей. Добавлены только bounded retries той же fsynced временной записи для Windows 5/32/33: до 6 попыток, суммарный backoff 310 мс. Постоянный отказ сохраняет старые bytes и quarantine, остальные ошибки не повторяются. После исправления 10 000 реальных записей завершились без необработанной ошибки; observer зарегистрировал 4 восстановленных отказа, charges копии ledger остались прежними. Настоящий ledger не удалялся, допуски восстановлены только новой калибровкой. Все восемь V2 arms, включая baseline/short-chunks и 52-case replay, запущены заново на одинаковых исправленных owners. Старые V1 artifacts сохранены и не участвуют в выборе.

Во время technical-query параллельная работа изменила Python API/ingestion/schema. Guard source hashes отклонил попытку после 306 HTTP/SQL пар; она сохранена отдельно, БД удалена, метрики не засчитаны. Последние два варианта выполнялись в отдельной копии a44c9f9: 96 owner-файлов побайтово совпали с первыми шестью arms, дополнительно проверен 301 файл прежнего Haystack source. Исходный tokenizer/sentence bundle подключён по проверенной общей директории; отдельная попытка привязки без этого bundle была отклонена до backfill и не засчитана. Общий admission ledger и взаимное исключение через два пути проверены по физической идентичности файла и реальному FileLock conflict. Параллельные UI/API изменения сохранены. Тесты и выводы относятся к фиксированному снимку, а не ко всем последующим изменениям рабочего дерева.

## Изменения, совместимость и воспроизведение

Изменения штатного кода: необязательный keyword-only query instruction для существующего capacity benchmark. Без аргумента профиль/fingerprint прежние; новая инструкция создаёт отдельную ревизию. Второе изменение — bounded Windows retry в существующем writer capacity ledger, с failure-contract tests и bugfix release note. CLI, API и UI не изменены. Повторно использованы владельцы parser/chunker, source mapping/EvidenceCoverage, capacity governor, backfill, Dense HTTP и independent SQL; второго relevance scorer нет. Миграции и новые зависимости не добавлены. Удаление необязательного параметра откатывает helper; writer fix можно откатить отдельно без изменения формата ledger. Это вернёт подверженность Windows replacement failures. Рабочие поколения/профили не переключались.

Изменённые tracked paths:

- [Capacity benchmark](../../../scripts/workbench_embedding_capacity_benchmark.py).
- [Capacity owner](../../../apps/workbench/embedding/embedding_capacity.py) и [его проверки](../../../apps/workbench/embedding/tests/test_embedding_capacity.py).
- [Release note](../../../releasenotes/notes/workbench-ledger-windows-locks-e632ae9c64e964bf.yaml).
- [Task](../../quality/TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md), этот отчёт и [metrics.json](metrics.json).

Raw evidence и временный код: `.local/evaluation-holdout/quality-check/runs/current-stack-2026-11-25-v2` и `.local/evaluation-holdout/quality-check/rag_quality/`. В Git входят отчёт, агрегаты с opaque IDs, task, изменения benchmark/writer, его тесты и release note. Секреты, векторы, вопросы, эталоны и тексты источников не опубликованы. SHA-256 локальных артефактов и frozen implementation manifest записаны в metrics.json. Повторный эксперимент требует сохранённой локальной поставки и новой свежей калибровки; истёкший допуск использовать нельзя.

- [x] Baseline независимо воспроизведён и immutable fixture сохранён.
- [x] Восемь predeclared OPEN вариантов реально выполнены с одинаковым контекстным бюджетом.
- [x] Парные метрики, интервалы, cohorts, tokens, churn и per-case handoff сохранены.
- [x] Отдельный diagnostic verdict получен; нет production/answer-quality claim.
- [x] Временные БД удалены, protected delivery и основные данные сохранены.
- [ ] Release qualification: вне QUALITY-001, остаётся заблокирована полнотой/разметкой.
