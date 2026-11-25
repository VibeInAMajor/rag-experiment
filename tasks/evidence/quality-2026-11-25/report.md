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

## Продолжение: локализация провалов и исправление Markdown

Дополнение от 2026-11-25 сохраняет прежние восемь arms и их результаты. Повторного retrieval, model inference, SQL replay или новой тестовой БД для этого анализа не было. Существующий `EvidenceCoverage` сопоставил сохранённые rankings/context с исходными OPEN anchors: 2448 наблюдений, ровно 306 вопросов на arm, 261 answerable и 45 no-answer. Для объединения провалов baseline/selected разобраны 101 answerable-вопрос и все 45 no-answer: всего 146 ID. Полные locators, source hashes, версии, альтернативные evidence sets, eligible chunk IDs, ranks, context membership и следующие владельцы сохранены локально в `runs/current-stack-2026-11-25-v2/failure-analysis.json` и `FAILURE_ANALYSIS.md` под `.local/evaluation-holdout/quality-check/`. Разбивки по 102 семьям на arm остаются там же. В репозитории — только агрегаты в `metrics.json → failure_localization`.

Исторические поля `primary@k` в этом OPEN delivery означают попадание любого полного размеченного факта. Отдельного reviewed primary label нет: новый анализ явно сохраняет **Primary Evidence Hit = NOT_EVALUABLE**, отдельно от any-complete-fact coverage. Полные relevance Recall/nDCG также остаются NOT_EVALUABLE при sparse qrels.

| Наблюдение, из 261 answerable | Baseline | Code-query |
| --- | ---: | ---: |
| Любой полный факт @1 | 176 | 180 |
| Все факты @5 | 222 | 225 |
| Все факты в top-10 union | 232 | 238 |
| Все факты в контексте 2048 токена | 225 | 228 |
| Есть факт вне candidate top-10 | 29 | 23 |
| Есть факт в top-10, потерянный при @5 | 14 | 16 |
| Есть факт в top-10, потерянный контекстным prefix | 12 | 12 |
| Полный reviewed anchor отсутствует в union всех eligible indexed chunks | 0 | 0 |

Потери пересекаются: строки нельзя складывать как независимые вопросы. Top-10 union — верхняя граница candidate pool, а не обещание вместить все факты в пять чанков или 2048 токена. Ранжирование не восстановит факт вне pool. У baseline earliest per-facet attribution затрагивает 41 вопрос по структуре, 70 по ranking и 11 по candidate retrieval; у selected — 40, 68 и 10 соответственно. Часть candidate/context потерь имеет более раннюю структурную причину. 657 translated facet observations на arm соответствуют 219 family/facet identities; переводы не считаются независимыми фактами.

Парное сравнение трёх наблюдаемых целей (any-fact@1, all-facts@5, all-facts in context): 17 улучшений, 8 регрессий, 1 смешанный случай и 235 неизменившихся answerable-вопросов. Ещё 45 no-answer — отдельные NOT_EVALUABLE; всего 306. По языкам improved/regressed/mixed: EN 8/2/0, RU 6/1/0, UK 3/5/1. Сводный выигрыш не скрывает украинские регрессии.

| Домен | Answerable | Any fact @1, baseline → selected | All @5 | All context | Improved / regressed |
| --- | ---: | --- | --- | --- | --- |
| Art | 24 | 13 → 15 | 17 → 17 | 17 → 16 | 3 / 1 |
| Literature | 60 | 32 → 34 | 51 → 52 | 50 → 52 | 6 / 2 |
| Kubernetes | 57 | 37 → 36 | 45 → 45 | 46 → 47 | 3 / 3 |

Гипотеза «увеличить длину — значит улучшить контекст» не подтверждается: 768-token arm даёт 4 улучшения против 14 регрессий all-context относительно baseline; потери из полного candidate pool растут с 12 до 25 вопросов. Уменьшение overlap до нуля даёт 0 улучшений против 7 регрессий all-facts@5. Более широкий overlap даёт 0/3 для этой же цели. Heading-input даёт 8/13 any-fact@1 и 6/4 all-context; универсального улучшения нет. Это парные наблюдения, а не причинное доказательство по каждому механизму. Окна source-only и распределённые anchors видны в per-facet lineage; все reviewed spans покрыты eligible union. Entity/alias mismatch и полнота альтернативной разметки остаются UNKNOWN там, где captured judgments этого не устанавливают.

**Неподтверждённые проверки остаются явными.** Точные ранги пропущенных фактов после top-10 не захвачены. Прежние disposable БД удалены; текущий UI сообщает только lexical profile и работает уже с изменённым корпусом. Нельзя выдать новый поиск по нему за top-20/50 probe старого pinned Dense arm. Native FTS controls исторически прошли 10/10: stored vectors равны native projection, исходный chunk соответствует native AND tsquery. Это подтверждает исправность хранения/операционного контроля и поддерживает диагноз restrictive conjunction, но не заменяет отсутствующие native lexemes/AND/subset/OR dumps для каждого из 306 исходных вопросов. В UI нет native token inspector; эта часть J.1 остаётся открытой. По всем 45 no-answer сохранены original automated absence reviews, отрицательные spans, соседи и distance gaps; семантическая достаточность соседей UNKNOWN, answerability NOT_IMPLEMENTED/NOT_EVALUATED, generation NOT_EVALUATED. Не было ни измеренной false acceptance, ни успешной abstention.

### Отдельная UI-проверка исправления Markdown

По прямому запросу пользователя исправлены существующие parsing/chunking owners: сервисные HTML-комментарии, frontmatter и Hugo delimiters исключены из индексируемой проекции; локальные tooltip labels и тела блоков сохранены. Literal code сохранён, внешние Hugo definitions/includes/version values не вычисляются. Небольшие соседние структурные единицы упаковываются в пределах прежних token/character budgets; заголовки присоединяются к содержимому. Явная карта проекции сохраняет оригинальные source envelopes, строки и SHA-256. Это новый processing fingerprint, без миграции или автоматической подмены старых source versions.

Реальные операции выполнены через UI: **Replace file** для всех 31 originals, затем просмотр всех **645** новых чанков, включая вторую страницу deployments. Heading-only chunks: **0**. Папка корпуса: **31/31 Ready**. Для services.md число чанков изменилось **154 → 43**, исходный SHA-256 сохранился. Отдельный локальный control document дал пять фрагментов: ancestor headings вместе с prose; heading + fenced code; heading + table; heading + list; EN/RU/UK text. Service markers удалены, literal comments/Hugo examples внутри code сохранены. В probes.md один фрагмент намеренно содержит Hugo syntax внутри inline code. Примеры и raw UI evidence остаются под игнорируемой локальной quality-папкой.

В пользовательском UI создан и выполнен новый **QUALITY-001 · Markdown evidence** — Search query → Keyword search → Search results, профиль postgres-fts-baseline-r1. Настоящий lexical control вернул пять результатов из новой версии services.md, первый — заголовок с пояснением и YAML. Экспорт пайплайна: локальный `Downloads/quality-001---markdown-evidence.json`. Это acceptance исправления и видимая схема исполнения; новый Dense score/прирост relevance **NOT_EVALUATED**, девятого scored arm нет.

Дополнительный UI-контроль после последнего API restart: Markdown с начальным `---` без закрывающего metadata delimiter успешно опубликован одним чанком, весь body сохранён (строки 1–3). Это закрывает обнаруженный риск ошибочно удалить всё содержимое такого файла как frontmatter. Естественный lexical-вопрос дал zero matches, его короткий literal control — пять результатов; серверные corpus_load/retrieval/projection stages показаны в новом пайплайне. Эти два UI-запроса относятся к текущему корпусу, а не заменяют native probes исторических arms.

Проверки этого продолжения: реальные ingestion/retrieval/content checks через UI; Hatch 1.18.2; Ruff, formatting и mypy для семи изменённых backend/test-файлов прошли с exit 0; `git diff --check` прошёл; frontend `npm run build` прошёл для обновления ранее устаревшего `dist`. Ruff сообщил только о недоступной записи cache, проверка кода завершилась успешно. Существующие parser/chunker assertions обновлены под projection/packing contract, добавлен один regression case на очищенный source с точными citations. CLI unit/integration suites в этом продолжении не запускались по требованию выполнять функциональные проверки через UI; прежние 156/108 относятся только к frozen snapshot. Нового production evaluation-кода, зависимостей и миграций нет. Последние байты report/metrics проверены существующим статическим `current_stack_artifact_audit` (конфигурированные credentials, credential URLs, vector arrays, private JSON payload fields); результат и точные SHA-256 — в локальном `artifact-safety-audit-ui-continuation.json`, отдельно от исторического аудита.

## Завершение QUALITY-001: Dense, FTS и парное сравнение чанкинга — 2026-11-26

**Статус задачи: COMPLETE как диагностическое исследование. Решение о качестве: `INSUFFICIENT_WITH_CURRENT_STACK`; рабочий профиль не повышался.**

Все новые runtime-проверки инициированы в локальном UI: восстановление/загрузка корпуса, свежая квалификация модели, governed backfill, реальные Dense/FTS HTTP-запросы и фиксированные read-only native SQL probes. Экран и tooling находятся только в игнорируемой локальной quality-папке; production API/UI не дополнены evaluation-функциями. Старые восемь arms сохранены. Прогон начался 25 ноября и завершился 26 ноября по Europe/Kiev.

### Изменение после Markdown cleanup

Сравниваются одинаковые 31 оригинал с проверенными canonical-LF SHA-256, 306 вопросов / 102 семейства (261 ответный вариант / 87 семейств). До: owners из `8cef42a`, raw Markdown r1 / structural chunks r2. После: текущие Markdown r3 / chunks r3. Модель, generic instruction, настройки 500/50, top-50 протокол и контекст 2048 `o200k_base` source-content tokens одинаковы. TXT-окна в этой паре не используются. Пара не является продолжением selector старой восьмивариантной матрицы.

Для обеих сторон применяется одинаковая явно объявленная интерпретация original evidence: только детерминированно удалённые служебные символы могут быть пропущены при проверке покрытия. Исходные labels/locators не переписаны; проверяются original bytes/hash, projection bounds/hash и actual chunk content hash. Все 182 review spans сохранены; removed-only anchors запрещены. Это coverage фактов источника, не Primary Evidence Hit и не точность ответов.

| Метрика | До | После | Дельта, п.п. | 95% интервал, п.п. |
|---|---:|---:|---:|---:|
| Хотя бы один полный факт @1 | 177/261 (67.82%) | 194/261 (74.33%) | +6.51 | [-0.38; +13.79] |
| Хотя бы один полный факт @5 | 245/261 (93.87%) | 255/261 (97.70%) | +3.83 | [+0.77; +8.05] |
| Все обязательные факты @5 | 222/261 (85.06%) | 237/261 (90.80%) | +5.75 | [+1.53; +10.73] |
| Все обязательные факты @10 | 232/261 (88.89%) | 246/261 (94.25%) | +5.36 | [+1.15; +10.34] |
| Все факты в фиксированном контексте | 226/261 (86.59%) | 240/261 (91.95%) | +5.36 | [+1.15; +10.34] |

Построение индекса с нуля: model HTTP attempts **195 → 94**, provider-reported tokens **198023 → 194749**; все попытки успешны, unknown usage = 0. Calibration/query traffic исключены. Cache reuse в этих отдельных свежих БД равен нулю; это не измерение incremental reindex.

Чанки: **1441 → 634**. Это canonical-LF pair; ранее зафиксированные 645 чанков основной UI-загрузки относились к файлам в checkout CRLF. Пара сравнивает только одинаковые нормализованные байты и не выдаёт свои scores за измерение основной БД. Парные исходы по @1, all@5 и context: `{"NOT_EVALUABLE_NO_ANSWER": 45, "improved": 34, "regressed": 10, "unchanged": 217}`. Интервалы: 2000 bootstrap-перевыборок семейств, переводы усредняются внутри семейства; пересекающий ноль интервал не доказывает улучшение. OPEN-разметка автоматическая, корпус небольшой, общие источники создают дополнительную зависимость.

Разбивки по доменам, языкам и intent, потери top-50 → top-10 → top-5 → context, токены и задержки сохранены в `metrics.json → ui_completion`. Full graded nDCG/relevance Recall и отдельный primary hit остаются NOT_EVALUABLE при sparse qrels. Все 45 no-answer запросов рассматриваются отдельно; выдача соседей не считается ложным принятием. Answerability и generation не реализовывались и не оценивались.

### Закрытие недостающих Dense ranks

- generic baseline: 29 targeted queries; 28 identical top-ten replays, 1 changed. Из 59 отсутствовавших facet observations полное покрытие найдено к rank 20 в 35, к rank 50 в 53; 6 остаются OUTSIDE_BOUNDED_TOP50. Точные first union/singleton ranks и исходные locators сохранены локально.
  Строго среди совпавших top-ten replays: 57 missing facets, из них 35 найдены к rank 20, 51 к rank 50; 6 вне top-50.
- selected code-query: 23 targeted queries; 23 identical top-ten replays, 0 changed. Из 50 отсутствовавших facet observations полное покрытие найдено к rank 20 в 25, к rank 50 в 44; 6 остаются OUTSIDE_BOUNDED_TOP50. Точные first union/singleton ranks и исходные locators сохранены локально.
  Строго среди совпавших top-ten replays: 50 missing facets, из них 25 найдены к rank 20, 44 к rank 50; 6 вне top-50.

Один generic top-ten prefix отличается после свежего re-embedding; два его missing-facet observations выделены из строгих identical-replay totals. Причина дрейфа UNKNOWN; исходные scored rankings не заменены. Следующая bounded probe принадлежит существующему embedding owner: сопоставить input hashes и повторить одинаковую форму батчей, без настройки на labels. Совпадение профиля не доказывает bitwise воспроизводимость векторов.

Прежние 1080 chunk IDs/contents восстановлены из проверенных исходных диапазонов и captured hashes, без повторного парсинга. Это восстановление chunk-level capture для document input без title/heading, не полная копия прежней upload history/file-version metadata. Каждый профиль заново квалифицирован при истекшем admission и выполнен governed backfill с исходным fingerprint. Расхождения replay явно учитываются; за пределами top-50 точный ранг не заявляется. Новые вектора не смешиваются между профилями.

### Нативная причина FTS zero results

| Корпус | Вопросы | AND zero | Несовпадения stored vector | Literal controls |
|---|---:|---:|---:|---:|
| after | 306 | 306 | 0 | 306/306 |
| before | 306 | 306 | 0 | 306/306 |
| frozen-code | 306 | 306 | 0 | 306/306 |
| frozen-generic | 306 | 306 | 0 | 306/306 |

`plainto_tsquery(simple, question)` требует все лексемы одновременно. Native lexemes, фактический AND tsquery, bounded OR tsquery, присутствие слов в корпусе, до 100 known-positive source vectors и HTTP literal controls проверены по каждому вопросу. В каждом корпусе 252 вопроса имеют отсутствующие в корпусе лексемы; у 54 все слова есть, но не вместе в одном чанке. OR является диагностикой; lexical policy не изменена и BM25/fusion не квалифицированы.

### UI, измерения и сохранённые данные

Дополнительно выполнено **664 Dense HTTP/SQL agreements** и **1224 natural + 1224 literal FTS HTTP** запросов; 1224 набора native SQL diagnostics. Итоговый именованный Dense-пайплайн создан, выполнен и экспортирован через настоящий Workbench; его проверка выполнена после freeze и не включена в scored denominator. UI: `http://127.0.0.1:8015/`; итоговая таблица: `http://127.0.0.1:8018/comparison`. Имена/экспорт: `ui_completion.ui_pipeline`.

Server duration берётся из штатного ответа; p50/p95/p99 доступны в `server_reported_ms`. `observer_with_oracle_ms` дополнительно включает независимый SQL oracle и source scoring, это не чистая HTTP/network latency и не browser rendering benchmark. Старые ASGI top-10 задержки не сравниваются с этим top-50 протоколом как одинаковая нагрузка.

Карточки поисковой выдачи всё ещё подписывают Markdown как `Page unavailable`, хотя документный просмотр уже показывает строки исходника. Это отдельная UI-ошибка; retrieval/scoring от неё не зависят. Production UI в этом продолжении не менялся.

Через UI выполнены существующие parser/chunker и локальные quality suites: **364 passed, 0 failed**, 35.56 s. Полный Haystack/frontend suite и production-load qualification не запускались; frontend source в этом продолжении не менялся. Статические Ruff F/E9 для временной UI-обвязки и `git diff --check` прошли. Исправление локального cleanup-вызова проверено фактическим удалением принадлежащих эксперименту БД; первый сбой и recovery сохранены.

Три ранних принятых UI-корпуса и БД неудачной подготовки «до» удалены после проверки owner marker. Неудачная подготовка пула сохранена отдельно и не включена в scores. Финальная owned test-БД оставлена для доставленного Live Dense-пайплайна; в локальном UI есть отдельная кнопка удаления завершённого временного корпуса. Основная БД, её документы и рабочий профиль не изменены. Исходные восемь временных БД были удалены ранее. Raw captures, SQL lexemes, вопросы, тексты результатов, case IDs, тестовые логи, calibration и implementation manifests остаются в `.local/evaluation-holdout/quality-check/runs/ui-comparison-2026-11-25/`.

Использованы существующие create_app/upload owners, parser/chunker/projection, PostgresPersistence, capacity calibration/governor/backfill, DenseService, _ObservedEmbedding/_sql_oracle/_audit_response, EvidenceCoverage и family-cluster bootstrap. Новых зависимостей, production evaluation-модуля и миграций нет. Наблюдаемые границы: FTS AND-policy, evidence ниже candidate cutoff, потери порядка/контекста и отсутствие semantic sufficiency. Исправления этих отдельных возможностей переданы существующим owner tasks; QUALITY-001 завершена без заявления о прохождении retrieval release gate.
