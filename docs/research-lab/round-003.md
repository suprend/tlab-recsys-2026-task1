# Research lab, round 003: бюджет по выходной схеме и исполнимая grammar search

15 октября 2026. **Предложение для review, без измеренного quality gain.** Прочитаны canonical [backlog](../backlog.md), rounds [001](round-001.md)/[002](round-002.md), оба critic review и prospective strong-control proposal. Read-only проверены `scripts/manual_features.py` и `configs/features/manual-18.json`; raw, Git, dependencies, модели и API не затрагивались. Единственный созданный файл — эта записка в временном каталоге. Отсутствие корневого AGENTS.md в targetrepo явно отмечено координатору; approval flow не запускался.

## Что добавил повторный разбор первоисточников

1. **Kanter, Veeramachaneni, 2015, Deep Feature Synthesis: Towards Automating Data Science Endeavors.** Композиция relational traversal и агрегатов полезна как представление программы. Filter Objects задают categorical filters и временные интервалы, сериализуемые в SQL. Отсюда не следует, что произвольный фильтр уже реализован нашим compiler. Практическое следствие — grammar должна перечислять реально поддержанные signatures, а более глубокие HYP-011/045 оставить отдельными extensions. [Авторский PDF, §§II–III](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf).

2. **Katz, Shin, Song, 2016, ExploreKit: Automatic Feature Generation and Selection.** Три стадии — генерация, ranking кандидатов, дорогая classifier evaluation. Unary/binary/groupby операции ограничены; generated features внутри одной генерации повторно не комбинируются. Meta-ranker требует labels, полученных из feature trials прежних datasets. Для малого пилота берём ограниченное пространство, но не запускаем обучение такого ranker: оно создаст скрытый search budget. [Авторский PDF, §IV](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf).

3. **Zhang et al., 2023, OpenFE: Automated Feature Generation with Expert-level Performance.** В §5.3 гиперпараметры downstream LightGBM настраиваются на base features; методы получают одинаковое число новых features. Algorithms 3–4 разделяют featurewise pruning и совместную attribution. Их equality-based dedup относится к значениям на рассмотренных данных: равенство не доказывает идентичность программ при другом anchor. Здесь замораживаем B до extensions и различаем semantic equivalence и наблюдаемую коллинеарность. FeatureBoost не объявляется бесплатным selector. [Официальный PDF, §§3.2/5.3](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf), [авторы/издание](https://proceedings.mlr.press/v202/zhang23ay.html).

4. **Featuretools, официальная документация 1.31.0.** Primitive описывает input/output types; aggregation и transform имеют разные grains. `primitive_options` ограничивает допустимые columns/dataframes, причём include overrides ignore. Поэтому отрицательный список сам по себе слабее явного whitelist. `include_cutoff_time=False` задаёт нужные `[lower,t)` границы; это документационный факт, не проверка установленной библиотеки. Библиотеку не устанавливаем и accepted005 не заменяем. [Типы](https://docs.featuretools.com/en/stable/getting_started/primitives.html), [options](https://featuretools.alteryx.com/en/stable/guides/specifying_primitive_options.html), [время](https://docs.featuretools.com/en/stable/getting_started/handling_time.html).

## Фактическая граница accepted005

Проверенный source SHA256: `e2558299783a04aba34432fe72c0e7e16e6ddbcbfd074bdf18e8b09eae224103`; manual18: `44587dd2106ab9bbfc9ec1faa0c496703969ca401894eea73f84a93700b41d9c`. Это fingerprint чтения, не новый acceptance artifact.

Validator принимает шесть grains: user/item/pair/user_category/item_category/category; events view/cart/purchase; `count`, exact `count_distinct(user_id|product_id)`, `recency_seconds` по полному observed history, и два вида matching-count share. Count windows — integer 1…744 часов; **grammar намеренно ограничивается 24/72/168**. Recency с окном 24h не поддержана. Ratio допускает только user_category/user либо item_category/category с одинаковыми event/window. Arbitrary arithmetic, mean/max вложенных popularity и HYP-045 не представлены этим JSON vocabulary.

Compiler автоматически создаёт missing flags для recency/ratio/category-grain и coverage для каждого нового числового окна. Поэтому бюджет — **фактическая разность физических выходных schemas относительно pinned005**, включая dependencies/flags/coverage, даже если часть не передаётся модели. Например:

| Extension относительно manual18 | Новые physical columns |
|---|---:|
| pair_cart_24h + item_cart_24h + item_purchase_168h | 3 |
| pair_cart observed recency + missing flag + item_cart_24h | 3 |
| pair_cart_72h + item_cart_72h + source_coverage_72h | 3 |
| user_category_cart_share_168h, с existing user_cart denominator | минимум 4: numerator, его flag, ratio, его flag |

Последний вариант не помещается в three-column arm. Удалять flags или объявлять dependency бесплатной нельзя. Известный пустой count равен нулю; неизвестный category key, отсутствующая recency и zero-denominator ratio остаются missing. Event-attached categories не переклассифицируются текущей карточкой.

## Refinement HYP-002: closure-aware proposal, одинаковый пул

**Статус: needs-pilot; новых IDs/квоты нет.** Это уточнение TLAB-016/HYP-002, а не отдельная predictive hypothesis. HYP-011/045 сохраняются альтернативами; HYP-046 уже покрывает shared execution/equivalence. HYP-091/092 оставляем свободными: отдельного нового механизма здесь недостаточно.

Grammar сначала schema-only перечисляет конечный whitelist extension bundles с **ровно тремя новыми columns после dependency closure**. Canonical identity включает grain, event, operator, operand identity, окно/границы, category/missingness policy, unit и version. Имена не входят. Manual duplicates удаляются до proposal одинаково для всех arms. `count_distinct` по grouping key — indicator существования, а не count; без доказательства не переписывать. Эмпирическое равенство на 100 queries только диагностируется, не становится глобальным rewrite. Никаких labels/future summaries proposer не видит.

**Минимальный опыт:** два heuristic proposals I1/I2 и два uniform-seeded random R1/R2 из **того же полного bundle pool**. Каждое arm делает ровно **одну попытку предложить целый bundle**, затем максимум один fit `B+bundle`; seeds 1601/1602 для I, 1603/1604 для R prospectively фиксируются. Это четыре равные proposal attempts, не скрытый best-of-many. Invalid/duplicate bundle расходует попытку, replacement запрещён; коллизия arms сохраняется и уменьшает число уникальных fits, без refill.

Предлагаемая эвристика воспроизводима: вес bundle `1 + число новых core-программ с event∈{cart,purchase} + число новых core-программ grain∈{pair,item}`; I выбирает пропорционально весу, R равномерно. Это слабый domain prior, не обученный интеллект. Cost/type gates общие; ему не предоставляется эксклюзивный operator. Все bundles со стоимостью трёх columns остаются в обоих распределениях. Новый ratio объективно отсутствует в обоих пулах из-за closure, не из-за предпочтений эвристики.

**Контргипотезы:** boosting уже извлекает доступный сигнал; cart/purchase prior выбирает разреженные features; выигрыш принадлежит случайному seed; cheap-schema preference исключает полезный дорогой оператор. Inputs — pinned Q/C/Y, accepted registry/source lineage, external006 evaluator и frozen tuned B. До исполнения нужен review точного grammar/pool hash, weights, seeds, model-input manifest и selection rule. OneBM/DFS terminology не делает неподдержанный AST исполнимым.

## Бюджет, chronology, accept/reject

Общий остаток016 **≤12 новых columns / ≤4 fits / ≤2 CPUh**, не на arm/HYP; суммарный user+system всех процессов, wall cap120min, 2 threads/RSS8GiB. Предлагаем распределение CPU: 20min schema/oracle/fixtures, 30min materialization, 60min четыре fits, 10min scoring/report; перерасход не создаёт новый budget. Ошибки/repair/confirmation оплачиваются. Cost gate на label-independent 100 queries не доказывает full-source cost; при прогнозе превышения остановить fits.

Контроль — **сильно настроенный frozen B** с фиксированными population, parameters, trees и train seed для всех arms. Initial008 ровно два fixed50-tree fits остаётся smoke. Предложенные strong-control fourfits/max300/checkpoints50/150/300 ещё не одобрены; все 12 selection looks должны учитываться в отдельном prospective tuning ledger. Новый B внутри016 уменьшает остаток, не становится бесплатным.

Selection22–23 уже имеет доступные labels; начало confirmation24Oct00 не оставляет доказанного compute gap. Предложение — сохранить selection, закрыть query-day25Oct00–26Oct00 и оставить24-й для decision/compute, либо сузить selection до22-го. **Это не выполненная смена manifest.** До раскрытия confirmation нужны approved calendar, actual017 maturity/availability checks и timestamped immutable decision artifact; более позднее получение labels учитывается отдельно. Final26+ закрыт, refit/retuning после confirmation нет.

Selection ранжирует все четыре arms по full-Y conditional query-macro NDCG@20; tie — меньше измеренный CPU, затем AST hash. Выбирается один winner, включая random; сравнение best-of-two I против best-of-two R остаётся screening, две seeds не доказывают superiority стратегии. Primary confirmation — только frozen winner против frozen B. Предлагаемый accept: ΔNDCG≥0,002, paired user-cluster95% CI lower>0, ΔRecall≥−0,002, exact Q/C/Y coverage и budget. All-query/user-macro, day/repeat/novel/missing-history slices и cost обязательны как диагностика. Semantic mismatch — reject; неуверенный CI — inconclusive; исчерпанный ресурс — deferred. Нет выигрыша у B — не заявлять выполнение quality alternative, хотя корректная автоматизация остаётся самостоятельным engineering result.

## Второй schema и сознательные отказы

В пределах тех же20min предложен independent synthetic mapping: visitor/sku/occurred_at/action→canonical fields, дополнительный unsupported `refund`, NULL category, conflicting latest timestamp, lower/cutoff peers и future suffix. Сравнить mapped и canonical oracle values/missingness, exact candidate identity; unknown event нельзя молча превратить в purchase. Это refinement HYP-046 compatibility gate: проверяет adapter/automation, **не статистическую generalization**.

External data пока только [UCI Online Retail](https://archive.ics.uci.edu/dataset/352/online%2Bretail): CC BY4.0, 22,6MB XLSX,541909 invoice lines; CustomerID/StockCode/InvoiceDate, no view/cart/category taxonomy. Invoice-line count≠quantity≠invoice count; category primitives недоступны, Country не подстановка. Никаких downloads/training.

Отвергнуты: 3 intelligent arms против1 random; три core-features с бесплатными flags; второй selector/proxy вне четырёх fits; подмена frozenB на B+S; dedup по совпадению только selection values; открытие confirmation следующему literature round; установка OpenFE/Featuretools ради имитации automation. Следующий конкретный результат — reviewed grammar/pool/closure manifest и bounded semantic pilot, затем единственное зарегистрированное comparison при выполненных upstream gates.


## Coordinator critic appendix — 15 октября 2026

[Independentcritic](round-003-review.md) подтвердил synthetic005actualschema deltas3/3/3/4 иexact11Ckeys. DedupfullfrozenBвключает004popularity_distinct_users, не только18core. Onebundleattempt/arm, exactpool/PRNG/order/law/coreASTweights/modelinputs freeze; collisions неrefill. [Raw nextproposal+canonicalamendment](../backlog-reviews/strong-control-automation-proposal.md) сохраняет отвергнутые3I+1R alternatives какprovenance. 009block/pricing design передstrongtuning обязателен; neitherdesign acceptance norcritic расширяютexecutionbudget/calendar.
