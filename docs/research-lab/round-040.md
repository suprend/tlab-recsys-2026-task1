# Research lab, round040: EventFact, PropertyState и Query как разные temporal roles

15 октября 2026. **Future schema/adapter proposal**, уточняющий [030](round-030.md)/[036](round-036.md)/[039](round-039.md), не новый feature family/framework. Данные не читались; SQL/tests/Pool/model/fit/download и изменения code/config/Root не выполнялись. Новые operators, budget/approval и IDquota не создаются. Задача — описать честную границу переноса 005/016 между embedded metadata и property changelog, а не объявить перенос реализованным.

## Четыре первичных основания

[Featuretools Handling Time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html) определяет time index как время знания строки; secondary time index объявляет более позднее знание отдельных columns. Default `include_cutoff_time=True` включает peers; наш `<t` не следует из одного слова cutoff, требуется явное endpoint agreement. Ни тип datetime, ни название timestamp не доказывают available time.

[Feast PIT joins](https://docs.feast.dev/getting-started/concepts/point-in-time-joins) привязывают retrieval/TTL к каждому entity timestamp. Документация отдельно предупреждает: default event-time join может вернуть поздний backfill; created timestamp обычно только deduplicates одинаковое eventtime. Opt-in `filter_by_created_timestamp=True` добавляет created≤entity, предполагая, что created отражает online availability. Это не наша strict`<t` гарантия и не installed/pinned capabilityTLAB.

[DFS2015](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) строит features по relations/types; это основание для typed generation, не автоматическое понимание observational unit/knowledge clocks. [DuckDB joins](https://duckdb.org/docs/current/sql/query_syntax/from) различают ordinary/semi/as-of joins. SQL syntax «ASOF» не удостоверяет uniqueness/tie/NULL/business policy. Schema constraints и source annotations остаются reviewer inputs.

## Три минимальных relation roles — proposal

| Role | Минимальные аннотации | Multiplicity/clock obligation |
|---|---|---|
| EventFact | Nominal user/item keys, action predicate, event_time/unit/UTC precision, optional event-attached attributes | Countable raw bag; no invented eventID/dedup/peerorder; event availability declared отдельно |
| PropertyState | Entity key, fieldID/type/unit, observed/valid timestamp, optional available_at, value/NULL/revision policy | Неколичественный metadata update; determinant(entity,field,asof,policy), не business event |
| Query | Q(query_id,user,t), fixed C(query_id,item), phase/source/coverage/past eligibility policy | Exact Q/C uniqueness/cover; repeated contexts могут factorize, каждая physicalrow сохраняется |

Query role содержит две physical relations Q/C; денормализация в произведение queries×events не требуется. Target Y — отдельная закрытая relation, не обязательный вход compiler/inference; held-out inference не получает Yrefs до prediction seal039. IDs номинальны. Единица count — raw rows либо distinct projected entities, recency — seconds. Тип и единица metadata задаются человеком: numeric property code не означает price/currency, treeID — readable label.

Наблюдение на sample не доказывает PK/FK/one-to-one. Отсутствующее поле означает unsupported capability, а не observed0. Неизвестная availability требует explicit offline assumption либо отказа от strict knowledge claim. Source coverage, first-observed age и exposure — разные величины.

## Temporal joins и две metadata policies

History использует `[max(S,t−W),t)`, observed recency — `[S,t)`. При известном available_at дополнительно требуется `<t`; поздние corrections/revisions требуют явной knowledge/version policy. Optional availability нельзя автоматически считать event_time. Peers читаются глобально до updates, без rowid ordering.

**Embedded-global-bucket005:** для item найти последний past event timestamp среди всех users и рассмотреть целый bucket. Known+NULL или разные categories означают unknown; older backoff запрещён. Historical counters сохраняют category каждого event. Выделение metadata observations из событий не меняет countable EventFact bag.

**Per-property changelog:** отдельно для `(item,field)` выбрать последний eligible past state timestamp и разрешить весь bucket по declared conflict rule. Поле carry-forward своего последнего observed state, даже если другое поле обновилось позже. Latest explicit NULL не возвращается к older known value. Future first snapshot не заполняет прошлое. Это proposed interpretation036, не доказательство непрерывной истинности weekly snapshots или известного ingestion clock.

Resolved state обязан быть уникален по `(entity,field,t,policy)`. LEFT many-to-one join сохраняет каждую event/query row. Join всех property versions перед COUNT размножит событие и запрещён. Semi-join ограничивает keys, сохраняя raw duplicates. Taxonomy ancestors — отдельная membership relation; они не становятся дополнительными business events или новым legal operator.

## Historical category и current-as-of cohort

Пусть `K_e` — event-attached category либо category knowledge перед событием по отдельному reviewed contract. Historical count: `H_c(u,t)=Σ pastviewevents 1[K_e=c]`. Current-cohort count: `J_c(u,t)=Σ pastviewevents 1[M_item(e)(t)=c]`, где M использует только eligible state до query t. J переклассифицирует прошлую историю по текущей категории; он не утверждает, что эта категория была известна тогда.

Оба определения могут соблюдать query-asof `<t`, но имеют разные classification clocks, determinants и provenance. «Нет future data» не означает равенство semantics. Current005 header требует `historical_event_category_id`; J сейчас unsupported. Это объяснение будущего contract, не добавление J в016. Denominator share должен совпадать с numerator по classification/bag/action/window population, включая off-C products; смешивать historical numerator и current-cohort denominator нельзя.

## Почему нет drop-in переноса

| Источник | Binding | Граница005/016 |
|---|---|---|
| REES46 | EventFact с attached category | Current005 global event bucket, не per-field catalog state |
| Retailrocket | EventFact и отдельный PropertyState | Event enrichment не учитывает property change после последнего event до query; full manual18 требует нового resolver contract |
| Taobao031 | Пятиколоночный consumer с event category | Action/clock/availability annotations и fav observation domain не подтверждены полностью; price/brand/property relation не выдумываются |

Current016 генерирует registry существующих count/distinct/observed-recency по canonical event roles;005 SQL ожидает canonical events и фиксированную metadata policy. Это не универсальный relational ingestion или bitemporal resolver. Abstract roles не добавляют adapters, arbitrary SQL или unsupported joins. Даже noncategory grammar требует reviewed mapping/clock/bag/context/pins и closure проверки относительно source-local B. Полной B41 parity или переносимости качества нет.

## Будущий literal proof≤32rows,0fits

Fixture T: XcategoryA вT−4h, UviewX вT−3h, XcategoryB вT−1h, unrelated availableX=0 вT−30min. Golden query category=B, historical view counts A1/B0, current-cohort B1. Последнее available update не стирает categoryB при per-property policy. Frozen005 last-event metadata дал быA: это ожидаемое semantic difference, не rounding.

Другой itemZ: oldcategoryA, latest bucket B+NULL→unknown/no older backoff. Known category с пустой историей даёт count0; unknown conditional key→NULL. Correction с old valid time, но future available_at исключён. Property ровноT исключено. Duplicate view удваивает raw count, не distinct; два fields/ancestors не удваивают event. User age1h при полном window coverage не означает coverage1h. Literal expected tables отдельно фиксируют EventFact, resolved PropertyState, historical event category и query-current category, затем каждый physical key.

Future checks должны ловить wrong grain/fanout/unit/clock/capability и различать H/J; сейчас они не исполняются. Evidence связывает adapter/policy/source version/typedAST/representation, domain cover, NULL cases и independent formula scope. Parsing/oracle/readback/failures/cleanup учитываются в существующем authorized ledger, без дополнительной allowance. Proof подтверждает mechanics/conformance; он не доказывает online availability, cross-dataset quality, speedup и не разрешает менять frozen005/016.
