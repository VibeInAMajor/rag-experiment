# DATASET-002: локальная разметка ranking и допустимость метрик

Дата: 2026-11-26. Результат: **COMPLETE_BOUNDED_OPEN_JUDGMENT_REVISION**. Это завершение объявленного диагностического объёма, не retrieval release GO и не полная разметка всех 306 OPEN-вопросов.

## Что зафиксировано

До просмотра нового пула в задаче объявлены 18 answerable families из завершённой source-fidelity диагностики (по три на каждый из шести доменов), все их EN/RU/UK варианты и первые три отсортированные OPEN no-answer families. Итого **21 семейство / 63 вопроса: 54 answerable и 9 no-answer**. Выбор purposive; это не случайная репрезентативная выборка и не 63 независимых наблюдения.

Использованы только сохранённые post-cleanup UI captures QUALITY-001: 31 исходник, 634 активных чанка, прежние top-50 и фактически выбранный prefix context с бюджетом 2048 source-content tokens. Новых загрузок, запросов к модели, retrieval runs и БД не было. Исходники, вопросы, исторические labels и результаты QUALITY-001 не изменялись.

Сначала через локальный UI проверены исходные альтернативы и запросы на трёх языках, затем сохранены роли: **45 query-specific primary source units, 4 supporting units**, без неопределённых ролей в выбранных семействах. Только после этого построен пул из уникальных family/chunk occurrences в baseline top-5 всех 63 вопросов и чанков, целиком покрывающих проверенные primary anchors. Ранг, distance и arm в карточке оценки скрыты; сортировка по opaque ID. Предыдущая работа с QUALITY-001 раскрыта: независимая слепая оценка не заявляется.

Пул: **143 occurrences, 143 assessed, 0 UNKNOWN**. Из них 24 получили оценку через полное отображение проверенной исходной альтернативы; остальные 119 прочитаны и оценены по отдельности через UI. Итог: **36 primary (3), 39 support (1), 68 explicit negative (0)**. Для каждой оценки сохранены rationale, family, source/version/hash, исходный диапазон, chunk/content hash и projection revision. Новые прямые альтернативы привязаны к существующим primary units в добавочной revision; старый gold не переписан.

## Семантика и eligibility

| Метрика | Что считается | Допустимость здесь |
|---|---|---|
| Primary Evidence Hit@K | Есть хотя бы один оценённый primary occurrence | @1/@5: все 54 answerable; @10: часть исходов определена, один остаётся UNKNOWN |
| First-primary MRR@K | Среднее 1/r первого grade-3 occurrence; support не засчитывается | @1/@5: все 54; @10: 51, три неопределённых |
| Judged precision@K | Доля grade-1/3 среди возвращённых K; при коротком ответе знаменатель — фактически возвращённое число | @1/@5: все 54; @10: только один полностью оценённый prefix, общей оценки нет |
| Pooled recall@K | Найденные grade-1/3 occurrences / все grade-1/3 occurrences семейства в объявленном пуле | Только @1/@5; не recall по всему корпусу |
| Pooled primary occurrence recall | Найденные grade-3 occurrences / все grade-3 occurrences семейства в пуле | Отдельно от recall исходных смысловых units |
| Pooled nDCG@K | Gain = 2^grade−1, discount = log2(rank+1); IDCG по всем положительным оценкам семейства в пуле | Только @1/@5 при полностью оценённом пуле |
| Known-primary source-unit recall | Доля 45 проверенных primary units, покрытых исходными alternative sets или новой проверенной прямой альтернативой | Отдельные union и singleton результаты; фиксированный известный universe, не все релевантные сведения корпуса |
| Legacy any-fact / all-facts | Покрытие прежних обязательных source facets | Старые определения и числа сохранены; это не Primary Evidence Hit |
| Full-corpus Recall/nDCG, release gates | Требуют обоснованного полного relevant universe и остальных gate checks | **NOT_EVALUABLE_POOL_IS_NOT_CORPUS** |

Отсутствующий ID и null-оценка остаются UNKNOWN. Null нельзя передавать прежнему scorer как implicit zero. Если неизвестный occurrence расположен до первого известного primary, MRR не определён; известный primary всё же доказывает Hit, даже при других неизвестных позициях. Неизвестный элемент ideal pool блокирует pooled recall/nDCG даже при полностью оценённом возвращённом prefix.

Переводы одного family/chunk используют одну оценку. Альтернативы одного source unit не увеличивают знаменатель unit recall. Различные перекрывающиеся occurrences сохраняют собственную идентичность и могут давать отдельный gain в occurrence-level nDCG — это явное ограничение pooling. Полный multi-span union не считается одним primary chunk: отдельный regression case проверяет реальный Kubernetes unit, требующий нескольких источников.

## Пересчёт сохранённого baseline

Все строки @1/@5 ниже имеют **54 answerable queries / 18 families**. Macro — среднее по вопросам; поскольку у каждого семейства три перевода, полные macro и family-mean point estimates совпадают. No-answer исключены из этих знаменателей.

| Метрика | @1 | @5 |
|---|---:|---:|
| Primary Evidence Hit | 42/54 = **77,78%** | 49/54 = **90,74%** |
| First-primary MRR | 0,77778 | 0,83148 |
| Judged precision | 45/54 = 83,33% | 174/270 = 64,44% |
| Pooled relevant-occurrence recall, macro | 21,85% | 78,95% |
| Pooled primary-occurrence recall, macro | 50,46% | 83,33% |
| Pooled nDCG | 0,78571 | **0,78604** |
| Known-primary unit recall, macro, union / singleton | 77,78% / 77,78% | 87,04% / 87,04% |
| Known-primary unit recall, micro across translated unit observations | 105/135 = 77,78% | 116/135 = 85,93% |
| All known primary units, union / singleton | 42/54 / 42/54 | 46/54 / 46/54 |
| Legacy any-complete-fact | 45/54 = 83,33% | 52/54 = 96,30% |
| Legacy all-required-facts | 40/54 = 74,07% | 43/54 = 79,63% |

Разница any-fact@5 52/54 против primary@5 49/54 показывает, почему прежнее название primary нельзя было переносить на новый критерий. Изменился способ измерения, не retrieval и не качество ранжирования в этом запуске; прирост качества не заявляется.

В top-10 по всем 63 вопросам оценены **399/630 positions**, 231 остаётся UNKNOWN вне объявленного top-5 pool. Для answerable подтверждены 53 primary hits; для одного вопроса исход неизвестен. Поэтому общий Hit@10 — **53 подтверждённых / 54, один UNKNOWN**, возможный диапазон 98,15–100%; число 53/53 в eligible subset не является общим 100%. MRR@10 = 0,88693 только на 51 определимом вопросе; для всех 54 point estimate отсутствует. Pooled @10 намеренно не разрешены.

Known-primary unit recall@10: macro 92,13%, micro 122/135 = 90,37%; все известные primary units покрыты в 48/54 вопросах. Это полнота фиксированных исходных units, не relevance judging всех top-10 occurrences. В сохранённом 2048-token context все primary units покрыты в **45/54**, прежние all-required-facts — **42/54**. На этих prefix cutoffs union и singleton показатели совпали; это не отменяет различия определений и наличие multi-source unit.

Family-cluster bootstrap (2000 resamples, seed 20261125) сначала усредняет три перевода внутри family. 95% intervals: Primary@1 **59,26–94,44%**, Primary@5 **77,78–100%**, pooled nDCG@5 **0,66934–0,88597**. Общие исходники могут связывать и разные families; эти интервалы описывают только выбранный диагностический subset и не дают population qualification. Интервалы для неполных eligible subsets @10 нельзя использовать как общие gate bounds.

| Домен | Семейств / вопросов | Primary@1 | Primary@5 | Pooled nDCG@5 |
|---|---:|---:|---:|---:|
| Art | 3 / 9 | 5/9 | 8/9 | 0,68059 |
| Azure | 3 / 9 | 9/9 | 9/9 | 0,93498 |
| C# | 3 / 9 | 9/9 | 9/9 | 0,90104 |
| Kubernetes | 3 / 9 | 6/9 | 6/9 | 0,68941 |
| Literature | 3 / 9 | 4/9 | 8/9 | 0,65232 |
| Mathematics | 3 / 9 | 9/9 | 9/9 | 0,85790 |

По языкам (18 answerable на язык, общие 18 families): EN primary@1 15/18, @5 16/18, nDCG@5 0,78776; RU 14/18, 17/18, 0,81154; UK 13/18, 16/18, 0,75883. Малые correlated cohorts не квалифицируют critical-cohort release gates.

Все **9 no-answer / 3 families** сохранены отдельно. Их pooled occurrences проверены на соответствие конкретному запрошенному факту. Публичная документация не становится телеметрией частного кластера, конфигурацией названного deployment или счётом указанного аккаунта. Ошибок транспорта в этих сохранённых строках: 0. False acceptance, abstention accuracy, sufficiency decision и generation quality **NOT_EVALUATED**: соответствующего решения/генератора здесь нет.

Полный прежний OPEN baseline неизменен: 261 answerable, any-fact@1 **194/261**, @5 **255/261**, all-facts@5 **237/261**, @10 **246/261**, all-context **240/261**. Размеченные 18 answerable families не заменяют оставшиеся 69; отдельные primary/relevance оценки для остальных 207 answerable вопросов не заявляются.

## Freeze, файлы и повторная проверка

Revision: `source-first-ranking-open-r1`.

- Content digest: `29a8ddccdb18eca67b9558a92b809419f9e622ce24383a4d4d95daaf261f7e3b`.
- Rubric SHA256: `0840d9fa3546997c7533619be02dea383221d4168bc8dc30e35c54d803fff239`.
- Legacy synthetic fixture SHA256 до/после: `a9e5af753d68a77bfdcc1d1b50c63ca0c3101e0eb749ab89bcbe454e3ef92d7f`.
- Проверены 38 frozen input files, включая исходники, OPEN review/overlay, saved captures и прежний scorer/fixture. Dataset digest, implementation hashes и выходной manifest проверяются отдельно.

Подробности находятся в существующей **игнорируемой** папке `.local/evaluation-holdout/quality-check/runs/ranking-judgments-2026-11-26/`:

| Файл | Что проверять |
|---|---|
| `source-cards.json`, `source-judgments.json` | Вопросы EN/RU/UK, оригинальные alternatives/locators, primary/support роли и rationale |
| `pool.json`, `candidate-judgments.json` | 143 исходных occurrences, grades, новые прямые альтернативы и объяснения отрицательных оценок |
| `revision.json`, `revision-manifest.json` | Единая замороженная revision, digest, source/version/content lineage и хеши файлов |
| `baseline-rescored.json` | Все 63 case-level результата, eligibility и контекст отдельно |
| `R2_RUBRIC.json` | **PREPARED_NOT_APPLIED**, тот же rubric с digest текущей revision |
| `code-checks/scoped.xml`, `code-checks/pytest.log` | Фактические результаты проверок |

Локальная страница: [ranking judgments](http://127.0.0.1:8018/ranking-judgments). Подготовка, source review, 119 индивидуальных candidate judgments, freeze и пересчёт выполнены кнопками этой страницы. Она восстанавливает сохранённое состояние при перезапуске. Повторная запись source roles после pool freeze, перестроение существующего pool и изменение judgments после revision freeze отклоняются. Для нового arm требуется новая добавочная revision, а не overwrite.

R2/ANSWER в этой задаче не открывались. Rubric только подготовлен; применение — у QUALITY-002 после freeze настроек кандидата, без циклов настройки по результатам holdout. Пул будущего arm необходимо дополнить и заново заморозить по тем же правилам, прежде чем сравнивать pooled метрики.

## Проверки и найденные риски

Проверки запускаются через существующий локальный code-check UI (`http://127.0.0.1:8018/`) в Hatch workbench-api. Точные targets: `apps/workbench/parsing/tests/test_parsing.py`, `apps/workbench/chunking/tests/test_chunking.py`, существующий ignored quality suite. Добавлены локальные проверки hand-computed arithmetic, support vs primary, UNKNOWN перед/после primary, неполного ideal pool, строгих grades/cutoffs, отсутствующего primary denominator, no-answer, дубликатов, реального multi-source union, stale source/version/content/locator, неполной разметки и frozen digests. Независимая формула дополнительно проверяет каждый из 54 фактических answerable baseline rankings при @1/@5.

**406 passed, 0 failed/errors/skipped, 43,05 s, exit 0** через UI: прежние 372 проверки и 34 новых локальных ranking cases. Первый проход 403 cases сохранён отдельно как `initial-403.xml/log`; финальные XML/log не заменяют исторические QUALITY-001 артефакты. Hatch 1.18.2. Статические Ruff format и F/E9 выполнены для новой локальной обвязки. Начальный Ruff formatter упал из-за локального cache defect; повторный запуск с `--no-cache` успешен. Frontend, полный Haystack suite, DB/model/live retrieval проверки не запускались: production code и runtime contracts этой задачей не менялись.

Кнопка «Проверить безопасность отчёта» использует прежний `current_stack_artifact_audit`: два публикуемых файла проверены на configured credentials, credential URLs, raw vector arrays и private payload fields. Результат **PASS, два файла, ноль совпадений**, локальное подтверждение: `artifact-safety-audit.json`. Сам audit хранит только counts и точные хеши проверенных report/metrics bytes; секреты не выводятся.

Обнаруженные методологические ошибки предотвращены в добавочном adapter: implicit zero для sparse labels, first-support MRR вместо first-primary, смешение occurrence recall и unit recall, ложный singleton для multi-span union, включение no-answer в answerable знаменатель и показ 53/53 eligible Hit@10 как общей оценки. Исторический scorer сохранён: его implicit-zero контракт остаётся корректным для полностью оценённой synthetic fixture; adapter допускает его только после проверки полноты нужного пула.

Переиспользованы `load_external_dataset`, `load_review_bundle`, `EvidenceCoverage`, original/projection mapping, `complete`, `chunk_text`, `validate_result`, `score_ranking`, family bootstrap и прежний локальный review/check UI. Новых production API, компонентов, зависимостей, схем и миграций нет. Код и raw artifacts остаются локальными; в Git — этот отчёт, агрегированные metrics и task/handoff документы.

Оставшиеся ограничения: 18/87 answerable families; субъективная agent-разметка без независимого blind review; incomplete corpus relevance universe и top-10 qrels; небольшие correlated cohorts; no-answer decisions и generation не измерялись. QUALITY-002 получает пригодные **bounded pooled** метрики, явные eligibility и frozen rubric, но full-corpus gates и итоговый GO по-прежнему не разрешены.
