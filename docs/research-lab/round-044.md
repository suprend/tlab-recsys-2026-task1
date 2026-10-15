# Round044 — три уровня pruning и отдельный physical plan

**Primary-source refinement, не изменение frozen016.** Прочитаны принятый compiler005, опубликованный016 design и первичные работы; WIP019/016collection, данные, модели и jobs не читались/не запускались. Нынешние12physical columns/4fits не расширяются. HYP137/138 уточняются; отдельный novelty ID для уже реализованного semantic dedup не нужен. Главное различие: доказанная семантическая избыточность, совпадение на конкретных values и outcome-based usefulness — разные основания удаления.

## Что реально делают источники

[DFS2015](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) строит relational features последовательными функциями по entities/relations; синтез и последующее autotuning разделены. Из этого не следует universal proof equivalence или наша measured экономия.

[ExploreKit2016](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf) использует meta-features и classifier, обученный на ранее разобранных datasets, для ranking кандидатов, затем wrapper evaluation. Labels, offline training и проверка downstream error входят в механизм; это не label-free AST canonicalization.

[OpenFE2023](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) оценивает incremental usefulness через FeatureBoost и двухэтапное pruning. Incremental training поверх base predictions не является0-fit проверкой. Current016 не реализует learned ranker, FeatureBoost или общий search этих статей; заимствуется только явное разделение generation/calculation/evaluation.

## Таблица допустимых доказательств

| Уровень | Возможное основание | Что действительно известно | Цена и граница |
|---|---|---|---|
| До values/Y | Exact AST+grain/action/window/projection/context/NULL identity | Равенство для всех допустимых inputs данного contract | Symbolic checks; нельзя игнорировать masks/coverage/fullB |
| Source values безY | Constant/all-missing/equal columns на закреплённой training relation | Empirical equality в этой relation | Source calculation/hash/validation оплачиваются; не universal equivalence |
| Train outcomes | Target-aware ranking, mutual information, fitted proposer | Использованы training labels и обученная selection heuristic | Fit/screening CPU и dependencies учитываются; это не автоматически selection-date look |
| Selection outcomes | Выбор по validation score/labels/error | Дополнительный development feedback | Selection look/history и training cost; нельзя скрыть как preprocessing |

Последние две строки принципиально различны. Train-only supervised screening может быть законным, если заранее объявлен и доступен к decision cutoff, но не является бесплатным или label-blind. Использование selectionY либо selection metric создаёт дополнительный look. Сегодня ни одна такая новая процедура не разрешена, а frozen pool нельзя менять даже на основании «только target-free correlation» после allocation.

## Exact aliases и опасные подмены

Переименованный `count(pair,view,24h)` с тем же raw bag и temporal context — alias независимо от имени. Полный dedup должен включать B41, retrieval scores и автоматически emitted masks/coverage, а не только18core names. Current v1 item purchase distinct-users168h совпадает с retrieval buyer score и для recent-only candidates; это конкретное ранее принятое равенство, не догадка по слову popularity. Category missing flag может повторять существующий B flag лишь при одинаковой resolver/unknown semantics.

Но `count(user,view,24h)` не равен сумме только candidate-pair counts: пользователь мог смотреть товар внеC. `count(item,cart,24h)` не равен distinct cart users: два одинаковых cart rows дают2против1. DuckDB различает count rows, count non-NULL и DISTINCT; NULL в projected distinct не становится отдельной сущностью. [Aggregate semantics](https://duckdb.org/docs/current/sql/functions/aggregates).

Нулевая weekly count не доказывает missing observed recency: событие8дней назад даёт count7d=0, но конечную recency. Full-prefix last purchase и last-any-event retrieval age различаются по predicate. Recency mask не заменяется observed-history flag, если второй охватывает другие actions. Эти маленькие counterexamples запрещают pruning по «почти одинаковому смыслу».

Для category shares005 требует matching raw-count action/window и nested populations: user-category/user либо item-category/category. Даже ratio1на всех observed rows не является universal constant: новая category или zero denominator создаёт0/NULL; unknown conditional key добавляет missingness. Current validator не разрешает произвольный ratio(x,x); добавлять его ради algebraic simplifier не предлагается.

Constant0/all-NULL на training F можно точно констатировать только после source computation и exact keys/types/null-stage сравнения. Such column может стать ненулевой позже. Корреляция1не доказывает equality; monotone/invertible transformations сохраняют информацию при математических assumptions, но меняют float32 collisions, quantization и missing branches. Поэтому correlation pruning — отдельная heuristic, способная удалить rare complementary сигнал, а не semantic proof. Просмотр heldout feature distribution ради нового выбора также изменил бы frozen information boundary, даже безY.

## Shared aggregate planning не pruning качества

Actual [005 _grain_sql](../../scripts/manual_features.py) собирает expressions одного grain/anchor в GROUP BY; recency использует full source prefix, прочие predicates фильтруют свои окна. Selected pair24 counts могут использовать уже существующий full-prefix pair batch; новый item/user168 primitive не обязан добавлять scan window. Однако DISTINCT требует отдельного state по projected keys/action/window; masks требуют physical export. Sharing scan не делает эти costs нулевыми.

[DuckDB WITH](https://duckdb.org/docs/current/sql/query_syntax/with) описывает materialization и inlining heuristics. Наличие CTE не является доказательством единственного scan, shared state или speedup. И наоборот, одинаковая physical scan boundary не делает разные aggregates semantic aliases. Current unchanged005 уже batched: сравнение с заведомо наивными отдельными scans не доказывает выигрыш относительно нашего baseline.

## Одна минимальная будущая гипотеза

Refinement, не новый feature family: **contract-aware closure dedup удаляет только exact aliases и уменьшает число запрашиваемых redundant physical expressions без изменения keyed values/NULL/schema выбранных nonaliases**. Counter: canonicalizer теряет context, маску или полезное distinct/window различие.

Будущий≤32literal-row,0-fit proof заранее включает renamed B/retrieval aliases и перечисленные nonalias witnesses. Accept: все declared aliases отвергнуты до calculation, все witnesses сохранены, independent literal/list values и required physical closure неизменны. Reject: любой false merge, потерянный mask/support, changed context или new operator. Counters: proposed ASTs, exact aliases, legal bundles, physical delta, aggregate expressions/states, actual validation CPU/wall/RSS при отдельно разрешённом выполнении. Меньше expressions не объявляется measured runtime gain. Это не materialization всего pool, не замена current allocation и не новые fits/looks; нынешний016 pipeline продолжает работать по своему frozen scope.
