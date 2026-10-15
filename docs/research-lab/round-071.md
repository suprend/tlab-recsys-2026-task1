# Round071 — distinct AST не означает distinct information

15 октября2026. Узкий refinement [044](round-044.md), [064](round-064.md) и scientific-claims review: не новая гипотеза или pruning algorithm. Прочитаны accepted [feature_programs](../../scripts/feature_programs.py)/[pool contract](../../configs/features/automation-pool.json), primary papers/docs; меняющиеся runner/oracle, actual data/models/outputs не читались. SQL/tests/fits/jobs отсутствуют. L02/L06/L01/L05,12physical columns/4fits/no-refill и selector неизменны.

**Вывод:** текущий symbolic dedup обосновывает отсутствие объявленных structural aliases относительно B/retrieval, но не гарантирует новый information signal. Empirical equality/constant values не отменяют consumed opportunities и не разрешают заменить frozen bundle. Это уже предусмотренное ограничение; дополнительный HYP/task не нужен.

## Три разных основания

Semantic alias — равенство функций для всех допустимых event bags при одном grain/action/window/projection/context/NULL contract. Переименование программы не меняет `_signature`; совпавшая подпись отбрасывается. Retrieval alias `item/distinct purchase users/168h` объявлен отдельно. Это ограниченная canonicalization, не theorem prover всех эквивалентных выражений: разные signatures могут оказаться связанными алгебраически или давать одинаковые values.

Empirical equality — совпадение на конкретном keyed domain/source prefix/representation. Два разных окна могут совпасть из-за отсутствия старых событий. Такое наблюдение не доказывает равенства на других dates/users или fuller history. Даже equality после float32 conversion слабее equality исходных BIGINT counts; masks, conditional NULL, coverage и support проверяются отдельно. Information-equivalence не обещает идентичное trained-model поведение при иной схеме/порядке признаков.

Outcome-based selection — выбор по fitted utility/validation metrics. Он использует labels/feedback и оплачивает fits/looks, даже если AST generation первоначально label-free. «Удалили redundant columns» не скрывает дополнительный supervised search.

[DFS2015](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) конструирует relational compositions, не доказывает наш universal alias class. [ExploreKit2016](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf), Algorithm1, сочетает learned ranking и classifier-based wrapper evaluation; это иной уровень evidence. [OpenFE2023](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf), §3.2, удаляет совпадающие по values кандидаты и использует supervised FeatureBoost/pruning. Его dedup — не доказательство temporal semantic equality, а incremental training не является0fit.

[Featuretools1.31.0 remove_single_value_features](https://docs.featuretools.com/en/stable/generated/featuretools.selection.remove_single_value_features.html) работает по matrix values. Default `count_nan_as_value=False` позволяет удалить колонку с единственным nonmissing value и остальными missing. Для нашего `[0,NULL]` это существенная граница:0 может означать известный пустой conditional cohort, NULL — неизвестную категорию. Missing companion различает состояния; нельзя объявить весь typed feature family константой, глядя только на non-NULL values. [Correlated-feature pruning](https://docs.featuretools.com/en/stable/generated/featuretools.selection.remove_highly_correlated_features.html) также основан на matrix correlation и предположении о порядке/сложности DFS columns, не на universal equivalence.

## Буквальный future fixture≤32rows, безY

Только спецификация. Source S=T−10d, anchor T, declared full coverage. Начальные events: U1→A/view вT−2h; две exact duplicate U1→A/view вT−1h; U2→P/purchase вT−1h; U3→M/view вT−1h. КатегорияA/P известная K; уM NULL. Q:U1/T,U2/T. C:дляU1 A, дляU2 A/M. Добавленная шестая строка — U1→B/view вT−100h, категорияK. Всего6events+2Q+3C=11rows.

До шестой строки user-view COUNT24=COUNT168=3, DISTINCT24=DISTINCT168=1 дляU1. После неё COUNT24=3/COUNT168=4, DISTINCT24=1/DISTINCT168=2. Source/context/C неизменны; более раннее событие законно, полнота окна не подменяется возрастом пользователя. Latest view recency остаётся3600s: count и recency не получают alias от одного совпадения.

Общий аналитический72vs168 witness такой же: recent-only history≤72h даёт3/3; допустимый eventT−100h даёт3/4. Но72h **rejected by frozen016**:005 validator допускает1–744h, тогда как accepted016 contract требует[24,168] и exactbindings. Этот arithmetic witness не добавляет программу в legal pool. Если сама source начинается позжеT−72h, совпадение count windows на данном anchor можно вывести из совпадающего clipped domain; это context-conditional equality, не universal alias и не равенство coverage columns.

ДляU2 conditional view count категорииA=0, candidateM category unknown→NULL с missing=true; noncategory view count0 остаётся известным. Constant-pruning, игнорирующий missing, обязан провалить этот expected table. Duplicate removal меняет raw count3→2, но distinct остаётся1; globalT peers/future suffix не меняют прошлые значения. Никаких вычислений этих fixtures сейчас не выполнялось.

## Current claim и future pruning obligations

Честная цепочка:8symbolic bundles→4predeclared slots→union12 для четырёх B+3 models→selector B либо один B+3. Это не «лучшие12 из24 по usefulness» и не обучение B+12. Static dedup означает distinct declared recipes, а не гарантированное увеличение информации/качества. Если selected column эмпирически constant/equal, она сохраняет frozen physical place; no extra replacement, seed, fit или postmetric pruning.

Будущая label-blind pruning policy потребовала бы **до нового allocation/targets** закрепить: exact train-only domain/source/context; этап сравнения raw/type-aware vs encoded values; NULL/NaN/support/mask rules; constant/equality критерий и deterministic representative; единицу whole-bundle/physical closure; общий pool/random law и collision/no-refill; стоимость всех screening columns, cache/readback/failures. Смотреть values всех24 потенциальных columns — materialization/screening24, не бесплатная операция внутри cap12. Pruning только allocated subset тоже не даёт права заполнить освободившийся slot другой программой без заранее объявленного нового протокола.

Train-constant rejection может быть полезным engineering rule для конкретного learner, но не доказательством universal feature uselessness; observations на selection inputs также являются отдельным transductive access, даже безY, и не должны молча выдаваться за train-only policy. Любой outcome feedback дополнительно входит в consumed-look history. Для нынешнего исследования достаточно отчётной оговорки и сохранения ledger, а не запуска нового pruning. **No-add outcome:** existing semantic/correctness/selection gates остаются; ни speedup, ни learned intelligence, ни missingness-safe empirical pruning здесь не реализованы/не измерены.
