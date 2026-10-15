# Round073 — reuse вычислений: exact values, physical plan и оплаченная экономия

15 октября 2026. **Source-only refinement**, без data/SQL/EXPLAIN, benchmarks, fits и изменений016. Прочитаны rounds [012](round-012.md), [его critic](round-012-review.md), [033](round-033.md), [037](round-037.md), [044](round-044.md), [062](round-062.md)/[064](round-064.md). Они уже охватывают strong calculation control005, complete sink, cost accounting и cache identity. Новый узкий вклад — конкретный документированный cache lifecycle Featuretools и контрпример, разделяющий exact reuse, stale snapshot и temporal approximation. Новая HYP/task не нужна; текущий once-owner остаётся единственным тяжёлым исполнением.

## Три разных механизма под словом «shared»

**Логический DAG** показывает общие зависимости. Он сам по себе не удостоверяет общий scan, aggregate state или отсутствие повторной материализации. [DuckDB WITH](https://duckdb.org/docs/current/sql/query_syntax/with) описывает materialization по умолчанию, возможный inlining и эвристики optimizer; повторённый SQL fragment не равен повторённой физической работе. Current docs относятся к ветке1.5, будущий physical claim требует pinned runtime и observed plans. Два AST могут после optimizer давать одинаковую работу; разные count/distinct FILTER могут проходить один scan, сохраняя разные состояния.

**Exact execution reuse** сохраняет определения, source snapshot, Q/C/domain, clock/window/NULL/multiplicity и representation. По уже опубликованному033 unchanged005 объединяет aggregates по grain/anchor; выбранные016 primitives не расширяют его scan bounds. Поэтому «автоматизированный DAG быстрее одного отдельного scan на каждый признак» сравнивает с другим, более слабым control. Для added speed claim нужен выигрыш относительно существующего batched005 при одинаковом полном output.

**Persistent transport/cache** может экономить передачу source, но обязан различать версии значений. [Featuretools1.31 performance guide](https://docs.featuretools.com/en/stable/guides/performance.html) прямо предупреждает: persistent cluster использует metadata EntitySet и при тех же metadata не пересылает изменённые row values; авторы предлагают уникальный EntitySet id. Там же описаны копии EntitySet в отдельных processes и overhead их передачи. Это авторский объявленный lifecycle, не найденная ошибка нашей системы: Featuretools здесь не установлен и не используется. Наш вывод — schema equality недостаточна для accepted source-bound cache hit; оплаченная более быстрая выдача stale значений не является выигрышем.

Отдельно [Featuretools handling time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html#approximating-features-by-rounding-cutoff-times) описывает `approximate`: часть aggregations рассчитывается по более раннему округлённому cutoff. Это может сохранить отсутствие будущего, но меняет допустимый исторический prefix. Temporal safety не равна точному совпадению feature values; approximation не разрешена нашим frozen AST contract. Chunking, наоборот, должно сохранять значения при полном необходимом source context, хотя может повторять setup/scan work.

## Буквальный fixture: двенадцать входных строк

Будущая спецификация, не исполненный тест. Source coverage начинается раньше T−168h; два Q: `(A,T)` и `(A,T+1h)`, у каждого C={i,j}. EventFact — raw bag из шести строк:

| User/action/item | event_time | Multiplicity |
|---|---|---|
| A/view/i | T−25h | 1 |
| A/view/i | T−2h | 2, exact duplicates |
| A/cart/i | T−26h | 1 |
| A/view/j | T+30min | 1 |
| B/view/i | T | 1 |

Суммарно6 events+2Q+4C=12. История строго `<query_time`, окна lower-inclusive. Literal expected user-view-count24 равен2/3, count168 —3/4, distinct viewed items24 —1/2. Pair(A,i) view-count24 равен2/2; item(i) view-count24 —2/3: глобальный peer пользователя B исключён при T и допустим при T+1h. Pair cart recency i —26h/27h, несмотря на отсутствие cart в24h; для j recency NULL и missing=true.

Кэш `(user,day)` с одним cached24h snapshot для обоих anchors выдаст stale значения; общий source filter до максимального anchor без отдельных predicates, напротив, внесёт будущее в первый query. Оба могут уменьшить работу, оба неверны. Вторая версия source добавляет один duplicate `A/view/i,T−2h`: прежние schema/EntitySet metadata сохраняются, counts увеличиваются, distinct остаётся прежним. Это13 строк, достаточных для обязательного cache miss/value invalidation без нового operator.

## Цена reuse и будущая acceptance specification

Обозначим K construction+hash+verification cache, R_j paid read/projection/export потребителя, D_j direct calculation. Даже если `R_j<D_j`, end-to-end экономия относительно repeated direct work требует `K+ΣR_j<ΣD_j`; при одном потребителе она может отсутствовать. Это аналитическое условие, не measurement. Если unchanged005 уже делает общий union один раз, primary control тоже оплачивает construction один раз: умножать его на четыре ради красивого speedup нельзя. Failed construction, invalidation, serialization, cleanup и independent evidence входят в стоимость; hit не переносит fit authorization.

Один **future-only** bounded protocol: сначала указанный≤13-row literal correctness suite, затем same-AST M=current005 и A=предложенный exact sharing на том же fixture/full sink. Не более двух balanced order blocks AB/BA,2threads,512MiB, суммарно≤5min,0fits — лишь prospective предел, не предоставленное разрешение и не добавка нынешнему016. Cache construction включается в каждый cold-process attempt; отдельно описывается один заранее определённый paid reuse consumer sequence. Fresh process не означает cold OS cache; source hashing тоже может прогреть страницы. Запрещены cache flush, случайные дополнительные repeats и бесплатный warmup.

Correctness acceptance: exact keys/integers/NULL/masks/coverage и заранее заданная float policy; changed-source mutation исключает hit. Cost acceptance для узкого workload требует complete matched attempts, меньший total process CPU у A в обоих order blocks и прохождение одинаковых memory/deadline gates. Иначе cost outcome inconclusive/no observed saving; tiny fixture не доказывает масштабируемость. Peak RSS/spill показываются отдельно, wall не подменяется wall×threads. [DuckDB tuning guidance](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads) отмечает memory-intensive blocking operators и возможный OOM при их сочетании; fusion не гарантирует меньший peak. [Profiling](https://duckdb.org/docs/current/sql/statements/profiling) даёт actual cardinalities и cumulative operator wall times: это диагностика, не полный OS CPU ledger. `EXPLAIN ANALYZE` исполняет запрос и тоже оплачивается; сейчас не запускался.

Нужное amendment existing compute/report scope: явно назвать cache lifecycle и оплаченный comparison boundary. Exact feature calculation и automatic generation остаются самостоятельными claims даже при одинаковых physical plans или отсутствии экономии. Ни скорость, ни human-hours, ни prediction gain этой запиской не установлены.


## Publication scope appendix — 15 October 2026

Original note SHA256 3c27c2da30bd0bbbd9c65c497c4155854916983344a607f7a2b0b03da1d08c38. This retained research snapshot predates the locally accepted actual016 model evidence in the current [progress report](../progress-report.md). Its future tense is historical scope, not the current canonical execution status. No new hypothesis execution, resource grant, fit, source download or reserved-target access is authorized by publication. Current accepted development winner is R2; this does not establish guided-strategy superiority or heldout improvement.
