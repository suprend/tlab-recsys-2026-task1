# Research lab, round033: физическая стоимость выбранных016 bundles

15 октября2026. **Статический разбор и prospective profiler plan**, не benchmark. Прочитаны actual [005 compiler](../../scripts/manual_features.py), [base18 registry](../../configs/features/manual-18.json) и [026 pool](round-026.md). Выбранные L02/L06/L01/L05 рассматриваются при неизменных Q/C/source, semantics и005sharedplan. SQL, EXPLAIN, compiler/tests/Pool/fits не запускались; источники данных и Root files не менялись. Это refinement существующего compute contract, без новых operators, бюджета или speed claim.

## Что shared plan действительно объединяет

`create_manual_features` собирает nonratio definitions в `by_grain` и выполняет отдельный SQL batch для каждого grain/anchor. `_grain_sql` выбирает общий нижний bound: source_start, если в этом grain есть хотя бы одна observed-recency; иначе max(source_start,t−largest_window). Individual aggregate expressions имеют собственные event/window FILTER. Это один GROUP BY внутри grain, **не один universal scan для всех шести grains** и не общий persistent DAG cache между отдельными runs.

В base18 pair batch уже содержит full-observed view/purchase recency; user batch имеет168h counts/distinct, item —24h counts и168h distinct viewers. User-category тоже уже full-prefix из-за recency, item-category/category —168h. Metadata и user-first-seen считаются отдельными full-prefix statements независимо от этих bounds.

Pair semi-join ограничивает **users из Q**, затем группирует все их past `(user,item)`; он не semi-join по C pairs. Item batch ограничивает products из C; user batch включает Q users, в том числе с emptyC. Следовательно число intermediate pair groups может превышать output pairs. Уменьшать работу до candidate-only pair rows без отдельного доказательства/изменения frozen compiler нельзя.

## Дельта четырёх выбранных bundles

N — raw-row count, D — exact distinct projected key, R — full-prefix max(event_time)→recency.

| Bundle и actual physical delta | Existing grain bound | Новая работа без расширения bound |
|---|---|---|
| L02: N(P,view/cart/purchase,24h),3cols | Pair уже source_start→t | Три filtered count states на существующую pair group |
| L06: R(P,cart)+missing, N(I,cart,24h),3cols | Pair full-prefix; item168h | Cart max state, scalar NULL mask после join, item count state |
| L01: N(U,view/cart/purchase,24h),3cols | User168h | Три filtered counts на user group |
| L05: D(I,view,24h,user),D(I,cart,168h,user),D(I,purchase,24h,user),3cols | Item168h | Три filtered distinct aggregates с разными populations |

**Ни один выбранный primitive не расширяет SQL time bounds и не добавляет новый grain batch.** Это доказуемое свойство emitted statement construction, не доказательство равных physical IO/runtime. Plan selection, vector work, aggregate payload и последующая materialization могут измениться.

24h count не выводится из168h count: два одинаковых weekly totals могут иметь разное распределение по последним суткам. L05viewers24h не равен existing viewers168h; purchase-users24h не равен retrieval purchase-users168h. Поэтому semantic dedup не удаляет эти definitions. Полезность/корреляция не проверяются для оправдания pruning после metrics.

## Physical closure не равна aggregate state

[DuckDB aggregate semantics](https://duckdb.org/docs/current/sql/functions/aggregates) различают raw count и DISTINCT; max нечувствителен к дубликатам. L02/L01 counts требуют обновлений scalar counters, L06cart recency — scalar max, mask — scalar projection, а не ещё одного event aggregation. L05distinct требует различать projected users внутри каждого filtered item population; нельзя складывать daily uniques или заменить distinct rawcount ради стоимости.

[DuckDB grouped-aggregation design](https://duckdb.org/2022/03/07/aggregate-hashtable) описывает group keys и aggregate states в hash payload, thread-local aggregation/merge. Отсюда гипотеза: L05 сильнее чувствителен к числу qualifying unique `(item,user)` и skew, чем три обычных counts. Counterhypothesis: таких users мало либо scan/common context доминируют, поэтому marginal time/RSS окажутся небольшими. Фактическое sharing distinct internals конкретной версии/filters статически не установлено; «одинаковый projected column» не гарантирует один shared set.

Ровно3new physical columns каждого bundle — schema/model-width constraint, а не одинаковая память. L06 имеет2new cores+1mask; остальные —3cores. Если будущий execution действительно материализует union всех четырёх selected bundles один раз, это11new aggregate cores+1mask, а не12aggregate states и не четыре независимых base recalculations. Но сам факт union/caching должен быть подтверждён actual execution lineage; здесь он не объявляется реализованным.

[Robust External Hash Aggregation](https://duckdb.org/pdf/ICDE2024-kuiper-boncz-muehleisen-out-of-core.pdf) объясняет давление intermediates и spilling. Он не гарантирует, что наш pinned runtime завершит все aggregates в cap, не доказывает marginal speed и не разрешает увеличить memory/spill limits. Мало output columns не ограничивает group cardinality или distinct support.

## Общий overhead и конкурирующие cost hypotheses

005всегда строит latest-global-past metadata для C-products: full-prefix first/last state, rejoin всего последнего timestamp bucket, conflict/NULL resolution. Отдельный user_state получает first_seen всех Q-users. Even noncategory bundles наследуют эту работу через полный B/context; нельзя убрать её в одном плече и назвать сравнение одинаковым. Совпадающие24/168windows переиспользуют output coverage, новых coverage columns нет; это не отменяет aggregate work.

После batches005LEFT JOINs/broadcast формируют все physical Frows, добавляют masks, INSERT материализует итог; range checks идут по каждому core, затем missing summary. Wrapper экспортирует полный ordered Parquet/ZSTD и хеширует output. Три добавленные колонки увеличивают payload проверки/записи/чтения, даже при прежнем количестве строк. Гипотеза common metadata/joins/export dominance конкурирует с aggregate-state dominance; ни одна сейчас не измерена.

[DuckDB performance guidance](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads) предупреждает о blocking operators, взаимодействии memory pressure и важности cache/connection context. Тёплые pages не равны кэшированным готовым feature tables. Повторный005run заново создаёт batches; shared hash/provenance preparation учитывается один раз только если реально выполнен один раз, per-arm reads/exports — каждый раз. Нельзя ни приписать четырём arms одну бесплатную materialization без evidence, ни четырежды начислить уже однократно оплаченный common stage.

## Только prospective проверка внутри существующего cap

Если отдельная optional cost check уже помещается в016budget, сравнивать baseline-only с B+3 конкретного bundle: exact Q/C/anchors/source/registry-B, pinned version, optimizerON, threads/memory/spill policy, **полный одинаковый common sink** с необходимой дельтой колонок. Никаких одноfeature-loop baseline, LIMIT1, droppedB/context, уменьшенной C или новой серии repeats. Не хватает остатка бюджета — cost hypothesis остаётся unmeasured, без расширения квоты.

[Profiling docs](https://duckdb.org/docs/current/dev/profiling) отличают EXPLAIN от выполняющего запрос EXPLAIN ANALYZE. Будущая instrumentation, только поддержанная pinned version, должна сохранить grain statements/bounds, actual scan/operator cardinalities, aggregate/projection/join/export timings, peak buffer/temp и process CPU/RSS/wall через cleanup. Operator timings не складывать с inclusive parents и не выдавать за OS process CPU; profiler overhead тоже входит в ledger. Wrong keys/values→integrity STOP; resource failure→censored attempt, без retry/refill под видом measurement.

Основной016claim остаётся schema→typedAST generation/selection и независимая правильность расчёта. Этот разбор даёт конкретные cost hypotheses и опровергает «shared columns бесплатны», но не доказывает DAG speedup, latency gain, экономию human-hours или качество новых признаков.
