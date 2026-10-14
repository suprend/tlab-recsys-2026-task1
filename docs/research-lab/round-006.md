# Research lab, round 006: temporal snapshots без изменения смысла признаков

15 октября 2026. Practical literature round для009 и будущего typed compiler. Прочитаны metadata/price design и его independent review, [manual005 source](../../scripts/manual_features.py), uv.lock. Проверена текущая официальная DuckDB documentation: ветка1.5, lock закрепляет1.5.6. Ниже **предложенные физические планы**, не измеренное ускорение и не implementation approval. Raw/реальные queries не читались; код, Git, зависимости,005/017/008 artifacts не изменялись. Бюджет009 и один ablation fit не расширяются.

## Семантический узел — bucket, а не последняя строка

Для товара i и exact UTC anchor t сначала определить `τ_i=max(event_time)` среди `[S,t)`. Затем взять **все** строки `(i,τ_i)`, включая других пользователей, дубли и NULL. Для каждого поля x независимо: allNULL→missing; один известный value без NULL→clean; known+NULL либо несколько известных→ambiguous. Слово «ненулевой» означает NON-NULL, числовая цена0 остаётся clean-but-invalid. Older-clean backoff запрещён.

`arg_max(x,event_time)` не является таким оператором: DuckDB игнорирует строки с NULL аргументом/временем и функция зависит от порядка при ties. Она может вернуть старое известное значение. `arg_max_null` не игнорирует NULL аргумента, но всё равно выбирает одну строку, не проверяет весь tied bucket. `any_value` также не решает задачу. [Первичный aggregate API](https://duckdb.org/docs/current/sql/functions/aggregates).

Минимальный reducer bucket хранит `rows=count(*)`, `nonnull=count(x)`, `min(x)`, `max(x)`; при объявленном equality/collation clean означает `nonnull=rows AND min=max`, allNULL — `nonnull=0`. Альтернатива — exact distinct count плюс explicit NULL count. Ни один вариант не удаляет NULL до проверки. Category/brand/price/code могут иметь разные states; price ambiguity не уничтожает clean category. Исходные category005 flags/ID должны совпасть побитово либо по объявленному nullable equality.

## P0: один snapshot на exact anchor

Рекомендация для первого009 cost gate — прозрачный **max+rejoin**, близкий принятому005:

1. На source prefix `[S,t)` получить таблицу `M_t(product_id,last_ts)` группировкой всех пользователей/event types. Это один ключ на known-past product.
2. Соединить M_t с source по `(product_id,last_ts)`, проверить relevant price rows и свернуть bucket независимо по полям. Отфильтровывать NULL/invalid поля до выбора last_ts нельзя.
3. По `last_ts≥t−7d` определить active products, затем clean current category и valid latest price задают R. Candidate metadata берётся также для неактивных кандидатов, если future retrieval protocol их когда-нибудь допускает.
4. Один раз получить category sum/count, past code dictionary; присоединить результаты к **фиксированным** C по ключам. Выход — отдельный immutable addon, не переписанный F005.

Эквивалентность `exists event in[t−7d,t)` ↔ `last_past_ts≥lower` следует из определения maximum для того же event predicate. Это безопасная экономия для **presence/active-distinct-products**. Ею нельзя заменить raw event count, distinct users или view-count005: они имеют другую multiplicity. При будущем type-filtered active operator требуется maximum именно этого типа.

Existing005 уже группирует запросы по distinct anchor и вычисляет несколько выражений одного grain вместе; это подтверждено чтением source, не performance claim. Переиспользование глобального metadata/category state нужно между всеми users/C этого **же t**. Совпадение UTC calendar day недостаточно при разных intraday anchors; cache key содержит полный timestamp, source fingerprint, field/null policy, window/event predicate и AST version. Группировать по дню можно только как partition/export boundary.

## P1: предварительные bucket states + строгий ASOF

Для многих anchors можно отдельно предложить relation `B(product_id,bucket_ts,field_states…)`, unique по двум ключам. Все tied raw rows сворачиваются **до** temporal join; ambiguous/missing states сохраняются как полноценные записи. Затем логический поиск последнего bucket выражается `ASOF LEFT JOIN … ON product_id equality AND t>bucket_ts`. DuckDB поддерживает строгую inequality; `USING` для ASOF подразумевает `>=` и включит peers, поэтому здесь непригоден. Outer variant сохраняет строки без прошлого. [Официальная join specification](https://duckdb.org/docs/current/sql/query_syntax/from#as-of-joins), [ASOF guide](https://duckdb.org/docs/current/guides/sql_features/asof_join).

Нельзя перед ASOF оставить только clean price rows: получится запрещённый backoff. Нельзя ASOF-join raw events и надеяться на правильное разрешение ties. Materialize только разрешённый source scope; несколько anchors могут делить bucket relation, но каждый выбор/state guard ограничен своим `<t`. B может хранить служебный bad-price count, а fail-closed проверка срабатывает для выбранного as-of bucket до использования цены; future-only malformed bucket не ломает ранний ответ. Стоимость построения/сортировки/хранения B учитывается полностью: B содержит product×timestamp, потенциально гораздо больше product snapshot. При few anchors выигрыш не гарантирован. P1 не запускается автоматически после P0 и не добавляет новый benchmark budget.

## Reference и dictionary — разные ветви DAG

`R_c(t)` состоит из distinct active products, clean **current** category c и finite p>0, по одному z на product. Сначала current snapshot, затем category predicate; фильтрация raw historical categories заранее может вернуть старую категорию и потерять moves. R включает товары вне C и вне выбранных users. Historical005 numerator остаётся на event-attached category, не переопределяется этим reference.

Code dictionary — отдельная `[S,t)` агрегация исторически наблюдённых `(category_id,named_code)`. NULL name не создаёт known code; несколько разных известных кодов дают conflict. Это recovery lookup по текущему clean ID с отдельным provenance, не latest-code imputation. Нельзя ограничить dictionary семью днями или будущим full-month словарём ради скорости.

Для R вычислить `N_c=count(*)`, `A_c=sum(z)` в double precision. Membership из фактического R: `removed=CASE WHEN member THEN z_i ELSE 0 END`; `n=N_c−CASE WHEN member THEN1 ELSE0 END`. Peer mean определён при known category и n>0; unknown category→supportNULL, known empty R→support0. Invalid own price не мешает mean других товаров, но difference остаётся NULL. Обычное `0*NULL` нельзя использовать: [NULL propagation](https://duckdb.org/docs/current/sql/data_types/nulls). Sum/count missing→zero допустим лишь после известного conditional key и явного empty-population решения.

## Numeric guard не должен читать будущее

Source NaN/±Inf — fail-closed до positive-price filter и log в **relevant as-of latest buckets** кандидатов/active reference inputs. Guard всего October до временного фильтра способен отклонить ранний snapshot из-за future-only malformed suffix: это нарушение invariance. Более широкий source-quality audit возможен отдельно и не должен влиять на ранние features неявно. SQL NULL имеет отдельный missing state; ожидаемый output NaN+mask допускается, неожиданный NaN/Inf и float32 overflow — ошибка.

DuckDB docs подтверждают `isfinite/isnan/isinf`, натуральный `ln` и **base10** `log`; документированного `log1p` в текущем numeric catalog не найдено. Предложение compiler: logical log1p→`LN(1.0+CAST(p AS DOUBLE))` после guard, с independent Python log1p oracle/tolerance. Это не заявление идентичности всех floating-point битов. Currency/price scale фиксирован; клиппинг не добавляется. [Официальный numeric API](https://duckdb.org/docs/current/sql/functions/numeric).

## Память, scans и bounded решение

`row_number OVER product ORDER BY time DESC` по всему prefix добавляет blocking/window buffering и всё равно требует bucket aggregation; P0 сначала обходится max+join. DuckDB прямо относит windows к memory-intensive blocking operators. [Window docs](https://duckdb.org/docs/current/sql/functions/window_functions). GROUP BY/JOIN/SORT тоже могут быть blocking; spill поддерживается, но сочетание операторов и complex aggregates способно вызвать OOM. Не собирать огромный `list(events)` ради last-state. [Tuning guide](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads).

Projection/time filters и exact-key semijoins предложены как способы уменьшить обработку, **не гарантированный pushdown**. Zonemaps помогают при подходящих row-group ranges/ordering; физическую упорядоченность source нельзя предположить. ART предназначен прежде всего для selective scans, не универсального ускорения aggregate/join; composite `(product,time)` нельзя объявлять готовым ASOF-index. Сейчас новые индексы не создавать. [Indexing docs](https://duckdb.org/docs/current/guides/performance/indexing).

`memory_limit` относится к buffer manager, часть structures/results выделяется вне него; RSS/spill измеряются отдельно. Профайл output перезаписывается каждой query, поэтому нужен отдельный stage path, не один «профиль всего pipeline». [Pragmas](https://duckdb.org/docs/current/configuration/pragmas). В будущем gate: прежние100 label-independent Q/≤22kC/2threads/10min/RSS8GiB/temp2GiB, independent all-selected-pairs metadata+full-R oracle. Фиксировать scanned/intermediate rows, state keys, CPU/wall/RSS/spill, setup/export costs. EXPLAIN — без исполнения; EXPLAIN ANALYZE исполняет запрос и расходует тот же gate.

## Переносимый seam и отказы

Typed logical nodes `LastTimestampBucket`, `ConsistentField`, `ActiveDistinctEntity`, `PastDictionary`, `ConditionalSumCount`, `LeaveOneOut` компилируются в общий physical DAG. Reuse допускается только при одинаковых grain, source/time/window/null/multiplicity policies; domain mapping живёт в manifest. Это переносимый execution seam HYP-002/046, не custom SQL на каждую feature и не новый framework. HYP-097/098 остаются reserved: нового механизма не предложено.

Обязательные fixtures: другой user обновил global bucket; known+NULL; field-independent conflicts; expired last-event ровно lower/до lower; peers t/future malformed suffix; move A→B; inactive i∉R/unknown price; singleton R; reference product вне C. Rejected alternatives: Q×raw inequality join, очистка NULL перед arg_max, unordered tied-row selection, automatic median/approx-distinct, игнорирование setup cost. Equality без speedup остаётся полезным результатом; resource failure завершает bounded gate, не открывает endless optimizer grid.
