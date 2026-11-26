# DATASET-002 — полная локальная OPEN-разметка

Дата: 2026-11-26. Разметка и пересчёт завершены; результаты финальных проверок приведены ниже. Это новая добавочная ревизия всей OPEN-части. [Предыдущий частичный отчёт](../dataset-ranking-2026-11-26/report.md) сохранён как исторический результат и больше не определяет текущий объём задачи.

Покрыты **все 87 answerable семейств / 261 вопрос**, включая оставшиеся 69 семейств / 207 вопросов, и **все 15 no-answer семейств / 45 вопросов**. Всего 102 семейства, 306 вопросов EN/RU/UK, 31 исходник, 634 сохранённых чанка. Источники, вопросы, выдача и прежние gold-данные не изменялись; новых retrieval-запусков, моделей, БД и production-компонентов нет.

## Разметка и границы измерения

Роли 209 primary и 10 support исходных units проверены по оригинальным alternatives до просмотра нового пула. Учитывались отрицания, числа, имена, временной контекст, глава и явно запрошенный язык источника. Три перевода одного семейства проверены на эквивалентность; они не считаются независимыми наблюдениями.

Объявленный до новой разметки пул: уникальные пары «семейство — исходный chunk occurrence» из baseline top-10 всех 306 вопросов плюс чанки, полностью покрывающие проверенные primary anchors. Получено **1241/1241 оценок**, из них **226 primary (3), 393 support (1), 622 explicit negative (0), 0 UNKNOWN**. Из 245 начальных оценок 143 точно унаследованы из прежней ревизии, ещё 102 получены полным сопоставлением проверенных исходных anchors. Остальные **996** оценены через локальный UI по фактическому тексту без ранга, расстояния или имени arm. Совпавшие тексты показывались один раз с отдельным решением для каждого семейства. Ранее увиденные результаты QUALITY-001 исключают заявление о независимом blind review.

**Каждая из 3060 возвращённых позиций top-10 оценена**; @1/@5/@10 не имеют UNKNOWN и допускают point estimates для всех 261 answerable вопросов. Это полнота объявленного baseline-пула, не исчерпывающая оценка релевантности всех 634 чанков для каждого вопроса. Новая выдача другого arm потребует добавления неизвестных occurrences и новой заморозки до сравнения.

Grade 3 подтверждает хотя бы один полностью сохранённый primary unit, заранее признанный прямым ответом для данного вопроса. Grade 1 — полезный контекст без такого unit. Grade 0 — явное отсутствие поддержки после просмотра. Непросмотренный текст не равен нулю. При составном evidence unit union нескольких чанков не становится singleton primary chunk.

## Результаты сохранённого post-cleanup baseline

| Метрика, 261 answerable вопрос | @1 | @5 | @10 |
|---|---:|---:|---:|
| Primary Evidence Hit | 209/261 = 80,08% | 252/261 = 96,55% | 257/261 = 98,47% |
| First-primary MRR с отсечением K | 0,80077 | 0,87414 | 0,87670 |
| Judged precision, grades 1 или 3 | 93,10% | 74,02% | 62,84% |
| Pooled occurrence recall, grades 1 или 3 | 17,03% | 58,48% | 90,13% |
| Pooled primary-occurrence recall, grade 3 | 43,63% | 80,19% | 94,90% |
| Pooled graded nDCG, gain 2^grade−1 | 0,81938 | 0,78748 | 0,85343 |
| Known-primary unit recall, macro union | 73,28% | 94,44% | 96,65% |
| Known-primary unit recall, macro singleton | 73,28% | 93,49% | 95,69% |
| Все known-primary units, union | 173/261 | 243/261 | 249/261 |
| Все known-primary units, singleton | 173/261 | 237/261 | 243/261 |

Pooled recall считает occurrences из общего пула переводов/anchors; несколько разных перекрывающихся occurrences могут получать отдельный nDCG gain. Unit recall дедуплицирует альтернативы одного исходного unit. Поэтому эти показатели имеют разные знаменатели и не заменяют друг друга. Precision использует фактически возвращённые K позиций; все rankings здесь имеют минимум 10 позиций. MRR — среднее обратного ранга первого grade 3, с нулём при отсутствии primary в пределах K; первый support не засчитывается.

При @5 micro union: **586/627 translated unit observations = 93,46%**, singleton 580/627 = 92,50%; при @10 — 602/627 = 96,01% и 596/627 = 95,06%. Уникальных primary units 209, а не 627 независимых фактов. В сохранённом prefix-контексте 2048 source-content tokens все known-primary units покрыты union в **245/261**, singleton в **239/261**; прежний all-required-facts context — 240/261.

95% family-cluster bootstrap intervals (2000 resamples, seed 20261125): Primary@1 **72,41–87,36%**, @5 **92,72–99,23%**, @10 **95,79–100%**; pooled nDCG@5 **0,74306–0,82743**. Сначала усредняются переводы внутри семьи; общие исходники могут связывать и разные семьи. Это описательная неопределённость OPEN, не независимая release qualification.

| Домен | Семейств / вопросов | Primary@1 | Primary@5 | Primary@10 | Pooled nDCG@5 |
|---|---:|---:|---:|---:|---:|
| Art | 8 / 24 | 16/24 | 23/24 | 24/24 | 0,67774 |
| Azure | 12 / 36 | 36/36 | 36/36 | 36/36 | 0,84095 |
| C# | 14 / 42 | 36/42 | 42/42 | 42/42 | 0,87983 |
| Kubernetes | 19 / 57 | 44/57 | 54/57 | 56/57 | 0,83670 |
| Literature | 20 / 60 | 39/60 | 55/60 | 57/60 | 0,70228 |
| Mathematics | 14 / 42 | 38/42 | 42/42 | 42/42 | 0,76693 |

По языкам — по 87 answerable вопросов: EN Primary@1 72/87, @5 84/87; RU 71/87, 85/87; UK 66/87, 83/87. Полные cohort denominators и интервалы находятся в [metrics.json](metrics.json).

Сохранены отдельно **45 no-answer / 15 семейства**, ошибки транспорта — 0. Проверка публичных фрагментов не превратила их в телеметрию названных частных кластеров, конфигурации вымышленных приложений, музейные инвентарные записи или текст отсутствующих глав. False acceptance, abstention accuracy, sufficiency decision и generation quality **NOT_EVALUATED**: соответствующих решений/генерации в этих captures нет.

Исторические метрики неизменны: any-fact@1 **194/261**, @5 **255/261**, all-facts@5 **237/261**, @10 **246/261**, all-context **240/261**. Они не переименованы в Primary Evidence Hit. Разница с новой разметкой — изменение измерения одной и той же выдачи, не прирост retrieval после нового запуска и не новая оценка эффекта чанкинга.

## Ревизия, воспроизводимость и проверка

- Revision: `source-first-ranking-open-r2-full` (суффикс r2 здесь номер ревизии, не чтение закрытого R2 dataset).
- Content digest: `a87a8e7c1fef975111acb59d6579e125c2c8c2a5d7eb74c16e29f97c5827d6a4`.
- Rubric SHA256: `3fb68239b9a5c91cf974c26414dafc516241d0388621265a9782b7a538b7a490`.
- Parent digest: `29a8ddccdb18eca67b9558a92b809419f9e622ce24383a4d4d95daaf261f7e3b`; прежние 143 labels, 21 source-role record и frozen artifact bytes сохранены.
- Legacy fixture SHA256: `a9e5af753d68a77bfdcc1d1b50c63ca0c3101e0eb749ab89bcbe454e3ef92d7f`; прежний scorer не изменён.
- Проверены 38 замороженных inputs; dataset digest, текущая implementation и output manifest фиксируются отдельно. Историческая implementation архивирована до изменения адаптера и проверяется по прежним хешам.

Сырые артефакты остаются в игнорируемой `.local/evaluation-holdout/quality-check/runs/ranking-judgments-full-open-2026-11-26/`: `source-cards.json`, `source-judgments.json`, `pool.json`, `candidate-judgments.json`, `revision.json`, `revision-manifest.json`, `parent-revision.json`, `baseline-rescored.json`, `R2_RUBRIC.json`. Там же находятся `code-checks/scoped.xml`, `code-checks/pytest.log` и `artifact-safety-audit.json`. Все source references, исходный текст, query-level scores и rationale доступны для локальной проверки, не публикуются в Git.

[Локальный UI разметки](http://127.0.0.1:8018/ranking-judgments) выполняет source review, candidate review, freeze, пересчёт и audit; [UI проверок](http://127.0.0.1:8018/) запускает существующие parser/chunker tests и ignored quality suite в Hatch workbench-api. После заморозки изменение source roles и judgments отклоняется. Тесты независимо вычисляют nDCG, pooled recall и first-primary MRR для каждого из 261 фактических answerable rankings при @1/@5/@10, проверяют все 3060 top-10 позиций, полный объём, неизменность parent и inheritance. Также сохранены проверки UNKNOWN, строгих grades, дубликатов, отсутствующего знаменателя, no-answer, stale locators/versions и реального multi-source union.

Переиспользованы `load_external_dataset`, `load_review_bundle`, `EvidenceCoverage`, `complete`, `chunk_text`, `score_ranking`, original/projection mappings и прежний локальный UI. Новых production файлов, зависимостей, API, схем или миграций нет. В Git добавляются только этот отчёт, агрегаты и task/handoff документы. Проверки runtime frontend, полного Haystack, DB/model и live retrieval не запускались: соответствующий код не изменён.

Итог: **409 passed, 0 failures/errors/skips, 43,41 s, exit 0** через UI в Hatch 1.18.2. Статические Ruff format и F/E9 с `--no-cache` прошли. Проверка безопасности через кнопку «Проверить безопасность отчёта»: **PASS, 2 файла, 0 совпадений** configured secrets, credential URLs, raw vector arrays и private fields. Audit фиксирует counts и хеши точных report/metrics bytes, не выводит configured secrets. Подтверждение результата хранится в локальном `artifact-safety-audit.json`; финальные bytes проверены повторно после оформления отчёта.

## Ограничения и передача QUALITY-002

Полный локальный объём DATASET-002 закрывает 87/87 answerable и 15/15 no-answer семейства; ограничение «оставшиеся 69 не размечены» устранено. Разметка выполнена агентом без заявления о независимом человеческом или blind review. Полнота corpus relevance вне объявленного пула, будущие arms, robustness, sufficiency/abstention и generation этим пересчётом не доказаны. Exhaustive corpus Recall/nDCG и соответствующие release gates остаются **NOT_EVALUABLE_POOL_IS_NOT_CORPUS**; полный retrieval GO не заявляется.

`R2_RUBRIC.json` имеет статус **PREPARED_NOT_APPLIED**. R2/ANSWER не открывались. QUALITY-002 получает полную OPEN-разметку и пригодные baseline @1/@5/@10 метрики; применение локального holdout возможно только после candidate freeze по прежнему процессу, без настройки на его результатах. Отдельные права, внешнее хранилище или два новых проверяющих не требуются.
