# Research round 009: typed grammar до дорогого расчёта

Статус: research/planning, без fits, real scans и изменений репозитория. Прочитаны rounds002/003 с coordinator amendments, текущие [compiler005](../../scripts/manual_features.py) и [manual18 registry](../../configs/features/manual-18.json). Центральный результат для task1 — конкретная граница автоматически перечисляемых программ и проверяемого расчёта. Нового predictive mechanism здесь нет: HYP103/104 зарезервированы; документ уточняет002/045/046.

## Что дают первичные источники

**Featuretools DFS:** primitives задают input/output types; aggregation сворачивает связанные строки в scalar, transform сохраняет grain таблицы. `features_only=True` позволяет получить определения до feature matrix. Это хороший образец разделения enumeration и calculation, но numeric type сам по себе не запрещает averaging ID или future metadata. [Официальные primitives](https://docs.featuretools.com/en/stable/getting_started/primitives.html). Документация отдельно описывает secondary time index для колонок, известных позже создания строки, и `[lower,t)` при `include_cutoff_time=False`. Следовательно, event timestamp и availability timestamp нельзя считать взаимозаменяемыми по одному имени поля. [Handling time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html).

**OneBM:** различает scalar, multiset, sequence/time-series после relational traversal; требует явного prediction cutoff и канонизирует эквивалентные пути. Его truncation больших joins до недавних строк сознательно теряет точность. Для нашего exact compiler пригодны typed collection и shared prefixes; незаявленный history cap не является корректной оптимизацией count/distinct. [Авторский текст, III–IV](https://arxiv.org/html/1706.00327v1).

**ExploreKit** разделяет generation, learned candidate ranking и classifier evaluation; meta-ranker обучается на trials прежних datasets. **OpenFE** обучает FeatureBoost на residual targets и выполняет successive pruning/attribution. Ни feature importance, ни «дешёвый» learned selector не являются schema-only enumeration или бесплатным доказательством корректности. [ExploreKit, IV](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf), [OpenFE, Algorithms2–4](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf).

**RelBench** задаёт primary/foreign-key relations и задачи с entity ID, seed time, labels; temporal split не снимает ответственности дизайнера за leakage. Это основание явно хранить ключи и prediction anchor в adapter, а не переносить опубликованные neural results на fixed-C feature search. [Первичная работа, §2](https://cs.stanford.edu/people/jure/pubs/relbench-neurips24.pdf).

## Доказуемый контракт AST

Предлагаемый узел хранит signature `(grain,keys,value_type,unit,multiplicity,event,window,cutoff,availability,null_policy,metadata_policy,version)` и свободные переменные `{u,i,t}`. Правило вывода типа должно проверять каждый operand и выдавать либо typed scalar, либо конкретную причину отказа. Это относительная гарантия при истинных schema/availability declarations, не доказательство отсутствия любых ошибок или полезности признака.

1. **Тип и единица.** IDs остаются номинальными, хотя физически BIGINT. Row-count, distinct-user count и distinct-item count имеют разные units. Share требует совместимых event/window и доказанного subset numerator⊆denominator; purchase/view ratio не становится probability только потому, что оба поля числовые.
2. **Grain и multiplicity.** После groupby результат уникален по declared keys. Присоединение к `(query_id,product_id)` допустимо many-to-one; две сырые one-to-many ветви без предварительной агрегации дают fanout и неверные counts. Raw event multiset сохраняет повторения; distinct требует explicit projected key. Нельзя складывать distinct counts пересекающихся partitions без доказательства disjointness.
3. **Время и availability.** Все history leaves имеют `<t`, finite windows — `[t−W,t)`, observed recency — весь наблюдаемый prefix. Latest metadata означает полный global timestamp bucket всех пользователей. Snapshot/encoder version и фактическая доступность не позже anchor — отдельные условия. REES46 использует принятый event-time replay contract; неизвестный ingestion lag нельзя выдать за доказанную online availability.
4. **NULL и coverage.** Known empty count=0, unknown category-conditioned count=NULL; отсутствующая recency=NULL; denominator0→NULL. Missing flags и coverage входят в closure. Source coverage не равно observed age. Typed adapter без views не должен подменять unsupported view operation нулём.

## Что реально выражает005

Validator поддерживает шесть grains, события view/cart/purchase, count, exact distinct по user_id/product_id, observed recency и два matching-count shares. Integer windows1…744h допустимы compiler; proposed enumeration ограничена24/72/168h. Произвольные arithmetic, category-code/brand/price, nested mean/max и HYP045 отсутствуют. Таблица использует сокращённую запись, не новый JSON/API.

| AST | Решение до evaluation |
|---|---|
| `count(pair,cart,24h)` | Legal005; strict-past raw rows, новый scalar |
| `distinct(item,user_id,purchase,168h)` | Legal005; exact buyers; duplicate frozen retrieval score требует dedup |
| `recency(pair,cart,observed)` | Legal005; scalar+missing flag |
| `count(user_category,cart,168h)/count(user,cart,168h)` | Legal matching share; supports/flags делают closure минимум4 новых columns при existing denominator |
| `recency(pair,cart,24h)` | Unsupported005: recency допускает только observed |
| `user_purchase_24h/user_view_168h` | Rejected share signature: events/windows не совпадают |
| `mean(product_id)`; `mean(popularity(history_items))` | Первое неверно по nominal unit; второе пока unsupported nested AST |
| `count(events JOIN C)` до groupby; final-month category lookup | Rejected physical plan: fanout; либо future-state policy |

`distinct(user,user_id,view,24h)` compiler допускает, но это индикатор наличия matching events. Это **не ошибка типов** и не доказанно бесполезный признак. Исключение такого шаблона — заранее объявленный общий lint/whitelist choice; нельзя тайно удалить его только у random arm. Query-constant признаки также не отбрасываются как бесполезные: boosting может использовать interactions.

Выполнено маленькое stdlib schema-only перечисление signatures без импортов producer и без DB: при6grains×3events×3windows получены54count,108distinct,18observed-recency и18matching-share templates, всего198. Число включает вырожденные шаблоны и baseline duplicates; это не198полезных features, не число exact3column bundles и не свидетельство правильности calculated values.

## Enumeration, closure и стоимость

Порядок: конечный whitelist→type/policy checks→canonical AST dedup против **полного frozenB**, включая retrieval features→dependency/mask/coverage closure→ровно3новые physical columns→общий bundle pool/manifest. Стоимость оценивается по required grains, observed-prefix scans, distinct keys, metadata joins и intermediate cardinality. Без реальных scans это консервативный инженерный proxy, не измеренная стоимость и не usefulness score.

Пример legal three-column bundle: pair_cart72h+item_cart72h+новая source_coverage72h. Иной bundle: cart-pair observed recency+его missing flag+item_cart24h. Нельзя считать только cores, прятать supports или удалять masks ради cap. Все model inputs и physical closure фиксируются до выбора; одна попытка целого bundle на arm, invalid/duplicate/collision не даёт free replacement. Предложенные2I+2R/12columns/4fits/2CPUh остаются единственным общим016ledger, не разрешением исполнения этого раунда.

Compiler уже группирует программы по grain/anchor, вычисляет несколько FILTER aggregates совместно и использует distinct user/item sets через SEMI JOIN. Это существующая physical reuse, а не новый измеренный speedup. В cache identity обязательны source/version, t, window/endpoints, event, multiplicity, conditional key и NULL/metadata policy. Category denominator должен охватывать полную category population, даже когда выходные строки ограничены C; фильтр до candidate items меняет величину.

## Минимальное non-fit calculation evidence

Следующий возможный шаг — tiny synthetic fixed Q/C, одинаковые manifest/AST/physical outputs для двух планов: independent per-expression SQL/Python oracle против compiler/shared plan. Предлагается≤100events/8Q/32C,0fits, внутри прежнего schema/oracle ledger. В этом раунде такой расчёт **не выполнен**; есть только schema enumeration выше.

Независимые contracts: перестановка peers; событие ровноlower включено, ровноt исключено; future suffix сохраняет past F при неизменном context; повтор события увеличивает raw count, но не distinct; expiry последней копии уменьшает distinct; category move не переписывает исторический numerator; mixed-NULL latest bucket не backoff; zero denominator/unknown key сохраняют NULL+mask. Candidate reorder не меняет keyed values; schema rename с явным обратным mapping сохраняет результат, unsupported action отклоняется.

Сравниваются exact keys/schema/integers/NULL/flags, floats с заранее заданным tolerance. Дефектный fanout/shared-cache policy обязан падать на fixture. Для будущего cost comparison одинаковы setup/output boundaries и cache policy, чередуются AB/BA, оплачиваются warmup/failures; при неоднозначном timing принимается только semantic equality. Такой результат подтверждает автоматический расчёт и reuse correctness на проверенном contract, без model-quality/generalization claim. Дальнейшая feature selection остаётся отдельным cost-matched опытом против frozen tuned manualB.
