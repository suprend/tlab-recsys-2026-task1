# Research lab, round024: source-faithful граница метода016

15 октября 2026. Consolidation [001](round-001.md)/[003](round-003.md)/[009](round-009.md)/[012 critic](round-012-review.md)/[017](round-017.md), actual [compiler005](../../scripts/manual_features.py) и prospective016. Прочитаны четыре первичные статьи; benchmarks/fits/tests/scans, установки, внешние LLM calls и изменения Root кода не выполнялись. Current full009 acceptance/ablation review — отдельная evidence line. HYP133/134 остаются reserved refinements002; новые методы, operators и бюджеты не объявлены реализованными.

## Компактная матрица происхождения идей

| Первичный метод и actual input/algorithm | Что016 заимствует концептуально | Что у нас не реализовано |
|---|---|---|
| [DFS, Kanter–Veeramachaneni2015, §§II–V](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf): связанные entity tables, unique keys, numeric/categorical/time/text; entity transforms, relational aggregates, direct features и композиция по depth | Programs по schema/grain; отделение definitions от вычисленных значений; зависимости между operations | Полный рекурсивный DFS vocabulary, Data Science Machine preprocessing/selection/model pathway и Gaussian-Copula tuning |
| [ExploreKit, Katz–Shin–Song2016, Algorithm1/§IV](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf): flat input-output rows; unary/binary/groupby candidates, cross-dataset learned ranking и greedy classifier evaluation | Разделение enumeration, proposal priority и оплачиваемой downstream оценки | Meta-features/ranker weights, meta-training, iterative per-candidate classifier evaluation и полный search |
| [OpenFE, Zhang et al.2023, Algorithms1–4](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf): tabular classification/regression features; FeatureBoost относительно base predictions, successive featurewise pruning и joint attribution | Явная добавочная польза относительно B; различие дешёвого proxy и итогового ranker evaluation | Residual/proxy models, repeated random-block pruning, learned attribution и библиотечный feature space |
| [AutoCross, авторский paper2019, §§4.2–4.4](https://arxiv.org/html/1904.12857v2): tabular categorical crosses, numeric discretization; beam search, field-wise LR и successive mini-batch training | Frozen search space, явный candidate evaluation cost, ограничение combinatorial growth | High-order categorical crosses/hash representation, multi-granularity discretization, LR tuning/probes и distributed search |

Это comparison of mechanisms, а не реализация четырёх baselines. Каждая строка относится к своему prediction/input grain; ни классификационная строка, ни relational entity автоматически не становятся нашим `(query,product)` с time-varying context.

## Уточнения, которые нельзя потерять при финальном описании

**DFS** в исходной статье генерирует признаки из relationships и typed fields; predictive modeling/tuning — отдельные части полного Data Science Machine. Авторы вручную преобразовали raw datasets в MySQL schema, а time intervals/categorical filters задавались дополнительно. Поэтому «вся task formulation выведена автоматически из сырого файла» неверно. Schema-guided calculation не означает automatic availability annotations. Здесь не переносится ни competition score, ни claim human-hours reduction. Современный Featuretools time API также нельзя приписывать всем гарантиям paper2015.

**ExploreKit** learned candidate ranker использует опыт прежних datasets, затем classifiers и labels оценивают предложенные features на current task. Flat groupby transformations не равны историческому per-anchor aggregate по глобальному cutoff. Meta-ranker не является schema-only правилом; pretrained вариант потребовал бы provenance/availability/inference cost, local adaptation — дополнительных оплачиваемых fits. Наш static intelligent proposer не должен называться воспроизведённым ExploreKit.

**OpenFE** не переобучает полный base model для каждой оценки, но FeatureBoost обучает дополнительный model относительно base predictions/targets. Алгоритмы pruning многократно запускают оценки, затем joint attribution учитывает взаимодействия. Его classification/regression split/proxy-loss не задаёт наши query weights, full-Y NDCG, maturity или temporal row-state. Исполнение даже маленького proxy надо отражать в ledger; random data blocks не становятся chronological folds из-за слова pruning.

**AutoCross** field-wise LR фиксирует old-feature weights и учит веса нового cross, после выбора обновляет solution LR; successive halving распределяет training blocks по candidates. Multi-granularity discretization тоже оценивается LR, preprocessing содержит tuning. Это label-aware optimization, не один бесплатный hash. Numeric bin и номинальный cross — иные operators/types; один hashed ID не доказывает exact injective representation и не заменяет объявленные missing/OOV/availability rules. Ни native CatBoost categorical handling, ни009 nominal columns не означают, что AutoCross operator уже добавлен в005.

## Actual vocabulary и честная prospective016 процедура

005 validator поддерживает шесть grains, view/cart/purchase, raw count, exact distinct по user/product, observed-prefix recency и два matching-count shares. Windows допустимы1–744h; конкретный common enumeration whitelist фиксируется отдельно. Generic arithmetic/log transforms, nested mean/max, native categorical cross/hash и temporal learned cluster state отсутствуют. Синтаксически допустимый primitive ещё должен пройти source capability, semantic-unit, as-of и physical closure checks.

Исследовательские198 templates009 — символические definitions до дедупликации, не198 полезных/вычисленных features или готовых legal bundles. Main016 требует generation/selection **и** correct calculation: объявленная программа выводит candidates из typed schema/vocabulary, canonicalizes exact aliases относительно полного frozen B, формирует common legal pool после support/mask/coverage closure и выбирает2 intelligent+2 seeded random bundles. Каждый bundle имеет ровно3 новые physical columns; один attempt/arm, без replacement invalid/duplicate/collision после новых metrics. Proposer inputs/PRNG/pool/order/AST фиксируются до evaluation.

Calculated outputs должны соответствовать независимым expected formulas и exact Q/C row domain, multiplicity, global peers, metadata NULL grains, coverage и dtype transport. Это external experimental protocol вокруг compiler, а не свойство названия библиотеки.019 задаёт exact frozen winning B population/settings; четыре downstream fits и ≤12 columns/≤2CPUh включают весь selection/preparation/oracle/failure cost. AST choice после train/selection сохраняет retrospective development status; исторические numeric counts всё равно strict-past. Full-Y comparator и закрытый confirmation lock не наследуются автоматически из статей.

## Conceptual witnesses против необоснованных claims

**Temporal guarantee из relational typing:** late product metadata меняет category старой query при final-table join, хотя PK/FK и count types корректны. Это свидетель против автоматической temporal гарантии, не утверждение, что DFS paper обещал её.

**ExploreKit как free proposal:** evaluation одного candidate через отдельный classifier плюс4 arm fits уже требует больше4 fits. Cross-dataset ranker не отменяет этот current-task stage. Переименование training в ranking не исправляет бюджет.

**OpenFE «без обучения»:** один FeatureBoost residual fit плюс4 final fits расходует пять; pruning больше candidates только увеличивает consumption. Это conceptual ledger arithmetic, не выполненная попытка.

**AutoCross как temporal-safe preprocessing:** bin thresholds по whole-month values меняют код ранней строки после добавления будущего extreme; даже неизменный hash этой discretized category не исправит fitted-state availability. Validation AUC successive-halving — дополнительные looks, не наш один frozen bundle.

Примеры не исполнялись и не дают budget grant. Optional DAG/speed experiment допустим только на том же AST, current005 optimizerON и полном common sink внутри existing ledger. Faster fixed-AST calculation само по себе не закрывает generation/selection; верные generated features не обещают speedup. Финальный допустимый claim — ограниченная автоматическая процедура породила проверяемые programs и показала измеренный offline contrast против strong B. Ни SOTA transfer, ни superior search strategy по двум seeds, ни экономия человеческих часов, ни универсальная temporal correctness не установлены.
