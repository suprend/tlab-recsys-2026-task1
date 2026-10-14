# Round016: три разных смысла feature equivalence

15 октября2026. **Research/proposal;0fits/raw scans/LLM API calls/test executions/dataset downloads, repo/frozen files не менялись.** Прочитаны currentmanual18/retrieval/loader и rounds[003](round-003.md)/[009](round-009.md)/[012](round-012.md)/[015](round-015.md). HYP117/118 reserved: refinement002/closure, без нового quality mechanism. Практический вывод: dedup до common legal pool должен быть консервативным semantic rule, а не обещанием treeboosting invariance.

## Три отношения, которые нельзя смешивать

**Exact semantic equality:** две программы дают одинаковые typed values/NULL/masks на всех допустимых source/context inputs. Одинаковые названия не нужны; совпадение100Qvalues недостаточно. Именно это оправдывает automatic alias/frozen-B rejection.

**Information equivalence:** известное обратимое преобразование позволяет восстановить исходное значение в идеальной арифметике, сохраняя missing state. `log1p(n)` дляn≥0 иpositiveconstant×n не равныn, хотя не добавляют информации кn. При конечной точности обратимость может исчезнуть. Deterministic ratio от двух Bcolumns не добавляет информации к их jointvector, но меняет представление взаимодействия.

**Identical trained behavior:** требует дополнительных условий quantization/splits/weights/seed/feature-order и inference values. Ни два первых отношения, ни один одинаковый seed сами по себе этого не гарантируют. Даже duplicate column может изменить выбор между tied candidate splits; semantic dedup — policy поиска, не theorem о неизменности любого retraining.

## Что подтверждают первичные источники

CatBoost сначала делит numerical values на buckets; Uniform использует absolute range, Median — распределение объектов. Поэтому нельзя приписывать всем режимам одинаковую invariance кmonotone transformations. [Quantization docs](https://catboost.ai/docs/en/concepts/quantization).

В tagged1.2.10 source values/borders имеютfloat type; `RegularBorder` и другие пути используют midpoint соседних values с rounding guard. **Hand-computed counterexample, не fit:** training values0и8, один midpoint border4; послеlog1p midpoint равенln3. Unseen count3 находится ниже4, ноln4 вышеln3. Training ordering одинаков, inference partition различается. Это условный пример данного border construction, не измеренный trained-model outcome. [Tagged binarization source](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/library/cpp/grid_creator/binarization.cpp).

Numerical NaN имеет отдельную обработку Forbidden/Min/Max; defaultMin гарантирует рассмотрение split, отделяющего missing от остальных. Замена NaN→0 меняет contract; log/ratio, создающий NaN из допустимого числа, тоже меняет missingness. [Missing-value docs](https://catboost.ai/docs/en/concepts/algorithm-missing-values-processing).

ExploreKit включает normalized/discretized features в generation, затем отдельный ranking/evaluation. OpenFE применяет unary/binary transformations и trained pruning/attribution. Наличие этих операций в primary papers не доказывает их полезности в нашем CatBoost или бесплатности selector. Их выбор по validation не является semantic canonicalization. [ExploreKit](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf), [OpenFE](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf).

## Actual frozen-B duplicates и важные nonaliases

[Candidate code](../../scripts/candidate_pilot.py) присоединяет **полный** `pilot_popularity` после popular/recent union. Поэтому `count_distinct(user_id,purchase,item,168h)` совпадает с `popularity_distinct_users` на acceptedC при одинаковых source/window/endpoints/null policies, включая recent-only items. Counts без покупателей дают0 в обоих путях. Top200ограничивает membership/rank, не этот score. Новый alias убрать до poolfreeze, вместе с уже имеющимися manual18 definitions.

`popular_source_rank` не alias count: ties дополнительно используют productID, rank имеет source-dependentNULL. `retrieval_last_event_age_seconds` тоже не manualpair-view/purchase recency: retrieval объединяетview/cart/purchase, ограничен7d/top20recent и может бытьNULL дляpopular-only пары с более старой историей. Manualrecency использует конкретный event иполныйobservedprefix. [Loader](../../scripts/train_baselines.py), [registry](../../configs/features/manual-18.json).

Loader переводит numeric values вfloat32, NULL→NaN. Например, соседние integers2²⁴ и2²⁴+1 коллидируют при обычномfloat32rounding. Такой collision — model-input fact на данном dtype, не доказательство semantic equality двух AST. Nonlinear transform доcast может изменить collisions; cast→transform иtransform→cast нельзя переставлять автоматически.

## Предлагаемые conservative rules

Canonical signature хранит grain/keys/sourcecontext, event/operator/operands, точноеwindow/endpoints, multiplicity, metadata/availability/null policy, unit/version и encoding stage. Имена нормализуются; literal aliases времени приводятся к одному exactunit. Удаляются одинаковые signatures и проверенные rewrites кfrozenB, включая retrieval, supports/masks/coverage. Rewrite имеет явные domain preconditions; future suffix/sample correlation не заменяют доказательство.

`count_distinct(group_key)` может означатьpresence indicator, а неcount: не переписывать вrawcount. `n/n=1` неверно приn=0/NULL; `(n/d)*d=n` не безопасно приd=0, missingness иrounding. Float associativity/cancellation не assumed. Ratio сохраняет denominator/support/missing closure: `(0,0)` даётNULL, `(0,5)` —known0. Удалятьsupport потому, что «ratio уже всё содержит», нельзя.

Constant scaling или`count/W` приfixedpositiveW — information-equivalent representation, не exactalias. Нормировка наcoverage(t,W) илиobservedage имеет переменный denominator; она может менять порядок между anchors и неопределена при0. First-seenage не exposure. Threshold`n>k` необратим и теряет magnitude; он не semanticduplicate, даже если дерево иногда может реализовать такой split.

Two-window difference/count ratio выражаютjoint interaction. При одинаковых rawgrain/endpoints разностьN7d−N24h математически равнаsource-restricted bandcount `[t−7d,t−24h)`; это rewrite только с точными count/unit/overflow guarantees. RatioN7d/N24h требуетzero support. Joint information уже может находиться вB, но ограниченная глубина иquantization не обещают одинаковой обучаемости.

Всеlog/scaling/threshold/arbitrarytwo-window arithmetic пока **unsupported005**, а не новые legal016operators. Если будущий whitelist заранее исключает pure unary transforms какrepresentation-only, это общая policy дляI/R, неsemanticduplicate proof и не postmetric pruning.

## Common pool и один prospective zero-fit gate

До2I+2R заморозить полныйB signature map, rewrite rules/preconditions, общийlegal bundle pool и hash. Затем closure даёт ровно3новыеphysicalcolumns наarm; masks/supports/coverage учитываются. Invalid/duplicate proposal расходуетattempt, replacement запрещён. Empirical equality/correlation/importance послеmetrics только описываются; нельзя уменьшить random pool или подобрать новое преобразование после плохогоscore.

Один proposed synthetic test, **не выполнен/не разрешён автоматически**:≤24typed rows надвухanchors сcounts0/1/3/8,2²⁴/2²⁴+1,NULL; ratios0/0и0/5; coverage1и½; разныеevent recencies. Проверить expected canonical classes иnonaliases, NULL/mask preservation, pre/postfloat32 stage иhandfixed midpoint counterexample выше. Ни одного model fit или targetmetric. Existingprepared quantization API допустим только после отдельного review/разрешения, без installs и нового proof fit.

Evidence различает universal rewrite, context-bound alias, observed encoded collision инепроверенное trained behavior. Cost gate входит вexistinggrammar/oracle ledger; caps не растут. Это делает generation/dedup проверяемыми и одинаковыми дляI/R, не заявляя speedup, quality gain или CatBoost invariance.
