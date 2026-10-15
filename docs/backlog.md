# Единый рабочий backlog T-Lab

Обновлено 15 октября 2026. Канонический текущий статус приведён в таблице; последующие разделы сохраняют историю первого среза и принятых уточнений. Пользователь разрешил ночное исполнение, meaningful tests и ограниченные pilots параллельно с постоянной research-линией. Рабочий development-протокол — daily purchase ranking, eligibility48h и горизонт24h. Окончательный whole-decision lock и отложенная проверка ещё не выполнены.

Координатор единолично ведёт этот файл и Git-публикацию в research-ветке/draft PR; Root и C11 разрабатывают/проверяют additive heldout inference/oracle; координатор ведёт whole-decision/source owner, acceptance и Git. Четыре модели016 с одним независимым observer, source016, ручной контроль019, smoke008 и данные017 приняты. Основная ветка не изменяется. Данные, локальные модели и run artifacts ignored; в Git — код, документация и агрегированные отчёты. Платный cloud не подключается.

## Текущий статус

| ID | Приоритет | Статус | Владелец | Обязательные зависимости |
|---|---|---|---|---|
| TLAB-001 | P0 | done | root; accepted B2/coordinator | — |
| TLAB-002 | P0 | done | root; accepted B2/coordinator | —; integration contract проверяется после001 |
| TLAB-003 | P0 | done | root; accepted B2/B3/coordinator | — |
| TLAB-004 | P0 | done | root; accepted B3/coordinator | — |
| TLAB-005 | P0 | done | root; accepted B2/coordinator | — |
| TLAB-006 | P0 | done | metrics worker; accepted B3/coordinator | — |
| TLAB-007 | P0 | done | heuristic worker; accepted B2/coordinator | — |
| TLAB-008 | P0 | done: two-fit smoke; strong tuning tracked019 | root; independent code/output accept | —;017 accepted |
| TLAB-009 | P1 | done: source/model accepted; wholeblock rejected, base41 frozen | root; independent direct-list reviewer | 008 smoke accepted; core→runner→100Q review gates |
| TLAB-010 | P1 | blocked | unassigned | 008 |
| TLAB-011 | P1 | blocked | unassigned | 008 |
| TLAB-012 | P1 | blocked | unassigned | 008, measured resource gate; user-item review completed |
| TLAB-013 | P1 | blocked | unassigned | 008, одна выбранная sensitivity |
| TLAB-014 | P1 | in_progress | permanent research line | постоянная линия, не блокирует ядро |
| TLAB-015 | P0 | in_progress: contract/source core accepted; no actual heldout reads | coordinator owner/source; root prediction core; C11 oracle/review | accepted016 models; exact whole-decision/prediction lock, budgets, owner/oracles |
| TLAB-016 | P1 | done:4fits/4looks/1observer; development W=R2 accepted | root implementation; coordinator acceptance; C11 observer | immutable438 model seal; heldout claim separately015 |
| TLAB-017 | P0 | done | root; accepted B2/coordinator/source oracles | —; immutable train/selection collections sealed |
| TLAB-018 | P0 | phase1 +P0A supplied-score/public prefix accepted; regeneration pending | C11; root independent review |12-row relocated smoke; actual private package/bootstrap not executed |
| TLAB-019 | P0 | done: four fits / 12 prefixes, control sealed | root; independent replay and coordinator acceptance | immutable304-pin control; original failure preserved |

Принятые core-файлы и их исходные acceptance pins заморожены. Новая реализация использует отдельные модули; их scopes назначаются явно. Новые исполнители получают непересекающийся scope. Сообщение агента не является доказательством done: нужны actual files/diff/checks и независимый substantive review. Не повторять неизменные проверки после их прохождения; следующий run оправдывается новой правкой, failure либо конкретной неопределённостью.

Источники первой версии: [архитектура B1](backlog-reviews/architecture.md), [независимая верификация B2](backlog-reviews/verification.md), [синтез16 feature studies](features/index.md), [target research](target-research/index.md). B3 завершил [независимый скептический review](backlog-reviews/skeptical-review.md): first-five допустимы как provisional slice с отдельным scan/state resource gate. Это проверка плана, не подтверждение реализации или экспериментального выигрыша.

Исходный портфель завершён:58studies/13groupedreviews/6indexes. Ранние counts ниже — хронологические срезы. Постоянные primarysource rounds продолжаются; новые budgets не складываются автоматически. Один worker-slot сохраняется за research/paper rounds, второй — planning/test/review/implementation. Canonical hypotheses и execution statuses ведутся здесь, не в расходящихся списках.

## Правила и подробные задачи


Единственный источник очереди — `docs/backlog.md`; исходная архитектурная записка сохраняется отдельно для traceability. Координатор владеет backlog и Git. Каждая запись имеет постоянный `TLAB-NNN`, priority, execution status, owner, источники, зависимости, результат, acceptance, проверки и бюджет. ID не переиспользуется после отказа; новые исследования добавляют задачи или уточняют существующие с записью причины. В описании отделять факт, предложение и measured result. `done` требует фактических outputs, проверок и ссылки на run/commit; сообщение исполнителя этого не заменяет.

Execution statuses: `ready` — нет невыполненных обязательных зависимостей; `in_progress` — назначен единственный исполнитель и ограничен scope; `review` — результат готов, ожидает независимой проверки; `done` — принят; `blocked` — назван конкретный prerequisite; `deferred` — сознательно вне текущего среза. P0 означает необходимое ядро первого сравнения, P1 — следующую проверяемую гипотезу, P2 — дорогую/неподтверждённую ветвь. Авторские P0 разных исследований не складывать автоматически.

Уже выполненные EDA, schema/category audit, 16 feature notes и два review — источники, а не новые задачи «сделать EDA». Восемь target notes и два review готовы для переноса; первые две user×item notes готовы, но полный review этой серии ещё не завершён. Источники: [feature index](features/index.md), [review 01–04](features/review-01-04.md), [review 05–08](features/review-05-08.md), [данные](data.md), [category audit](category-recovery.md), [target index](target-research/index.md). Публикация последних источников — обязанность координатора, без ожидания всех 58 исследований для начала исполнения.

## Общая инфраструктура и первый срез

**TLAB-001 — временной контракт. P0, done, owner Root; accepted.** Единственный владелец `scripts/temporal_contract.py` и `tests/test_temporal_contract.py` — Root; остальные задачи импортируют контракт и не редактируют эти файлы. Результат: UTC `[t−W,t)`, глобальный read-before-update секундных групп, конфигурируемые target endpoints/maturity, coverage отдельно от observed age. Acceptance: нижняя граница включена, верхняя исключена; golden fixture, перестановка peers и добавление future suffix сохраняют past features; новых dependencies нет. Источники: оба feature reviews и [temporal protocol](target-research/06-temporal-protocol.md). Бюджет: небольшой stdlib fixture, без полного сканирования данных.

**TLAB-002 — versioned protocol configs и run manifest. P0, done, owner Root; accepted.** Результат: `configs/protocols/*.json`, manifest schema/validator и короткая спецификация запуска. Два development-пилота: A — ежедневный 00:00 UTC, eligibility по любому прошлому событию за 7d; B меняет только eligibility на 48h. Оба используют distinct purchase-set `[t,t+24h)` до обработки секунды t. Это исследовательские config-варианты, не окончательный выбор за пользователя. Action anchors, closed-right endpoint, next-purchase и H=72h описываются как допустимые конфиги, но не запускаются всей сеткой. Manifest хранит input checksum/schema version, code/config hash, UTC ranges, seed/hash-sampling, history/label/candidate policies, component fit-cutoff/refresh, budgets и artifact references. Acceptance: endpoints/maturity согласованы; `Y` не зависит от C; execution не принимает unknown fields/несогласованные диапазоны. Проверка: round-trip и заведомо невалидный конфиг. Бюджет: ≤30 минут разработки/проверки, без вычислений по raw. Источники: [anchors](target-research/01-anchors.md), [target](target-research/02-purchase-target.md), [reviews 01–04](target-research/review-01-04.md), [05–08](target-research/review-05-08.md).

**TLAB-003 — anchor/label feasibility. P0, done, owner Root; accepted B2/B3/coordinator.** Outputs: bounded pilot script, ignored query/label manifests и агрегированный `docs/experiments/anchor-pilot.md`. Development: 8–10 октября, максимум 2 000 eligible пользователей на день, отбор стабильным hash до labels. Сравнить A/B отдельно; сохранить зрелые queries без покупки, cold targets и долю same-second purchases. Acceptance: eligibility исключительно past; незрелые labels не равны отрицательным; binary targets независимы от retrieval; counts всех состояний сходятся. Проверки: tiny independent SQL oracle, censoring/endpoints из 001; API интеграция зависит от 001. До его готовности допустим отдельный bounded SQL прототип без повторной реализации production-контракта. Бюджет: ≤6 000 queries на вариант, ≤30 минут на вариант, DuckDB 2 threads/2 GB. Источники: [feasibility](target-research/08-feasibility.md), оба target reviews. При превышении лимита сохранить partial cost report, уменьшить заранее label-independent sample, не выбирать покупателей.

**TLAB-004 — past-only candidate union и coverage. P0, done, owner Root; accepted B3/coordinator.** Outputs: `scripts/candidate_pilot.py`, candidate manifest и coverage report. Первый вариант намеренно обходится без ItemCF: до 200 past-popular плюс до 20 recent distinct items, после дедупликации не более 220. Это новый небольшой budget config, а не незаметная подмена предложений M=200/1000. Задать popularity events/window, fallback, quotas, tie-break, dedup и недобор. U(t) — всё ранее наблюдавшееся, не stock-каталог. Acceptance: C⊆U(t), labels присоединяются после candidates; future positive никогда не вставляется; прошлые покупки не исключаются автоматически. Проверки: cold target, пустые C/history, ties, source overlap, future suffix; сопоставить coverage U→C и all-target denominators. Бюджет на выбранном основном pilot: ≤1,32 млн candidate rows до дедупликации, batches, ≤30 минут, peak RSS ceiling 6 GB. Источник: [candidates](target-research/03-candidates.md). Если coverage низок, это измеренный bottleneck для отдельной retrieval-задачи, а не основание менять C внутри feature ablation.

**TLAB-005 — компактный manual feature materializer. P0, done, owner Root; accepted B2/coordinator.** Outputs: `scripts/manual_features.py`, feature registry и meaningful oracle tests. Начальные 18 числовых колонок из review 01–04: user view/cart/purchase7d и distinct-viewed-items7d; pair view/cart/purchase7d и view/purchase recency по наблюдаемой истории; item view/purchase24h и distinct-viewers7d; user-category-ID view7d/share7d/recency; item-within-category view-share7d с item-view7d/category-view7d supports. Общие coverage, user/item observed-age и missing/availability flags идут отдельно; совпадающие supports не дублируются. Acceptance: одна feature definition = grain/types/window/unit/missing/support/fit policy; exact distinct expires по multiplicity, все 372 безымянных ID сохраняются; никакого user×catalog. Проверки: прямой bounded SQL против materializer, duplicate expiry, category ID≠code, нулевой denominator, глобальные peers/future suffix. Бюджет: tiny fixture → 100 queries → выбранный pilot, ceiling RSS 8 GB и ≤60 минут на pilot. При превышении уменьшить batch/state или sample, а не выдавать calendar distinct за rolling distinct.

**TLAB-006 — независимый ranking evaluator. P0, done, accepted B3/coordinator.** Outputs: evaluator и hand-computed fixtures. Полный Y задаёт Recall и IDCG, недоступные targets остаются misses; короткий список не заполняется отсутствующими positives с score −∞. Публиковать p(nonempty), conditional macro-query NDCG/Recall@20, отдельно all-query zero-convention и user-macro. Acceptance: при трёх targets и одном найденном первым Recall=1/3, NDCG≈0,469 при K≥3; пустое Y не смешивается с censoring. Парный user-cluster bootstrap пересчитывает исходный estimand, использует одни multiplicities для разности моделей. Проверки: ties, duplicate ranked items, C=∅, zero-positive bootstrap draw. Бюджет: tiny fixtures; до 1 000 bootstrap repeats на агрегатах. Источники: [evaluation](target-research/05-evaluation.md), review 05–08.

**TLAB-007 — baseline и измеренный cost ledger. P0, done, accepted B2/coordinator.** Outputs: popularity, last-view и recent-distinct rankers на том же C; агрегаты по history/support/repeat/cold/day; wall time, peak RSS, disk spill, row/feature counts. Acceptance: одинаковые query/candidate manifests и tie-break; pooled outcome не скрывает retrieval loss. Проверки: tiny end-to-end replay, metamorphic будущие события и peers. Бюджет: ≤30 минут; никаких установок или GPU для этих эвристик. Источники: target 01/05/08.

**TLAB-008 — сильный CPU boosting baseline. P0, blocked до 005/007 и проверенной доступности CatBoost.** Outputs: pinned minimal dependency change при необходимости, воспроизводимый training runner, model manifest и validation report. Сначала один PairLogit и один query-weighted BCE на одинаковом C/features; pair mass и sampling probabilities явные. Нулевые покупки остаются в evaluation, отсутствие ranking signal измеряется. Proposed calendar: warmup 1–8, train anchors 8–21, fit 22, validation 22–25, maturity 26 октября; test anchors 26–31 не читаются для выбора. Для выбранного `[t,t+H)` labels зрелы при `t+H≤cutoff`. Acceptance: trained-model cutoff, histories refresh и encoder freeze разделены; нет случайного CV, future negative cleaning или target insertion. Проверки: группы contiguous, вес пары/запроса, полностью отрицательная и полностью положительная группа, independent substantive review. Бюджет: CPU Mac, 2 threads, ≤60 минут на smoke/первый fit, ≤2 fit-конфигурации; расширение только после измерения. RTX 3070 не считать доступной. Источники: [training negatives](target-research/04-training-negatives.md), temporal protocol, [alignment](target-research/07-tlab-alignment.md).

## Эксперименты после ядра

Следующие задачи P1 первоначально `blocked` до 008; owner назначается отдельно. Каждая имеет один неизменный baseline, query/candidate hashes, основной validation estimand, cost ceiling и counterhypothesis. Предложенный promotion gate фиксируется до запуска: парная ΔNDCG@20 положительна с 95% интервалом выше нуля, ΔRecall@20≥−0,002, стоимость подготовки ≤2× baseline и внутри absolute budget. При неопределённом интервале статус гипотезы needs-pilot, без заявления пользы; при отрицательном эффекте/исчерпании бюджета — отрицательный результат либо deferred с причиной. Эти пороги — config-предложение, не измеренный факт. Pooled gain без срезов/стоимости не принимается. CI после многократного поиска не устраняет selection bias: все failed attempts/preparation/tuning входят в ledger, а final test остаётся locked.

- **TLAB-009 — block ablations.** Counts → distinct/recency → category share; максимум четыре fits, ≤2 CPU-часов. Output: paired validation table. Counterhypothesis: прирост объясняется recent-repeat или популярностью; acceptance требует одинаковых запросов и честного отрицательного вывода при неопределённой разности. Источник: оба feature reviews.
- **TLAB-010 — taxonomy и lexical перенос.** Два независимых experiment IDs: сначала path view-count/recency+coverage, затем full-code identity против одного prefix TF-IDF cosine при одном weighting. Fit vocabulary/IDF до первого downstream anchor; OOV/missing различимы, terminal-parent STOP и backoff поддерживают заявленный узел. Output: маленькие materializers и две ablation tables; ≤2 fits на эксперимент, ≤60 минут каждый. Dense отложить. Counterhypothesis: эффект — exact code/brand affinity. Источники: [taxonomy A](features/06-taxonomy-nodes/research-a.md), [text A](features/07-text/research-a.md), review 05–08.
- **TLAB-011 — один rule-layer.** Output: event-time-owner purchase item count/mass и одна share либо lift; learned layers и exact unique buyers отложены. Проверки: смена owner, empty support, own contribution sensitivity. ≤2 fits/60 минут. Counterhypothesis: слой переупаковывает прямые affinity/counts. Источники: [layers A](features/05-user-layers/research-a.md), review 05–08. Learned extension требует отдельного cutoff/version/layer coverage.
- **TLAB-012 — ItemCF compatibility pilot.** Не менять retrieval; добавить cosine mean/max/support только к фиксированному C. Daily snapshot `[b−7d,b)`, distinct-user pairs, history cap20, diagonal исключён, для режима аудитории других пользователей собственный вклад вычитается до нормировки; self-included режим — отдельный контроль, не утечка сам по себе. Начать со 100 queries: максимум 440 000 requested pairs до cache; ≤30 минут, 6 GB RSS. Output: coverage/cost report и до двух fits после прохождения ресурса. Missing top-K edge не равен нулевой cooccurrence; self-exclusion после top-K не устраняет влияние пользователя на shortlist. Counterhypothesis: score лишь повторяет direct history/popularity. Источники: [direct history](features/09-user-item/01-direct.md), [item neighbors](features/09-user-item/02-item-neighbors.md); full review серии — gate перед повышением приоритета, не блокирует ядро.
- **TLAB-013 — one-at-a-time sensitivity.** Реестр отдельных экспериментов: raw/collapsed history при неизменных labels; один nonnested P/V с supports; один trend/decay; price-state и дневной relative-price snapshot support≥20. Не запускать пакетом: выбрать максимум две гипотезы по диагностике, ≤2 fits/60 минут каждая. Проверки: P>V допустимо, V=0 missing; price ambiguity; expiry; rolling≠calendar. Counterhypothesis: новая информация отсутствует либо эффект обусловлен сменой weighting. Источники: feature 02/03/04/08 и reviews. Clipping/IsolationForest остаются P2/deferred.

**TLAB-014 — постоянная research-линия. P1, in_progress; current actor определяется active agent status.** Исследователи продолжают 58-topic очередь и регулярные primary-paper/generalization rounds; один рабочий слот сохраняется за research. Новые `HYP-NNN` содержат mechanism, novelty относительно нашего backlog, counterhypothesis, sources, inputs, строгую временную политику, baseline, experiment, metric/cost, acceptance/reject и scope переносимости. Статусы гипотез `accepted/needs-pilot/deferred/rejected` отделены от execution; rejected сохраняются с причиной. Output: `docs/research-lab/round-NNN.md` и новые/уточнённые HYP в canonical backlog. Один раунд: 3–5 primary papers/author repos, 2–5 содержательных гипотез либо обоснованные отказы; ≤60 минут на раунд, без обязательной квоты новых идей. Другие датасеты: сначала compatibility/license matrix, массовую загрузку не планировать. Источники: [experiment plan](experiment-plan.md), [embedding protocol](embedding-experiments.md), будущие research-lab rounds.

**TLAB-016 — бюджетная автоматизация. P1, done: development models/source accepted; heldout separately015.** Исходное описание первого среза ниже дополнено позднейшими fixed-procedure/selector/budget решениями; актуальные guards и владельцы — в таблице и последних audit entries. Первое сравнение: ограниченная grammar/random search над уже проверенными primitives против strong manual; LLM-guided — лишь отдельная ветвь с тем же бюджетом и отдельной авторизацией внешнего API. Initial cap: ≤12 materialized candidates и ≤4 validation fits, ≤2 CPU-часов; preprocessing/failed attempts входят в бюджет. Output: experiment register и operator provenance. Контргипотеза: выигрыш объясняется большим search budget. Источники: experiment plan, embedding protocol и HYP, прошедшая независимое review.

**TLAB-015 — заморозка решения и единственный final holdout. P0, blocked до принятого protocol и завершённых выбранных ablations.** Output: lock manifest выбранных features/loss/refit policy, один test report и полный отрицательный/положительный вывод. Acceptance: latest research не переоткрывает использованный test; test не используется для новых HYP и early stopping. Максимум один согласованный финальный run на ветвь; если протокол ещё не принят, продолжать development и инфраструктуру, не читать test ради снятия блокировки.

## Исполнение без бесконечного ожидания

Порядок первого среза: 001 параллельно 002/006; затем 003→004→005 и 007→008. Dependencies динамически снимаются только после проверенных outputs. Начальный общий потолок вычислений на Mac — 6 CPU-часов на ограниченные pilots/fits, не обещание длительности всего исследования. Budget exhaustion останавливает конкретный run, сохраняет причину/артефакты и переводит исполнение к следующей полезной задаче. Продолжающиеся исследования пополняют canonical backlog, не увеличивают автоматически search budget и не блокируют уже готовое ядро.


## Дополнение к первому срезу: resource gate и проверка

TLAB-003 выбирает ≤2000/day только из past-eligible, до чтения будущих labels; `Y` строится независимо отC. TLAB-004 top200+recent20 — явно budgeted pilot; U — prior-observed proxy, не stock. TLAB-005 registry18 — начальный cap, не доказательство сильного baseline. Caps выходных candidate rows не ограничивают scan42m или размер state: до масштабирования записать scan bounds/план, elapsed time, peak RSS/spill и число активных ключей; query timeout/лимит останавливает конкретный run с partial cost report, не превращает частичный счётчик в полную метрику.

Минимальный verification gate: hand-computed golden fixture + independent bounded DuckDB SQL (не production helpers) + tiny temporal E2E. Глобальные peers, нижняя/верхняя граница, coverage/first-past age, mature labels, exact distinct expiry и полный target IDCG обязательны. Future suffix сохраняет past features/candidates при неизменном context, но намеренно может изменить labels. Пройденные проверки не доказывают metric gain.

## Реестр начальных гипотез

Статусы hypotheses (`accepted`, `needs-pilot`, `deferred`, `rejected`) отделены от execution status. `accepted` означает принятие экспериментальной идеи, а не доказанную пользу. ID не переиспользуется; rejected сохраняется с причиной.

- **HYP-001, needs-pilot, TLAB-012:** item-neighbor compatibility может дать перенос на непросмотренные пары сверх direct history/popularity. Counter: score повторяет популярность/refresh. Inputs: past view-user postings, fixed C/history; experiment: scalar cosine mean/max/support против baseline на том же C. Scope: generalizable user-item primitive. Gate: сначала100 queries/cost≤30min/6GB, затем≤2 fits; primary ΔNDCG20, Recall/coverage/cost constraints из задач. Источник: [ItemCF note](features/09-user-item/02-item-neighbors.md); full-series review обязателен до fit.
- **HYP-002, needs-pilot, TLAB-016:** typed grammar search над проверенными entity/window primitives может улучшить manual features при равном search budget. Counter: выигрыш лишь от большего числа validation attempts. Inputs: registry005, fixed manifests/evaluator; ≤12 materialized candidates/≤4 fits/≤2CPUh, сравнение manual и random grammar; failed attempts оплачиваются. Strictpast/provenance обязательны. Scope: переносимые schema-aware primitives; primary metric и promotion/reject фиксируются до run. Источник: [feature synthesis](features/index.md); literature round уточнит первичные основания.
- **HYP-003, needs-pilot, TLAB-010:** path/lexical profile даёт перенос между родственными категориями. Counter: эффект объясняется exact code/brand identity. Inputs: observed code/brand as-of, past-fit vocabulary/IDF; одинаковые weighting и C; identity→prefixTF-IDF, ≤2fits/≤60min. Отдельные missing/OOV/coverage slices; метрики и reject gate как выше. Scope: hierarchy/text primitives, не восстановление отсутствующих описаний. Источник: [text review](features/review-05-08.md).

- **HYP-004, needs-pilot; execution blocked config extension, TLAB-004:** past recent history увеличивает coverage сверх popularity при том же бюджете. Counter: выигрыш лишь от большего shortlist. Compare popularity220 против popularity200+recent20 на тех же Q/U/Y, с явной dedup/fill policy; один pilot, безfit; all-target candidate Recall, repeat/new-item иcost. Источник: [B3](backlog-reviews/skeptical-review.md). Protocolv1 ограничивает popular_limit≤200: popularity220 требует отдельного versionedconfig/validatorchange иreview. Текущий004baselineunion не исполняет этоHYPсравнение; no-refill послеoverlap оставляет фактическийC≤220, не приписывать ему equal-budget220comparison.

HYP-005…010 зарезервированы координатору для уже выполненных отчётов; round001 резервирует HYP-011…020. Новые раунды проверяют дедупликацию, mechanism/counter/baseline/metric/budget/reproducibility; не обязаны создавать задачу из каждой статьи. Финальный test не переоткрывается последовательными rounds. Новые датасеты сначала schema/license/size compatibility matrix, без массовой загрузки.

## Actual results и audit

- 15 октября: опубликованы16 feature studies и2reviews; target8+2 сохранены отдельным коммитом. Первый paper round завершён; raw note и HYP будут сохранены следующей traceability-публикацией. Это завершённая документация, не обучение моделей.
- 15 октября: Root реализовал001 и передал наreview, B1/B2 planning завершены; B3 полный report завершён. Root сообщил12 passing unittest для001; B2 независимо проверил actual diff/tests и далaccept. Actual code/evidence001 проверены и публикуются в этом обновлении;001 принят. TLAB-002 Root начал в четырёх отдельно зарезервированных файлах; TLAB-006 назначен отдельному metrics worker.
- Модельные scores пока не измерены. Первые bounded003 run artifacts с label support/runtime/RSS получены и находятся на independent verification; до acceptance не объявляются окончательным результатом. Run manifests после исполнения сохраняются в ignored artifacts; принятые агрегаты и commit references добавляются сюда без затирания отрицательных результатов.


Файловый ownership текущего цикла: Root002 — `scripts/protocol_manifest.py`, `tests/test_protocol_manifest.py`, `configs/protocols/clock-7d.json`, `configs/protocols/clock-48h.json`; worker006 — `scripts/ranking_metrics.py`, `tests/test_ranking_metrics.py`. Все прочие исполнители эти файлы не редактируют.


### Принятый результат TLAB-001 — 15 октября2026

[Temporal contract](../scripts/temporal_contract.py) и [12 meaningful tests](../tests/test_temporal_contract.py) приняты после [независимой verification B2](backlog-reviews/tlab-001-verification.md). Coordinator прочитал actual files и выполнил scoped suite:12testsPASS, exit0,0.028s. Handgolden и independent in-memory DuckDB oracle не читают реальные логи. Приёмка относится к primitives; production read-before-update, distinct/metadata/candidates/fitted-state остаются gates следующих задач. Новых dependencies и raw-data изменений нет.


### Принятый результат TLAB-002 — 15 октября2026

[Protocol/run manifests](../scripts/protocol_manifest.py), два [provisional configs](../configs/protocols/clock-7d.json) и16 meaningful tests приняты после [B2 review с сохранённым finding/fix audit](backlog-reviews/tlab-002-verification.md). Coordinator прочитал actual revised files и получил16testsPASS,exit0,0.012s. Mandatory `available_at` теперь отдельно от fit data cutoff, выполняется `fit_cutoff≤available_at≤first_query` и поле входит в identity. Hashes фактических inputs/code/checkpoints должен предоставлять executor; declaration не подменяет проверку файлов. TLAB-003 manifest prerequisite снят, его code/data provenance проверяются отдельно.


### Принятый результат TLAB-006 — 15 октября 2026

[Ranking evaluator](../scripts/ranking_metrics.py) и [13 meaningful tests](../tests/test_ranking_metrics.py) приняты после [независимого B3 review](backlog-reviews/tlab-006-verification.md); сохранён [implementation handoff](backlog-reviews/tlab-006-implementation.md). Coordinator прочитал actual files и независимо получил13testsPASS,0.002s,exit0. Full Y остаётся знаменателем Recall/AP/IDCG, censored/empty различаются, four estimands и paired user-cluster bootstrap имеют отдельные denominators. Undefined draws не пересэмплируются; малый user support/defined-draw count и временные шоки ограничивают интерпретацию CI. Caller обеспечивает полноту labels/maturity/tie policy; приёмка вычислителя не доказывает model quality. Новых dependencies/raw scans нет. TLAB-007 evaluator prerequisite снят, retrieval004 acceptance ещё ожидается.

## Reservation gate до любых TLAB-008/009 fits — 15 октября 2026

По [round 001](research-lab/round-001.md) и [независимой критике](research-lab/round-001-review.md), общий development 22–25 октября предварительно разделён: **selection 22–23, locked confirmation 24–25**. Reservation относится ко всем связанным решениям: baseline/loss, ручные блоки, search branch, thresholds и budgets. Ни early stopping, ни tuning, ни выбор feature/loss/control не используют confirmation. До первой confirmation query фиксируются единственная выбранная claim/model/control и manifest; fit/maturity/available_at должны позволять этот freeze. Past histories обновляются по заданной политике, это не разрешает refit. Если reservation не обеспечена, метрики честно называются reused development/screening-only без confirmatory promotion. Использованный confirmation не открывается следующим round; final test остаётся закрытым. Bootstrap CI не исправляет selection bias.

Initial 008 ≤2 fits — **smoke**, а не доказательство «хорошо настроенного» boosting-контроля. Перед сравнением 016/final claim нужен отдельный заранее ограниченный tuning plan с ledger, на selection, без раскрытия confirmation/test. Автоматизация 016 остаётся центральным сравнением задания и не вытесняется бесконечным ростом ручных признаков; критерий task1 и live provenance сохраняются отдельной source note. Общий cap 016 ≤12 columns/4 fits/2 CPUh совместный для ветвей, не аддитивный на каждую HYP.

- **HYP-011, accepted-for-pilot, refinement HYP-002/TLAB-016:** typed nested user→distinct past items→current past item popularity→user reference. Difference с query constant не меняет standalone popularity ordering; проверяется interaction в boosting. Tiny independent oracle +100-query cost gate после 005/008/009; ≤4 columns/1 fit внутри общего ledger. Full Y/candidates неизменны, strict-past общий t. [Механизм, контргипотеза и точный опыт](research-lab/round-001.md).
- **HYP-012, deferred, refinement HYP-002/TLAB-016:** semantic vs blinded LLM vs seeded grammar в той же DSL, при том же column/fit budget. Внешний API не авторизован, raw rows/validation feedback proposer не получает; это design-only. Invalid/duplicate attempts не заменяются. [План](research-lab/round-001.md).
- **HYP-013, deferred, альтернативная ветвь TLAB-016:** train-only joint residual probe вместо LLM-ветви, не поверх её бюджета. До исполнения нужны selector loss/query weights, score offset/scale, deterministic importance/tie policy и обоснование interaction inputs. In-sample selector — риск качества, не сам по себе temporal leak; OOF fits не получают бесплатный budget. [Review границ](research-lab/round-001-review.md).
- **HYP-014, rejected для текущего бюджета:** готовый ExploreKit meta-ranker без versioned compatible corpus/model. Причина отказа — отсутствующие inputs и скрытая стоимость их получения, не опровержение метода. [Сохранённый отказ](research-lab/round-001.md).

Online Retail/UCI рассматривается только как schema/license/size compatibility matrix: CC BY 4.0, invoice-line grain, no views, cancellation as-of; missing customer нельзя сливать в одного пользователя. Файл не скачивался, переносимость/quality не измерены. Новый dataset pilot не расширяет автоматически fit budget.


### Принятый результат TLAB-003 — 15 октября 2026

[Bounded anchor/label pilot](experiments/anchor-pilot.md), [actual runner](../scripts/anchor_pilot.py) и13 synthetic tests приняты после [независимого source/code review, deadline finding/fix и новой provenance сверки](backlog-reviews/tlab-003-verification.md). A/B сохраняют по 6000 mature Q, 43/104 positive Q, 51/121 targets, cold1/0. Новыйexecutor после persistent deadline fix дал10.16/9.70s,RSS712.1/710.5MiB,engine peak spill0. Старые artifacts не перезаписаны; новые Q/Y полностью совпали по bidirectional EXCEPT ALL. B48h выбран только как provisional более плотный smoke для004; это не окончательный выбор target/population. Support слишком мал для уверенных тонких ablations; будущий development expansion должен оставаться label-independent.


## Incremental research archive — 15 октября 2026

Теперь сохранены36 из58 независимых исследований:16 features,8 target,5 user×item,3 candidate,2 model,2 loss. Original4 research cross-reviews готовы; остальные9 reviews выполняются после соответствующих групп. Family indexes явно промежуточные: [user×item](features/09-user-item/index.md), [candidate generation](candidate-generation/index.md), [models](model-selection/index.md), [losses](loss-selection/index.md). Предложения и авторские budgets не принимаются автоматически.

Проверенное liveусловие [task1](task1-requirements.md) требует сильный ручной boosting pipeline и experimental evidence для автоматизации features либо превосходящего tunedboosting метода; architecture/target/loss не предписаны. В interface deadline25октября23:59, timezone не установлен. Source-note — парафраз authorized readonly чтения Root, answer/submit не менялись.

[Независимый prereview005](backlog-reviews/tlab-005-design.md) принял18-grainMVP с gates: category denominator включает товары внеC; exactanchor сохраняется; historical event-attached categories не переклассифицируются currentmetadata; latestbucket known+NULL — ambiguity. Root owns scripts/manual_features.py, tests/test_manual_features.py, configs/features/manual-18.json, docs/experiments/manual-features.md. Synthetic разрешён, production после004accept.

007 worker owns scripts/heuristic_baselines.py, tests/test_heuristic_baselines.py, docs/experiments/heuristic-baselines.md. Three fixedC rankers: purchase-distinct-user popularity; recent-source-first поexistingrecent20; last-view7d по всемfixedCпарам. Это разныеdeclaredscorers, одинаковыеQ/Y/C иfullY evaluator006. Production после004accept исобственного code/provenance gate,≤30min/6GiB. Не менятьRoot005 илиupstreamмодули.

LightGBMresearch выявило nativeNDCG all-zeroquery=1 иразнуюzero-grouptrainingсемантику LambdaRank/XE_NDCG. External006fullY evaluator иявныйtrainmask обязательны; nativecandidate-onlymetric не подменяет end-to-endcriterion. Model02proposed12trials/8h насемейство не принято: действуетsharedbudget, reservationgate ипредварительныйtuningplan.


### Принятый результат TLAB-004 — 15 октября2026

[Candidate pilot](experiments/candidate-pilot.md), [runner](../scripts/candidate_pilot.py),14synthetic tests и [независимый review +final source/provenance audit](backlog-reviews/tlab-004-verification.md) приняты. Fixed Bsample:6000Q,1 226268uniqueCrows,121fullY/92hits,positive-querymacroRecall78.365%,84informativepairwisegroups. Repeat-pair coverage71/73 противnew-pair21/48; этоdiagnostic, некаузальныйвыигрыш. Runtime1.476s/RSS635.3MiB,spill0. FullC independently rebuilt изsource безmismatches; config200+20/no-refill иQ/Yfingerprints не менялись. Retrieval prerequisite005/007снят; собственные code/review и100-querycost gates остаются.


### Принятый результат TLAB-007 — 15 октября 2026

[Fixed-C heuristic pilot](experiments/heuristic-baselines.md),17meaningful tests и [независимый code review +execution audit](backlog-reviews/tlab-007-verification.md) приняты. На том же6000Q/121Y/C: recent-source-first/last-view conditional NDCG20=0.489135,Recall20=0.649038 противpopularity0.073133/0.187500. Это exploratory sanity benchmark;84informativegroups/104positiveQ слишком мало для тонких conclusions. New-pair hits всех трёх6/48,repeat recent70/73. Runtime29.551s/RSS878.7MiB/spill0,все3 678804orderedpositions и четыре estimands сверены независимымsource/formulaoracle.008 prerequisite007снят;005 runner finding/fix и label-independent train/selection expansion остаются gates. Accepted core001/002/003/004/006 combined suite68PASS0.731s;007 separately17PASS0.457s.


### Принятый результат TLAB-005 — 15 октября 2026

[Typed manual18](experiments/manual-features.md),18 meaningful tests и [независимый review/fix +final source/provenance audit](backlog-reviews/tlab-005-verification.md) приняты.100Q/20477pairs→full6000Q/1 226268pairs,18core/45output columns. Full5.128s/RSS2.01GiB,spill0,Parquet3.87MB. Exact fixed-C/retrieval columns, labelblindsubset и324 independent source feature comparisons совпали. Engine buffer high-water≈2.95GiB выше requested2GB; причина не установлена, hardcapclaim отсутствует. SeparateRSS8GiB gate пройден; scale017partitioned/resource gates остаются.008 infrastructure prerequisites005/007 сняты, но phase/dependency/tunedmodel/automation gates ещё открыты.


### TLAB-017 plan accepted, runtime pending — 15 октября 2026

[Additive development plan](experiments/development-collection.md) и [independent finding/fix review](backlog-reviews/tlab-017-plan-verification.md) приняты только как validator/shardplan/plannedidentity:9testsPASS0.016s. Root owns scripts/development_collection.py, tests/test_development_collection.py, configs/development/train.json, selection.json, confirmation.json, docs/experiments/development-collection.md. Train8–20 из5 неизменённыхv1shards≤3days/≤6000Q, outer≤26000Q/≤5.72mC; cutoff21/available22. Selection22–23, confirmation24–25locked, final26closed.

Runtime collection ещё не реализована/не исполнена. До017done нужны acceptedproducer/source/config/output lineage, exactQ/C/Y/features/count completeness, nooverlap/gaps, partitionedexports, source spotchecks, resource/errorledger. Planned counts не measured counts. Confirmationlock требует available_at≤frozen_before≤firstquery; actualselectedwinner chronology/metricsavailability доказываютсяruntime, неphase-onlyschema.008Rootdependency preparation получает только pyproject.toml/uv.lock +dependencyreport; старыеartifactpins не переписываются, новаяlock требуетновой reviewed lineage. StrongtunedB/automationfits ещё не выполнены.


### TLAB-008 dependency accepted, baseline fits pending — 15 октября 2026

[CPU environment](experiments/cpu-environment.md) и [independent dependency verification](backlog-reviews/tlab-008-dependency-verification.md) приняты:CatBoost1.2.10 officialwheel,51existingpinsunchanged,7newlockentries/1directdep. Root tinyCPU API checks1iteration/8syntheticrows не являются realbaselinefits. Coordinatoractualimports+PyPI/lockhashcheck и103accepted-coretestsPASS1.726s подnewenv; B2 plan0179PASSотдельно. Currentlock4675021…85eab — новаяlineage, oldacceptedartifactpins не переписываются.017runtime/externalshardreview/collectionacceptance и full-Y checkpointselection/tunedB/automation gates ещё открыты. Nativecandidate-onlymetric/implicitbestmodel не выбирают checkpoint.


## Актуальная сводка research и дедупликация — 15 октября 2026

Сохранены58 из58 independent studies:16 features,8 target,8 user×item,12 candidate,8 model,6 loss. Готовы13 из13 grouped cross-reviews: features2/target2/useritem2/candidate3/model2/loss2. [User×item synthesis](features/09-user-item/index.md) завершён; остальные family indexes явно промежуточные. Ранние counts в хронологических sections отражают предыдущие срезы. Исходная очередь58studies/13reviews завершена; постоянные literature/generalization rounds продолжаются отдельной линией; raw notes не удаляются при расхождениях.

Material amendments: historical item×category numerator вместо общего item count в category share; UserKNN N−1[u∈population] вместо безусловного N−1; latest global metadata bucket без older-clean backoff; graph group weights по retained seed mass, endpoint probabilities отдельно от visit counts. Full-Y checkpoint criterion должен реально выбирать модель. BCE all-mature и pairwise informative populations различны; native equal-label semantics не унифицированы. Review ссылки и repro находятся в family indexes.

| HYP | Статус и связь | Ограничение |
|---|---|---|
|045|needs-pilot, refinement002/011/016|Category-bound nested reference,8T/U+3supports=11columns внутри existing cap |
|046|needs-pilot, execution gate045|Exact shared DAG equality; symmetric20min timing, no extra fits |
|051/056|needs-pilot, одна ALS family|Fold-in против pooling на тех же V; encoder/downstream costs отдельный заранее bounded ledger |
|052/055/059/066|rejected duplicate|SASRec protocol/ItemCF001/grammar002/warm-up freeze соответственно |
|053|needs-pilot, category retrieval|Category-quota вариант032 объединён сюда; normalization-only032 rejected |
|054|needs-pilot, retrieval price|Не fixed-C feature029; median cancellation и reference weighting проверяются |
|057/058|deferred до neural support gate|Full vs sampled CE; uniform vs actual mixed law; авторские GPU budgets не приняты |
|060|deferred|Mature target-rate encoder, отдельная availability/cost policy |
|061/062|needs-pilot, ItemCF retrieval|Не feature001; новый equal-budget/refill protocol до запуска |
|063|deferred до tuned B/resource gate|Candidate-conditioned vs mean pooling, matched architecture/loss budget |
|064|deferred|Cross layers после полезного compact MLP, не дополнительная обязательная family |
|065|deferred до encoder gate|Purchase+any с purchase-only/any-only/reweighted-single-head controls |
|067/068|deferred до graph cost gate|Walk4 vs matched walk2; max vs mean, retained mass/versioned sampling |
|069/070|deferred до source gates|UserCF/audience marginal retrieval с одинаковым actual C-size; квоты400+100 не приняты |
|071/072|reserved|M06 base frozen ladder уже есть в embedding protocol; integration review до новой HYP |

[Round002](research-lab/round-002.md) и [critic](research-lab/round-002-review.md) уточняют016: primary confirmation against frozen tuned B; выигрыш только над ухудшенным B+S не promotion. Сохраняются shared≤12columns/4fits/2CPUh; scoring B входит в time ledger без нового fit. HYP046 symmetric setup/cache/AB–BA timing; если evidence недостаточно, equality accepted, speedup inconclusive. RelBench/OneBM/F-IVM поддерживают механизм, не доказывают REES46 quality. Другой dataset остаётся compatibility matrix, без downloads.

008 dependency принята, real fits blocked до017 runtime/shard semantic reviews/collection acceptance; source/current-lock approval не равен fresh-hash autoaccept.017 Root runtime in_progress в owned файлах, другие workers их не редактируют. Старые acceptance pins сохраняются, новая lock требует новой producer lineage. Исследовательская линия и substantive review исполнения работают параллельно.


### Prospective decision gap, не принятая новая reservation — 15 октября 2026

Selection anchors22–23 с H24h дают последние доступные labels24Oct00; first confirmation24Oct00 оставляет нулевой интервал для выбора/compute. Confirmation не читался и runtime017 его не открывает. До freeze008/confirmation prospectively выбрать положительный gap: например firstconfirmation25Oct00 либо сократить selection до22Oct. Нужны actual metric/selectedwinner availability≤frozen_before<firstconfirmation, bounded compute ledger и отдельная reviewed config change; никакой post-hoc замены уже использованного holdout. Сейчас это open decision gate, не approved schedule.

Root008 owns scripts/train_baselines.py, tests/test_train_baselines.py, configs/models/cpu-smoke.json, docs/experiments/boosting-baselines.md; contract/synthetic разрешены, real fits только после017 acceptance. HYP073 needs-pilot ALS retrieval отдельно от existing fixed-C ALS051/056;074 rejected duplicate. HYP075/076 reserved для independent L06, не автоматически зарегистрированы. [M06 integration review](model-selection/integration-review-06.md) — дополнительный single-note audit, не один из13 grouped reviews.


Loss6+2reviews [завершены](loss-selection/index.md), без новых train/quality claims. M07 [sequence proposal](model-selection/07-sequential.md) archived;077/078 reserved, новая hypothesis не сформулирована. L06 validation075/076 тоже reserved. Runtime017 firstreview нашёл generic unsealed-child retry blocker; Root fresh output attempt namespace сохраняет partials и costs,20scopedtestsPASS, independent re-review pending. Producer approval не выдан до acceptance; root008 выполняет только contract/synthetic.


### TLAB-017 runtime code accepted, реальная collection ещё не принята — 15 октября 2026

[Initial fault review](backlog-reviews/tlab017-runtime-review.md) и [independent re-review](backlog-reviews/tlab017-runtime-rereview.md) сохранены. Retry namespaces исправлены для каждого unsealed producer; scoped20PASS B2/coordinator и independent before-parent-seal faults подтвердили обычный resume/cache/artifact preservation/cumulative costs. Producer train5fdc4dce…8b918 и selectionc2c6ba09…81b74 approvals выданы на14actualpins каждый, sourceDB/newlock/currentcode сверены; confirmation не approved. Root выполняет первый bounded pass только до waiting_for_shard_review. Далее independent fullQ/Y/C source oracle→externalshardapprovals→Fresume→numericspotchecks/collectionacceptance;017notdone/008realfitblocked до этого gate. Coordinator oracle tiny2shardfixture Q4/Y2/C8 прошёл; это не actualtrain/selection result.


[Model8+2reviews](model-selection/index.md) завершены, candidate10+2groupreviews опубликованы. Последние candidate11/12 и group09–12 ещё не объявлены опубликованными.085 lexical retrieval needs-pilot как sourceprotocol с matchedidentity/prefix/expansion;086 dense retrieval deferred до lexical residual/resourcegate.079/080/081/082/083/084 reserved без сформулированных новых hypotheses.

Sourceoracle017: train26000Q/619Y/5317058C/496positive/444retrieved, selection4000Q/96Y/817149C/73positive/65retrieved; все Q/Y/C source-rebuilt,6externalshardapprovals выданы. Train F fullrowset=5317058C,78sourcepairs×18=1404formulachecks PASS; finalcollectionacceptance ещё ожидает complete audit/selectionFchecks.008 review обнаружил смену outputroot для повторныхfits и config parse/plan mismatch; Root исправляет, realfitapproval не выдан. Strong-control/016 nextplan остаётся proposal, budget не расширен.


### Исходный исследовательский портфель завершён — 15 октября 2026

Врепозитории58independentstudies,13groupedreviews и6familyindexes: [features16+2](features/index.md), [target8+2](target-research/index.md), [user×item8+2](features/09-user-item/index.md), [candidates12+3](candidate-generation/index.md), [models8+2](model-selection/index.md), [loss6+2](loss-selection/index.md). Дополнительныеintegrationaudits/literaturecritics неувеличиваютэтотcount. Разногласия/rawnotes иrejected/duplicateHYP сохранены; исходныеplanningbudgets не сталиаддитивнымиpermissions. Постоянная researchлиния продолжаетround003/004, исполнениенеожидаетновойэнциклопедии.

Следующиеprioritygates: 008revisedcodeacceptance→двухfitSMOKE→singlemetadata-price009design/100Qcost/≤1ablationfit внутриexisting009cap→featuresfreeze→boundedstrongtuning→016. Толькопослеprospectivepositivegap иactualdecisionfreeze однократнаяconfirmation. Никакихrealmodelqualityclaims здесьнет.


### TLAB-017 done — 15 октября 2026

[Independentcollectionaudit](backlog-reviews/tlab017-collection-verification.md) принимает обе immutable train/selection collections:26000/4000Q,619/96Y,5317058/817149C=F. Exhaustive Q/Y/C source reconciliation и1620numeric F comparisons, exactrowset/lineage/ranges,82/30externalpins. Production119.131s cumulativewall sum, spill0, RSS within8GiB; enginebuffer>requested2GB неhardcap. ActualCPU secondsнеизмереныотдельно, остаток6CPUh невыдумываем.008datasetgateснят; revisedtrainingcode+atomicfitconsumptionapproval ещёобязательны, realfitsнет.009будетоднимboundedmetadata/priceblock послеsmoke идоstrongtuning;≤1ablationfit внутриexisting009cap, безбесконечногоmanualgrowth.


### Research/design updates после58-noteportfolio — 15 октября 2026

[Round003+critic](research-lab/round-003.md), [Round004](research-lab/round-004.md), [Round005](research-lab/round-005.md) сохранены.003designaccepted,004/005criticpending; datasetlicenses/metadataavailability неизвестные явноотмечены, никакихdownloads.091–098reserved, refinements002/046 невыдаютсязановыеHYP. Слабыйdomainprior в016 не называетсяобученнымintelligence;2seeds недостаточныдляsuperioritystrategyclaim.

[Rawstrong/016proposal+canonicalamendment](backlog-reviews/strong-control-automation-proposal.md):4arms2I+2R×3ACTUALcols inclflags/support/coverage, onebundleattempt, fullfrozenBdedup (including004buyer-score), nofreereplacements/selector/fits. Execution/calendar/CPUledger approval ещёотдельные. 009DESIGN [original+acceptedsemanticamendment](backlog-reviews/metadata-price-design.md), [independentcritic](backlog-reviews/metadata-price-design-review.md) и [actualsyntheticAPIproof](experiments/metadata-price-api-proof.md) сохранены:3nominal+15numeric, NON-NULLvszero/nonfinite, piecewiseLOO, exactconditionalstates. После008smoke —100Qsource/costgate,≤1ablationfit внутри009, затемfreeze/tuning/016; sourcebaseartifacts не меняются.


### TLAB-008 code accepted; two-fit execution next — 15 октября 2026

[Initial review](backlog-reviews/tlab008-training-review.md), [binding re-review](backlog-reviews/tlab008-training-rereview.md), [independent child-lineage finding](backlog-reviews/tlab008-final-independent-review.md) и [final targeted ACCEPT](backlog-reviews/tlab008-final-independent-rereview.md) сохранены. Atomic project-wide fit consumption, same-byte config binding, exact plan/source/registry/code/phase pins, immutable017 child lineage и2threads дляfit/Pool/predict проверены. Финальный frozen runner bdab8bbe…412a:22 scoped tests PASS; independent3fresh-child faults reject; actual82/30collection approvals read-only accept. Первоначальные findings не удалены. Старые строки о pending017/data acceptance выше — исторические;017done.

[100Q read-only loader gate](backlog-reviews/tlab008-loader-gate.json):20560rows×41float32,3,371,840matrixbytes,0.839s/RSS134,643,712bytes,1informative/99all-negativegroups, query weight mass100. Никакихfit/predict/claims; это data-preparation cost, неmodelquality. Следующий шаг — coordinator exact current fit identity approval, ровно2fixed50treeCPU smoke fits и независимый replay exported models/scores/full-Y metrics. Tuning/009/016 budgets этим acceptance не открываются.

Методологическая граница: ingestion/hash/source coverage и месячный EDA уже читали полный исходный файл. Confirmation/final query-level targets и metrics не использовались для model selection; нельзя утверждать, что future raw bytes никогда не читались. Features используют толькоdata<t, held-out outcomes остаются закрыты для выбора моделей. Историческая симуляция availability и фактическое время вычислений различаются.


### Selection references иследующиеengineering gates — 15 октября 2026

[007selection source audit](backlog-reviews/tlab-007-verification.md) принят:4000Q/96Y/817149C, recent/last-viewconditionalNDCG20=.388390 противpop.105936, fullYRecall20=.571429/.233855.3fixedlooks,0fits,7.3595s/RSS749092864;all2451447rankedpositions и4estimands source-rebuilt. Oldpilotpopulationотличается. [Actualaggregate](backlog-reviews/tlab007-selection-aggregate.json) сохраняет200bootstrapdraws иslices; bootstrapнеустраняетdevelopmentadaptivity. ПодготовительныйCLIguardfailure ипоследующийwrapperKeyError невызвалиproductionrerun; неучтённоеwalltimeневыдумываем.

[Round006](research-lab/round-006.md), [007](research-lab/round-007.md), [008](research-lab/round-008.md) сохранены; independentcritic004–008inprogress. PairweightL2conclusion — sourceinference, toy0073fitsconsumed/2saved/APIfailure, noPaircomparison/free retry. Frozen008неизменён; prospectiveL2gridwithinexistingbudgetотдельноревьюится.

Следующая воспроизводимостьзадачаTLAB-018(proposed,ownershippending): portableindependentsourceverifier Q/Y/C/F дляacceptedmanual18/protocolv1, readonlyCLIdefault иexplicitwriteacceptance послеsemanticchecks/externalreviewdecision. Freshclone synthetic gate, schema/type/NULL/coverage/missing/supportchecks, freshlyresealedwrongvaluesfault; oldpinsнепереписывать. Первыйscopeнеподдерживает009/grammarавтоматически. Исполнение018после008smoke, безновыхfits/framework. Ignored data/approvalнеобязанынаходитьсявGit, ноregenerationне должензависетьотчата/temporaryscripts.


### TLAB-008 smoke done;009/018 in progress — 15 октября 2026

[Independentactualmodelaudit](backlog-reviews/tlab008-smoke-output-verification.md) принимаетrun195c89…846b6:2attempts/50trees, все817149scoresreplayed, 4fullYestimands и200paireduserdraws recomputed. Train6000Q/1227213rows/92informative/20741pairs; selection4000Q/73positive/96Y. LoglossconditionalNDCG20=.414448/Recall=.581213,Pair=.375197/.571429, recent007=.388390/.571429. Screeningobjectiveдляодного009ablation=Logloss, unchangedcontrolparams/C/Y;нетsuperiority/tunedB/promotionclaim. Runtime22.663335swall/RSS1.665GiB; productionCPUнеизмерен. Independentverification1.961741swall/2.307942CPUseconds,0additionalfits. [Aggregate](backlog-reviews/tlab008-smoke-aggregate.json) и [oraclearchive](backlog-reviews/tlab008-output-oracle.md) сохранены.

TLAB009rootowns scripts/metadata_price_features.py,tests/test_metadata_price_features.py,configs/features/metadata-price.json,docs/experiments/metadata-price-features.md. Purecore+testsreview→separaterunnerreview→100Qdirect-list-source/costgate→полныйexport→≤1Loglossablationfit внутри009budget. Accepted005/008/017immutable; no directsourcepriceSQLreuseinindependentoracle.

TLAB018auxworkerowns scripts/verify_development.py,tests/test_verify_development.py,docs/experiments/verification-workflow.md, перваяsynthetic/read-onlyiteration. Matchingmanual18/protocolv1 only; noactualacceptancewrites/realrescans/fits доindependentreview. Root009reviewpriorityперед018continuation; researchslotсохранён.

[Groupedcritic004–008](research-lab/round-004-008-review.md) acceptedсexplicit005/007appendices; nofreefits. [Round009](research-lab/round-009.md) отдельный198templateenumeration,нетmaterializedfeature/costqualityproof. BroadmonthlyEDAнеравноheldoutmodelselection;confirmation/finalquerymetricsдлявыборамоделейнеиспользовались.


### TLAB-019 — bounded tuning остатка strong-control requirement

Отделено от принятого двух-fit smoke008: первоначальная цель сильногоCPUbaseline ещё не выполнена. Ownerпокаunassigned; статусblocked до009featuresfreeze иindependentreview exactplan. [Rawproposal](backlog-reviews/strong-control-automation-proposal.md) и [Round010 alternatives](research-lab/round-010.md) предлагаютодну4fitgrid×3externalcheckpoints(50/150/300), не12fits. Перспективный≤60CPUmin/RSS8GiB иactualuser+systemledger требуютявногопринятия; это неавтоматическоерасширение двухsmokefits. Previousdevelopmentlooks отдельноучтены:007selection3fixedscorers+0082models,009≤1futureablation. Confirmation/finaltargets неиспользуютсядляподбора.

Послеacceptedtuning честныйclaim — manualcontrolselectedbyboundedsearch сраскрытымиограничениями, неглобальныйoptimum. Толькоегоfrozenfeature/model/checkpointmanifest задаётBдля016primarycomparison. Metadata009и018sourceverificationнеоткладываютцентральнуюавтоматизациюрадибесконечногоспискаручныхfeatures.


### TLAB-009 pure core accepted; bounded runner next — 15 октября 2026

[IndependentpurecoreACCEPT](backlog-reviews/tlab009-pure-core-review.md) и [measuredsyntheticevidence](backlog-reviews/tlab009-pure-core-evidence.json) сохранены. Exact4freeze pinsпроверены;15authortestsreproduced, independentdirectlist518rows×18=9324modelcomparisons/323fullRrows/518provenancerows,6nonfiniterejections/8faults/3metamorphiccases. Oraclewrittenbeforeproductionread, neverusesproducerexpectedvalues/sum-minus-self. [Durablelisthelper](../tests/oracles/metadata_price.py) и [harnessarchive](backlog-reviews/tlab009-pure-core-harness.md) опубликованы. Reviewcumulativeharness2.1111wall/2.4393CPUseconds/RSS123338752,authortestCPUunknownseparate. Rootfullsuite160PASS5.065sнаpurefreeze,неповторялибезновогоизменения.

[100Qrunnerproposal](backlog-reviews/tlab009-runner-proposal.md) и [coordinatordesignreview](backlog-reviews/tlab009-runner-proposal-review.md) разрешаюттолькоimplementationunderRootownership. Доactual100Qнужнынезависимыйrunnercodegate+exactexternalexecutionapproval;fullR/allselectedpairs sourceoracle,cost/RSS/CPU/selectionprovenanceнеподменяютсяsyntheticcoreacceptance. Fulltraincardinality≤4096/mixed59/noCTR иsingleLoglossfitещёнеприняты.

018syntheticproducerfixtureвыявилupstream017all-emptyrawsourceboundary:daily_outcomesотсутствуетиaggregationfails. Pinned017/actualnonemptytrainselectionнеизменены.018mustfailclosedнаincompletebundle,сохраняяerror/regression;zero-purchaseQиemptyCотдельны. Этоfutureproduceredgefix,нетпричиныобъявлятьrealoutputsневерными.


### TLAB-009 runner code accepted; actual gate pending — 15 октября 2026

[OriginalrunnerP1](backlog-reviews/tlab009-runner-review.md) и [targetedACCEPT](backlog-reviews/tlab009-runner-rereview.md) сохранены вместе сindependentfaultscripts/results. Aftercleanup fake+700wall/RSS8GiB+1 раньшедавалиcomplete; новый596f137e…52b4 проверяетterminalclose/CPU/serialization/auditwrite иприoverrunсохраняетfailed+rethrow.28scopedtestsPASS, own10cases (healthy+9faults) приняты. Exactsourceexecutionapproval100Qещёотдельныйgate; producercompleteнеравенsourceacceptance.

README/experimentplan обновлены: рабочийpurchaseprotocol/accepted017+008smoke,009pendingactual100,019/016неисполнены. СтарыеEDAутверждения«модели не запускались» больше невводятreviewerвзаблуждение. FullmonthEDAраскрыт,held-outtargets/metricsдляmodelselectionнеиспользованы.


### TLAB-009100Q source accepted; full/newmodel gates — 15 октября 2026

[Exactsourceaudit](backlog-reviews/tlab009-100q-source-verification.md) и [aggregate](backlog-reviews/tlab009-100q-aggregate.json) приняты:20586pairs×18=370548comparisons,20586provenance,full1603114Rrows/13anchors,93externalacceptancepins. Producer22.1533wall/33.1295CPU/RSS1.49GB; oracle18.4017wall/26.5238CPU/RSS955MB. No fits/labels; singletonNULLmeanverified. Newfull009Rootowns scripts/metadata_price_collection.py,tests/test_metadata_price_collection.py,docs/experiments/metadata-price-collection.md;[boundedproposal](backlog-reviews/tlab009-full-export-proposal.md) directionacceptedforimplementation, actualfullneedsnewcode/runtime/sourceacceptance. Frozen100module/spec не меняются.

Доablationmetrics009retentionpredicateзафиксирован: ALLsource/cost/encoded6000traincardinality≤4096/noCTR/effectiveparam/keygatesPASS, Recall20≥.5792133072407045 иNDCG20>.41444755081727774+1e−12→retainwholeblock. Иначеbase41; semantic/integrity/APIfaultSTOP, failedonefitconsumed/no replacement. Tolerance tieprefersbase. Это point-estimate screeningfeatureselection, неtrueeffect/practicalΔ≥.002/CIpromotionclaim. Full26000cardinality позднеесамостоятельный019gate.

019prospectiveGridCзаморожендодо009modelmetrics:4Loglossattempts depth{4,6}×L2{3,30},LR.05,max300trees/checkpoints50/150/300,CPU2,actualNewton10/AnyImprovement/random_strength1/boost_from_averageFalse/Plain/bootstrapNo. [Originalcritic](backlog-reviews/tlab019-prospective-plan-review.md) и [incumbentamendment](backlog-reviews/tlab019-incumbent-policy-review.md): ресурсный26000matrix/PoolgatePASS→все4newfits26000, resource/cardinalityFAIL→предъявленный6000fallback; integrity/APIfaultSTOP. GateнеобещаетfitRSSбезопасность,allstopgatesremain. Executioncode/exact4fitapprovalещёнеприняты.

EligibleincumbentнаFINALschema: existing008Logloss50/6000еслиblockrejected, accepted009Logloss50/6000еслиretained;никакогоincumbentrefit. PrimarymaxexternalfullYNDCG средиincumbent+feasiblecompletednewcheckpoints,общийRecallguard. Stabletie-setscore≥globalmax−1e−12,thenfewertrees/smallerdepth/incumbentifotherwiseequal/configID. NonefeasibleSTOP/no refill. Winnerpipeline6000or26000задаётТОЧНЫЕодинаковыеtrainQ/C/Y/weights/features/settings/trees длявсех016I/Rarms; pipeline/populationselectionнеприписываетсяintelligence.12newcheckpointlooks+priorincumbent/009/007historyявны. Proposed60actualCPUmin019includesgate/prep/failures/oracles/scoring,неwall×threads/невыдуманныйостаток6CPUh.

[Workingreadablereport](progress-report.md) отражаеттекущиеacceptedresults; финальныйtask1outcomeещёоткрыт. [Rounds011/012](research-lab/index.md) сохранены. Main016automaticGENERATION/selectiontypedAST+correctcalculation, неDAGspeedpromise;005ужеsharedplan. OptionalcomputeexperimentonlysameAST/optimizerON/fullcommonsinkvs005insideexisting2CPUh. Никакихнеизмеренныхhuman-hours/победынаднамереннонаивнымSQL.


### TLAB-018 phase1 code accepted; full009 proposal critic — 15 октября 2026

[Portable readonly workflow](experiments/verification-workflow.md) принят по [targeted independent review](backlog-reviews/tlab018-independent-rereview.md), original [changes requested](backlog-reviews/tlab018-independent-review.md) не переписан. Exact14 mandatory shard map выводится независимо от approval; fresh resealing missing Q/C не получает pass.29scoped synthetic tests и independent18cases закрывают lineage/report-ID/cleanup. Никаких actual018 rescans/fits/acceptance writes. Phase1 НЕ завершает clean-clone regeneration; pre-acceptance verification, explicit externally bound acceptance-writing и real-resource plan остаются отдельным pending scope.

[Full009 proposal critic](backlog-reviews/tlab009-full-export-proposal-review.md) принимает daily/exhaustive направление с обязательными уточнениями: expected unique-item domain из acceptedQ/C, comparison EVERY physical keyed row и fullR/provenance, exact14+accepted10093pins, combined1800actualCPU-second gate.26000-population cardinality diagnostic не отменяет6000-ablation criterion. Root drafting only; code/fault review и exact execution approval ещё впереди.

[Round013](research-lab/round-013.md) уточняет typed key/cardinality/multiplicity obligations через пять counterexamples; это исследовательский проект synthetic adapter test, не новый бюджет или исполнение. HYP-111/112 reserved refinements existing HYP-002/046, не самостоятельные подтверждённые quality hypotheses.


### Full009 initial code review: changes requested — 15 октября 2026

[Independent original review](backlog-reviews/tlab009-full-export-code-review.md) наf60b639f freeze воспроизвёл4P1: physical schema/key/count consumer gate, primary exception при secondary counter/write failures, terminalCPU accounting, narrowed self-declared100inputscope. P2: daily cardinality не равна phase union.24ownsyntheticcases и11author tests не являются realfull acceptance. Frozen100/actual93source record unaffected; Root исправляет только новый full module. Actual full execution/approval ещё отсутствуют.

[Mixedloader/one-ablation proposal](backlog-reviews/model-data-and-ablation-proposal.md) принят только как направление новых files: execute once/fetch_df_chunk32, preallocated56numeric+3categorical, exactold008base6000arrayequivalence, actual6000cardinality4096, ONELogloss50claim и fixedretention. До realfeatures/Pool/fit — independently accepted fullsource outputs и новый code/fit approval. Никаких dependencies/uv/pinned008 изменений. Уточнение: fetch_df_chunk32 даёт максимум65536rows/chunk; bounded resource failure→base/no replacement отличается от integrity/semantic/API failure→STOP.

Future independent fulloracle transport проверен только tiny:280rows/5040values+allprovenance/fullR passed, единственная испорченная broadcastcopy rejected.0actualsource/modelreads/fits; author tiny proposal transport mocked явно. Initial harnessimportpath failure исправлен до тестов. Эти tinychecks не объявляются actualfullsourceacceptance.

Rounds014–016 сохраняют дальнейшие obligations: actual2026 seal before reserved-target access отдельно от simulated2019 availability; expectedgrain-domain cover перед everyphysicalrow broadcast; conservative semantic aliases и floating/quantization nonaliases до common2I2Rpool. HYP113–118 reserved refinements, не новые quality claims/бюджеты. [Critic011/013](research-lab/round-011-013-review.md) принят с explicitpopulation/context appendix. Main016generation/selection остаётся центральным, новые заметки не откладывают ready execution.


### Full009 producer/observer code accepted — 15 октября 2026

[Final code acceptance](backlog-reviews/tlab009-full-export-final-rereview.md) закрыла original4P1/P2 и failed-receipt boundary: initialsummaryfinalizing, finalreceiptcomplete, knownfailedmarker отвергается до input/source work. Actualfull exports/qualityfits ещё отсутствуют. Current published code59565643f58a…77afa, [AST-identical EOF correction](backlog-reviews/tlab009-full-publication-note.md); frozen100 unchanged; nextexactexternalproducerapproval→boundedexport→900CPUindependentsourceaudit→externalseal→reviewedmixedloader/ONEablation.

Independent sourceobserver [nullableBIGINT P1](backlog-reviews/tlab009-full-source-oracle-review.md) воспроизведён как correctIDfalse-reject/wrongroundedIDfalse-accept; explicittypedSeriesBEFOREDataFrame fixed it. [12typed cases](backlog-reviews/tlab009-full-source-oracle-rereview.md) и [marker/setup gate](backlog-reviews/tlab009-full-source-oracle-marker-rereview.md) приняты. Currentpublicsourceoracle supports exactmetadata009 context, не объявляет complete018manual18regeneration или actualfullsourceproof. Originald76/typed577 versions preserved.

Rounds017–019 сохраняют proposerinformation/typedfuzzing/cluster-bootstrap limits; no extra fits/materializedcolumns/selectionlooks authorized. Root model_data остаётся отдельным uncommitted review scope.


### Full009 data + chunkedloader/single-ablation code accepted — 15 октября 2026

[Actualsource verdict](backlog-reviews/tlab009-full-source-verification.md):all6134207pairs×18metadata values/provenance/full1858481R checked; producer+oracle159.4891actualCPU seconds,176pin seal. Existing [008control114pin seal](backlog-reviews/tlab008-control-seal.md) reusesacceptedmodels/scores/proof,0refits/0newmetrics.

[Chunkedloader review](backlog-reviews/tlab-model-data-independent-review.md) принят26independentcases+10author tests. [Single-ablation initialP1](backlog-reviews/tlab-metadata-ablation-independent-review.md) terminaldecision былисправленlocalAblationAudit без измененияsharedfull5956. [TargetedACCEPT](backlog-reviews/tlab-metadata-ablation-independent-rereview.md) закрываетresourcebase41/APISTOP/primarypreservation/globalnoretry. Current35733…/89766… codeaccepted; exactactual192pinproposalce0e… requiresONEexternalfitapproval, noactualfit/matricesyet. Parentcostledger обязателен.


### Permanent research020–025 and exact009 single-fit gate — 15 октября 2026

Six [new literature rounds](research-lab/index.md) preserve source/capability/lifecycle/cost/causal/typedoperator boundaries. [Critic017–022](research-lab/round-017-022-review.md) confirms mechanisms while clarifying nonoverlapping CPU accounting and actual availability-clock provenance. No new data/fit quota granted by these notes.

[Exact009 execution gate](backlog-reviews/tlab009-single-fit-approval.md) issued for unchanged192pins/runce0e…; Root started ONEattempt with fresh-parent CPU/tail receipt. Actual outputs remain pending independent model/score/fullY/bootstrap audit. No independent heavy source/model job overlaps measured fitting.

[019 worker seam](backlog-reviews/strong-worker-design.md) is changes-requested: canonical tie law remains fewer trees→smaller depth→incumbent→configID within globalmax−1e−12. TERM/grace/KILL/reap/no descendants, live-child CPU and partial-checkpoint eligibility must be fixed prospectively before execution. Fresh processes solve monotonic peakRSS fallback; they do not create extra CPU, fits or looks.


### TLAB009 actual model ACCEPT, whole metadata block REJECT — 15 октября 2026

[Independent output verdict](backlog-reviews/tlab009-model-output-verification.md): exactlyONE50treefit/runce0e67…, all817149scores/fourfullYestimands/200pairedbootstrap/modelparams/noCTR/keys/claim/pins verified. NDCG.40041404049<.41444755082; Recall.54500978474<.57921330724floor. **Frozenfinalmanualfeature schema for019/016 = base41; eligibleincumbent existing008Logloss50/6000.** Sourcecheckedmetadataoutputs remain archive, no replacement/refit/retune. TLAB009done as falsifiedblockhypothesis, not successfulqualitygain.

Producer101.181955CPU seconds; failedobserver3.335586+corrected4.585806=7.921392CPU charged, no reset/no new nativefits. Staticcritic terminal/scope/metadata blindspots closed by external checks and successfulparentexit; weightproofscope limited to acceptedcode+expectedpopulation, notCBMweightrecovery.

[Round026](research-lab/round-026.md)+[critic](research-lab/round-026-review.md) offer8current005legal bundles with exact3physicalclosure; candidatebuyerdistinct168/categorymissing/coverage72aliases excluded. [Round027](research-lab/round-027.md) separates prospective fixedslotfairness from equalrealisedCPU and measuredstrategyquality. These do not grant newoperators/fits;019workercontract/exactexecution and016namedpool/seed/schema freeze still required.


### Reviewed019direction and016symbolicpreflight — 15 октября 2026

[019v2freezeappendix](backlog-reviews/strong-worker-design-freeze.md) согласован: ONEouter3600wall includes verifier/finalseal, reserve360wall+20cleanup;3600actualCPU includes300verification and liveparent/cleanup60 reserve, nofreshverifierbudget. Parent1GiB+sequentialchild7GiB=8GiBjob; TERM5/KILL/reap5/no childsubprocesses. Latefailedarmwholeineligible/all3lookslotsconsumed;016inherits trainediterations and scoringprefix separately. Rootowns newstrong_baseline script/tests/config/doc; noactualgate/fits untilindependentcode/exactplanapproval.

Coorowns newfeature_programs script/tests/automation-pool/doc: schema+3humanboundedparameterizedfamilies→8generatedregistries, legality/semanticBalias/3physicalclosure, fixedI2/R2random2026 givesL02/L06/L01/L05. EighttinytestsPASS.646s, ≤25fixtureinputrows/onlyselected12newcols,0realdata/Pool/fits. Independentcode reviewpending; no execution approval. [Research028–030+critic](research-lab/round-028-030-review.md) preserve generation claims and exacthandgold; [031Taobaoschema](research-lab/round-031.md) doesnotgrantdatasetdownload/license/qualityclaim.

[009203pinseal receipt](backlog-reviews/tlab009-model-acceptance-seal.md) fixesbase41/008incumbent, originalproofsimmutable. Moremanualfeatures are not addedaftermetadatarejection; priority019then016comparison remains.


### TLAB016 symbolicgenerator ACCEPT — 15 октября 2026

[Independent code review](backlog-reviews/tlab016-programs-code-review.md) accepts immutableafaefd6b…script/config/tests.8authorPASS and21ownPASS/180independentnewscalarchecks(60literal),≤25inputrows/selected12newcols/0realdata/Pool/fits. Schema/templates genuinely instantiateprogramdefinitions; humanbindings remain explicit. FixedI L02/L06 +seededR L01/L05, all4unique/11cores+autoBOOLmask12physical; names/order/schema/digests frozen.

Implementationdoesnotprovideactualsourceapproval/durableglobalclaim/final019settings. Futureloader must projectB41first+each3cols (rawSQL interleavesnewcolumns); exactactualbase/source/protocol/QCY/trainediterations/scoringprefix/population/settings/clocks and shared016budget bind externally. [Publication note](backlog-reviews/tlab016-programs-publication-note.md) archives originaldocstatus; codebytesunchanged. Nextcoorscope: selected-union12featurecollection and independent sourceoracle only, neverall8/24materialisation; realcalc/fits waitseparatereview.

[Research032](research-lab/round-032.md)/[033](research-lab/round-033.md) add no rescue fits or speedclaim. Root019newmodule remains independent owner; semantic/source failuresSTOP, no fallbackbyfreshhash.


### Исследования и границы следующих этапов — 15 октября 2026

Сохранены [раунды034–041](research-lab/index.md), включая независимый план проверки новых12 признаков, переносимость на другие наборы и различия между идентичностью значений, provenance и оплаченной попыткой обучения. [Дизайн коллекции016](backlog-reviews/tlab016-feature-collection-design.md) принят [ревью дизайна](backlog-reviews/tlab016-feature-collection-design-review.md) только как направление реализации. Реального расчёта016 и новых сравнений пока нет.

Предлагаемая политика отложенной проверки: confirmation25 и final26+ только сообщают качество тех же заранее замороженных моделей и программ; они не выбирают победителя и не вызывают refit. Желательно запечатать все held-out predictions до открытия query-level targets. Использование сырых событий25 как strict-past истории26 отличается от открытия targets/metrics25. Это пока проект нового календарного контракта, а не изменение текущих конфигураций или уже выполненная проверка. [Раунд038](research-lab/round-038.md) и [039](research-lab/round-039.md) фиксируют необходимые границы.

После независимого ревью019 до реальных запусков уточнена ресурсная политика: индивидуальные лимиты обязательны для успешных workers. Известный resource-failure может честно показать выход за индивидуальный порог, остаётся неуспешной оплаченной попыткой; общий CPU, wall и консервативный job RSS обязательны всегда. Неизвестный расход или превышение общего бюджета ведёт к STOP. Это не разрешение скрывать расход или пополнять четыре попытки.


### TLAB019 code accepted; execution pending — 15 октября 2026

[Исходное ревью](backlog-reviews/tlab019-code-review.md) выявило три существенные ошибки и один типовой дефект. [Повторное ревью](backlog-reviews/tlab019-code-rereview.md) закрыло их; [узкая проверка launch evidence](backlog-reviews/tlab019-launch-code-rereview.md) приняла финальные10dffd… bytes. Controller3758 принят [отдельным synthetic review](backlog-reviews/tlab019-controller-rereview.md) и опубликован в scripts/run_strong_control.py.40 scoped и303 общих теста прошли. Реальных019 запусков пока нет: до них нужны финальный независимый аудитор результатов и точные external approvals. [Publication evidence](backlog-reviews/tlab019-code-publication.md).

[Fresh-clone audit](backlog-reviews/tlab-fresh-clone-reproducibility-audit.md) показывает отдельный незавершённый seam018: проверка существующих sealed artifacts не заменяет bootstrap source approvals и независимый rerun с новой identity. Эту работу нельзя маскировать README командой, ожидающей ignored approval JSON из текущей сессии. Она остаётся задачей воспроизводимости до итогового deliverable.


### TLAB019 independent observer ready — 15 октября 2026

[Независимое ревью аудитора](backlog-reviews/tlab019-oracle-independent-review.md) приняло public entry tests/oracles/strong_output_audit.py03b9c22…ccaab. Исправлены observer-only effective-LR mismatch и чтение context не из того же проверенного snapshot; producer10dffd/controller3758 не менялись. Семь независимых literal/context проверок и отдельный nativeAPI check на старом008CBM прошли,0fits/0realQY. Это готовность проверять будущий результат, а не принятие ещё не выполненного019.

Следующий шаг: один same-process controller, оплачивающий imports/planning/wait/run/oracle внутри исходных CPU/wall; сначала actual proposal, затем точный external approval. Во время измеренного019 нет конкурирующих тяжёлых016 расчётов. [Разбор силы доказательства](backlog-reviews/tlab-small-support-evidence-review.md) ограничивает будущую интерпретацию: двенадцать зависимых checkpoint looks не равны двенадцати независимым попыткам, bootstrap не устраняет selection bias.


### TLAB019: zero-fit восстановление observer — 15 октября 2026

Исходный producer завершил четыре заранее заданных fits и12 checkpoint looks на26000train queries. Его исходный контроллер сохранил failed status: независимый observer отказал из-за локального platform subprocess. Это не принятие победителя. [Диагноз](backlog-reviews/tlab019-observer-failure-diagnosis.md) воспроизведён без данных/моделей. [Независимое ревью](backlog-reviews/tlab019-zero-fit-recovery-code-review.md) приняло отдельные owner и observer, сохраняющие старые outputs и failed history, исходный абсолютный deadline и общий бюджет.

[Recovery contract](experiments/strong-recovery.md) разрешает после точного external policy ровно один zero-fit replay, без producer calls, новых fits/looks или held-out targets. На новый owner+observer остаётся218.520940actualCPU seconds из исходных300verification seconds; прежний отказ и консервативная диагностическая стоимость оплачены. CODE ACCEPT не равен actual output ACCEPT; следующая обязательная стадия — один replay и полная проверка его exit/tail receipts.


### TLAB019 done, actual control sealed — 15 октября 2026

[Фактическое независимое output review](backlog-reviews/tlab019-strong-output-verification.md) принято. Четыре fits/12checkpoint looks на26000train queries завершены; все12savedpredictions перепроверены без refit. SelectedB: Logloss/depth6/L2=30,300trained iterations иscoring prefix300, исходныйB41. Selection NDCG@20=0.4586107284411232/Recall@20=0.5851272015655578. Local control acceptance scope reviewed_strong_baseline_control связывает304exact fingerprints, включая неизменённую failed history и успешную отдельную recovery attestation; прежний failed invocation не переименован в success.

Весь019консервативно1666.94actualCPU seconds; cumulativeverification179.999060/300, originalwall deadline соблюдён. Следующий ready slice —016 selected12source-only export и независимый exhaustive source oracle, затем четыре matched fits по prospectively frozen all4+B selector. Никакие confirmation/final query-level targets иmetrics не открыты длявыбора. Full unit suite выполняетroot отдельно; тяжёлый016sourcejob ждёт его завершения.


### TLAB016 ready: selected12 source and prospective selector

Producerb3e05d85 and independent source oracle319327b8 are code-accepted. They calculate only the frozen11cores+1mask selected union, preserve all old45physical columns and accepted Q/C, and open no Y relation. The oracle checks every selected value against independent raw-event formulas; physical shape/range checks alone do not authorize formula acceptance. Source900CPU/1200wall plus oracle900CPU/1200wall are paid prefixes of the same7200actualCPU study; their successful full-lifetime receipts must be sealed before any four model fits.

[All4+B selection design](experiments/feature-program-selection.md) and [independent scope/tie critique](backlog-reviews/tlab016-selector-design-review.md) are frozen prospectively. Recall feasibility is inclusive B−.002, then global NDCG band1e−12, fewer added physical columns, lexical candidate ID. Primary W−B may be0 when B wins. Random winner supports mixed typed automation, not superiority of rule-guided allocation. Executable selector/model runner still requires independent review and exact fit approval.


### Additive data boundaries accepted — 15 октября 2026

[Inference narrow review](backlog-reviews/tlab-labelblind-inference-code-rereview.md) accepts the Q/F-only loader after fixing an optional-group alias that silently reassociated valid candidates. All queries including emptyC remain; no Y API or fake targets are returned. Source/calendar/feature provenance must still be externally accepted, and all model columns must be caller-frozen. This is physical boundary readiness, not permission to open heldout data or score models.

[Program-model loader review](backlog-reviews/tlab-program-model-data-independent-review.md) accepts base41+one approved3-column arm transport, preserving original Q/C/Y, exactBIGINT keys/order and base arrays. Accepted source/arm/model contexts remain required. No native fit or real matrix was created in these reviews. Full current regression351tests passed with ResourceWarning treated as error; no duplicate suite was run for publication.


### Source016 failed; explicit recovery under independent review — 15 октября 2026

The single claimed source process exported all15daily Q/F partitions, then failed terminal every_export_physical_consistency: its inspector materialized the full57-column phase under2GB/spill0. The original producer/report/sourceclaim and outputs remain immutable; source/model acceptance016 is HOLD. External failed lifetime155.77wall/107.41CPU seconds/RSS3627925504bytes is preserved, conservative paid prefix107.42. No source regeneration, source refill or fit is permitted by this failure.

The prospective recovery uses the one UNUSED source oracle to prove disjoint complete accepted Q/C partitions, all45old fields and every selected12 raw-event scalar from immutable exports. New owner+oracle together≤792CPU/1044freshactivewall, preserving original source900/1200 and unusedoracle900/1200 and7200shared study; admin repair elapsed is separately disclosed and a missing old absolute monotonic deadline is never invented. Code/policy and actual proof require independent acceptance; there is no approved recovery execution yet. Research046–064 is published, adding source/interpretation refinements rather than new production scope.


### Strong-control consumer accepted

[Independent consumer review](backlog-reviews/tlab-strong-control-independent-review.md) accepts scripts/strong_control.py4b469d0e,8author+4independent targeted cases. It reconstructs the304-pin source/output/recovery/failed-history closure and selected spec without subprocess-producing environment snapshot. The metadata preflight deliberately stops at the first streaming hash sentinel: this is code acceptance, not a claim that current304large inputs were fully replayed again. Source/model execution approval remains external; no fit budget is granted.


### Source016 recovered-proof code accepted, actual oracle still gated

[Combined independent review](backlog-reviews/tlab016-source-recovery-code-rereview.md) accepts admission47cc4495/oraclea3a485a0/owner9100471d. Initial missing-helper-codepin, preclaim paid-preparation and late-failed-marker findings are preserved with fixes. Verified bounded source snapshots execute before helper calls, original executable pins are mandatory, and the sole unused oracle claim precedes paid export hashing. The independent32-total-input integration proves policy/claim/context/physical/source flow without regeneration; it is not a107-input or real OS-lifetime proof.

Actual recovered-source acceptance remains HOLD until one exact external policy, one unused oracle process, every6134207pair×12value comparison, old45/Q/C completeness and successful external owner+child lifetime. No future original absolute source clock is invented; oldfailed107.42upper plus freshowner+oracle792CPU/1044activewall preserves the conservative existing limits. Source/model fits remain forbidden by code acceptance alone.

### Source016 accepted through the sole unused oracle — 15 октября 2026

[Фактическое независимое source review](backlog-reviews/tlab016-recovered-source-verification.md) принято: все15дневных partitions,30 000Q/6 134 207пар,73 610 484значений выбранных12столбцов проверены без расхождений; прежние45поля и полный принятый Q/C-домен сохранены. Source не регенерировался, Y/model fit не открывались. Исходный producer остаётся failed; отдельная успешная recovery attestation связывает166точных fingerprints и не переименовывает старую историю.

Весь source плюс sole recovery oracle консервативно177.72actualCPU seconds и199.34active-computation wall seconds; administrative repair отдельно, missing original absolute deadline не реконструируется. [Агрегаты и предел source-доказательства](backlog-reviews/tlab016-recovered-source-aggregate.json). Следующий gate: read-only recovered-source consumer и reviewed016 model runner/independent output observer; затем ровно четыре заранее разрешённых matched fits с accepted019 population26000,300trained/scoring300 и frozen all4+B selector. Сам source acceptance новых fit-разрешений не выдаёт. Confirmation/final query-level targets иmetrics по-прежнему закрыты для выбора.


### Recovered-source consumer accepted

[Independent review](backlog-reviews/tlab-recovered-source-independent-review.md) accepts the additive read-only consumer of the exact166-pin recovered-source attestation. Eleven author and four independent mutation/late-failure/path tests passed. Actual bounded receipts reached a deliberate stop before paid107-input rederivation; this is no second source oracle or full166-stream replay claim. Future model planning must pay all hashes, pin delegates and include the returned source acceptance reference itself. Source modules/attestation/proofs and original failed history remain immutable.


### Prospective heldout lock and scientific claims — design only

[Whole-decision/driver proposal](backlog-reviews/heldout-driver-lock-design.md) and [independent adversarial critic](backlog-reviews/heldout-contract-adversarial-review.md) specify reporting-only25 and unchanged26–31, a new prospective calendar version, all B/W predictions sealed before any reserved query-Y unlock, legal raw25 history for26, sampled user-day membership, fullY/censoring and separate clock/budget gates. No heldout data/model/target execution or new fit permission follows from these notes. Exact positive simulated compute allowance, budgets, code/seal reviews remain pending.

[Scientific scope review](backlog-reviews/tlab016-fixed-procedure-scientific-claims-review.md) clarifies that selected-union12 serves four B+3 arms; finalW adds0 or3 physical columns. A valid negative result may support an automation demonstration, without claiming quality/speed/strategy superiority or task completion before model/reproduction/report evidence. No new HYP, task or search budget is added.


### Model016 review v1: changes requested before any fits

[Full independent runner review](backlog-reviews/tlab016-model-runner-code-review-v1.md) reproduced two terminal-integrity blockers and unknown fit/look-count precision on missing child receipts. Twenty-one author tests passed; three unique independent synthetic regressions failed as expected against frozen61e977. Root is batching repairs; no actual016owner claim or native fit has run. The accepted019model native-parameter API probe passed without Q/Y/predictions or a quality look. Original failure evidence is retained; code acceptance awaits targeted repaired-freeze review and separate independent observer review.


### Model016 repaired code accepted; actual four-fit gate pending

[Runner v2](backlog-reviews/tlab016-model-runner-code-rereview-v2.md) and [independent zero-fit observer](backlog-reviews/tlab016-model-observer-independent-rereview.md) passed scoped independent review. [Evidence](backlog-reviews/tlab016-model-v2-review-evidence.md) preserves the original failures, narrow test-only fixture repair and full 440-test green integration check. Exactly four fixed-procedure fits and one observer remain gated by a fresh measured owner and approval of its actual complete proposal; no actual016 fit or heldout access has occurred. Remote publication remains pending direct destination consent; local commits preserve the work.


### Pure reserved-period contract accepted; source/inference still gated

The additive [contract](experiments/heldout-contract.md) passed [independent repaired-code review](backlog-reviews/heldout-contract-independent-rereview.md):16 author plus4 independent cases, including original duplicate-day and calendar-maturity faults. It checks only authenticated snapshots,25 reporting-only/26–31 frozen calendar,12-hour positive simulated decision allowance, B/W closure and all-day prediction-before-target intent. It opens no actual data or model and provides no heldout execution approval. New source/inference/evaluator owners, budgets, semantic proof, native replay and exit-tail seals remain mandatory.


### New-date source core and public score-replay prefix accepted

[Source-only core](experiments/heldout-source.md) passed14 author plus3 independent SQL/no-IO cases; it produces only B45+chosen0/3 and neverY. [P0A supplied-score replay](experiments/fresh-clone-reproduction.md) passed22 author plus2 unchanged terminal-fault regressions and a relocated12-row public CLI smoke without private data/artifacts. [Independent evidence](backlog-reviews/heldout-source-and-replay-independent-evidence.md) preserves original failures and the492-test green integration suite. These are separate limited code/mechanics acceptances: actual heldout source/inference/targets remain gated, while private package replay and fresh-source bootstrap remain distinct work.


### Original016 four-fit execution and external model acceptance

[Actual model verification](backlog-reviews/tlab016-feature-program-model-verification.md) accepts all4originalfits/4looks and the sole zero-fit observer after successful explicit reaping, exact authority/output pins, model/matrix/ranking/fullY replay and original-clock/resource checks. R2/L05 is frozen W on development; NDCG0.4647028774 versus B0.4586107284, descriptive postselection interval crosses0. Source+owner+observer upper1694.75CPU; conservative external admission upper10 gives1704.75<7200. No refits/refills or source regeneration. Original source failure remains failed. Whole decision and all25–31 predictions must still precede any reserved queryY; no heldout result exists. Prior007/008/009feedback and019selection are part of design history, not erased by the four016-look cap.


### Guarded historical438 B/W consumer accepted

The additive [choice consumer](experiments/feature-program-control.md) passed10 author plus3 independent synthetic cases; [review/evidence](backlog-reviews/model-choice-consumer-independent-review.md) retains a bounded actual metadata gate stopped before large paid input hashes. It returns B/W-only bindings after future caller-paid full438 authentication, not a fresh-source/bootstrap seal. Actual W=R2 and model/source authority remain immutable. New heldout owners must pin this consumer/code and authenticate new-date Q/C/F, all-prediction replay and target intent; no actual heldout operation follows from this code acceptance.
