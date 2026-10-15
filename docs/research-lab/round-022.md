# Research lab, round022: point-in-time строки и lifecycle обученных компонентов

15 октября 2026. **Research/design-only**, без fits, scans, datasets, реализации или новых budgets. Прочитаны [review features05–08](../features/review-05-08.md), исходные05/06, [round014](round-014.md), [017](round-017.md) и актуальные pipeline contracts. Current TLAB использует strict-past counts/metadata; learned layers/embeddings здесь не реализованы и этим документом не разрешаются. Root full009/ablation review и frozen файлы остаются неизменными. HYP129/130 — reserved refinements temporal contract, не новые operators.

## Пять первичных оснований

[Feast, current point-in-time documentation](https://docs.feast.dev/getting-started/concepts/point-in-time-joins) описывает backward temporal lookup/TTL относительно каждой entity row. Существенная граница: default ограничивает event timestamp, а created timestamp используется для deduplication последней correction; поздний backfill может попасть в старую entity row. Документированный opt-in `filter_by_created_timestamp=True` добавляет `created_timestamp≤entity_timestamp`, исключает NULL-created rows; unsupported offline stores должны отклонять flag. Это current docs, не проверка установленной версии и не предложение добавить Feast. Даже этот predicate отличается от нашего отдельно объявляемого strict knowledge `<t`.

[Featuretools, Handling Time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html) связывает time index с моментом, когда информация стала известна, допускает per-row cutoff и secondary time index для поздно известных полей. Пример flight delays показывает field-level availability. Cutoff filtering не восстанавливает отсутствующие версии metadata и не проверяет происхождение fitted parameters; включение границы также нужно согласовать отдельно с `[t−W,t)`, а не копировать пример по умолчанию.

[RelBench, §2](https://cs.stanford.edu/people/jure/pubs/relbench-neurips24.pdf) использует temporal splits/neighbor sampling и прямо оставляет предотвращение leakage ответственностью designer. [Ji et al.](https://arxiv.org/abs/2010.11060) показывают ошибку обучения на global-future interactions относительно test query. Ни paper не разрешает whole-file embedding для более ранних predictions. [scikit-learn, common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage) требует fit preprocessing на train, transform для test и separation до fit; это обычный model pipeline contract, но не доказательство того, что scaler был доступен у каждого исторического training anchor.

## Три разных временных утверждения

**Source features:** для query вt raw primitives используют допустимые строки `[S,t)`, metadata — весь последний global past bucket, historical category counts — category каждого события. Если известен ingestion clock, применяют отдельный available-time predicate. Иначе offline event-time assumption явно сохраняется. Одинаковые peers не упорядочиваются через rowid. Source coverage и missingness не заменяются возрастом модели.

**Training procedure:** модель, обученная после cutoffF на mature labels training queries, закономерно использует labels из будущего относительно собственных anchors. Это supervised training, а не автоматическая утечка. AST/hyperparameters также могут быть выбраны после train cutoff или selection: заново рассчитанные числовые primitives старых training rows остаются strict-past по этим anchors. Однако AST не объявляется существовавшим тогда, а выбор по selection остаётся retrospective development с полной consumed-look history.

**Fitted feature state:** scaler, vocabulary/IDF, embedding, cluster centres или learned prior сами имеют fit population/cutoff/availability. Их применение к историческим rows требует отдельного смыслового типа. Whole-train scaler, обученный без test и применённый к train/test после готовности, совместим с обычным offline model pipeline. Его transformed training values не являются записью того, что система могла выдать в старомt. Для embeddings, использующих future edges относительно training row, нельзя просто сослаться на scaler analogy: explicit row-data `<t` contract включает происхождение representation. Current005/018 такую альтернативу не поддерживают.

## Learned layers: ownership и snapshot

ПустьF — fit-data cutoff, E — завершение fit, A — доступность frozen artifact: `F≤fit_start< E≤A`. Для prediction вt требуется `A≤t`; для event-time ownership события вs модель и assignment inputs должны быть допустимы кs. Нельзя моделью, готовой вA, назначить owner событиям `s<A` и назвать назначения event-time historical state. В прежнем reviewτ означает готовый warmup artifact; еслиτ только cutoffF, старт counters необходимо сдвинуть кA.

Для frozen owner counters со стартомA хранить `layer_coverage_W=min(W,max(0,t−A))`, truncated flag, version и фактические gaps. Это верхняя календарная длина возможного learned покрытия, не гарантия отсутствия пропусков. Raw observed prefix может быть длиннее. При refresh нельзя склеить cluster7 версии1 и cluster7 версии2: номера не удостоверяют одну семантику.

Альтернатива — `reclassified_snapshot_at_t(version=v)`: доступной модельюv пересчитать допустимую историю доt либо current-membership перегруппировать её. Такой признак может быть корректен для downstream prediction послеA при всех inputs as-of t, но имеет иной смысл, поддержку и стоимость. Он не получает event-time ownership задним числом. Выбор snapshot для старых training anchors `t<A` не проходит strict historical feature-state contract; отдельный retrospective transform protocol должен быть явно принят, не скрыт metadata timestamp.

## Минимальные portable types и контрпримеры

| Тип artifact/value | Обязательные поля |
|---|---|
| SourceAsOfValue | anchor, grain, source/adapter, event/available predicates, window, coverage, NULL policy |
| FittedState | fit population/labels/dependencies, cutoffF, fit_endE, availableA, version, OOV policy |
| EventOwnerCounter | owner version, assignment instant/input prefix, startA, expiry/multiplicity, learned coverage |
| ReclassifiedSnapshot | evaluation anchor, frozen state version, complete admissible history domain, regrouping policy |
| ModelTransform | train-only fitting scope, input feature identities/order/dtypes, served-afterA claim |
| ProposerDecision | AST/pool, train/selection inputs, consumed looks, decision availability, frozen downstream scope |

Предлагаемые synthetic witnesses, без исполнения: event20Oct/available24/query22 должен отсутствовать при strict knowledge policy; embedding fit21/available22 не может быть historical feature row10; owner model ready8Oct/query9Oct имеет максимум один день learned coverage, а не семь; version swap с переставленными centroid IDs не сохраняет старые counters; scaler train counts{0,100} может transform старый0 после fit, но не доказывает availability scaler у первого anchor. Наконец, выбор AST по22–23 selection не меняет raw cutoff строки10, зато запрещает назвать decision доступным22.

Cache identity связывает semantic type, anchor/source prefix, state/dependency versions, adapter, cutoff/availability, coverage и dtype/null rules; одинаковый model filename недостаточен. Supervised encoders дополнительно требуют declared own-label/cross-fitting policy; shuffled OOF не исправляет global-time violations автоматически.019→016 честно наследует retrospective selection и точный winning pipeline, а confirmation требует нового prospective decision lock.

Physical audit2026 seals artifacts до открытия reserved targets сейчас; simulated2019 availability проверяет допустимость replay, не физическое существование файла в2019. Positive decision compute gap и remaining budgets сохраняются. Предложенные types лишь уточняют проверяемые claims; новых operators, универсального разрешения leaky embeddings, mandatory эксперимента или fit allocation нет.
