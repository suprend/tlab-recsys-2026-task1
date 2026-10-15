# Research lab, round035: exhaustive source oracle selected-union016

15 октября2026. **Prospective verifier design**, не implementation/acceptance. Заданный accepted scope:30000Q/6134207C-pairs; эти числа используются как upstream obligations, здесь не пересчитывались. Frozen selected union L02/L06/L01/L05 содержит11cores+1missing mask, ровно12new physical columns. Прочитаны [026](round-026.md), [028](round-028.md), [015](round-015.md) и [018workflow](../experiments/verification-workflow.md). Producer016не читался/не используется; SQL/EXPLAIN/data/tests/Pool/fits не запускались. Нового бюджета нет.

## Источник ожидаемого domain

Общий contextΓ фиксирует sourceSHA, adapter/rawbag/availability policy, source interval[S,E) и допустимые anchors≤E, UTC timestamp precision, interval endpoints, selected AST signatures, accepted Q/C/oldF pins и oracle version. Runtime root/path confinement, strict JSON/schema/hash validation и manifest canonicalization могут использовать reviewed public mechanical helpers. Нельзя импортировать producer materializer/compiler/grain resolver или исполнять artifact-supplied expressions для expected values.

Target relation `T=C JOIN Q` имеет exact `(query_id,product_id)` keys и привязку `(anchor,user_id)` изQ. Сначала independently проверить accepted identities, uniqueness/orphans, shard/day coverage и source/config compatibility. Count6134207 — дополнительный receipt, а не замена bidirectional key equality. Query set30000 включает zeroY/emptyC; ни labels, ни producerF не определяют нужную population.

Expected domains формируются **до чтения producer values**:

- `DU=distinct(anchor,user_id)` из всехQ, включая emptyC.
- `DI=distinct(anchor,product_id)` изT.
- `DP=distinct(anchor,user_id,product_id)` изT.

DISTINCT применяется к domain keys, никогда к raw event bag. Duplicate query contexts могут факторизоваться по determinant, но каждый query/C physical key всё равно сравнивается. Cache key включаетΓ и exact anchor; item-only key нельзя использовать для user/pair features. EmptyC query даёт0Frows и остаётся в отдельном Q coverage receipt, а не исчезает из проверенного query scope.

## Независимые формулы selected11cores+mask

Для key k соответствующего grain обозначим source bag `E_k(t)={e:key_g(e)=k,S≤e.ts<t}`. Каждая физическая raw строка сохраняет multiplicity, stable eventID/order не придумывается. Для a∈{view,cart,purchase}:

`N_g(a,w;k,t)=Σ_{e∈E_k(t)} 1[e.action=a ∧ e.ts≥max(S,t−w)]`.

`D_I(a,w;i,t)=|{e.user_id:e∈E_i(t),e.action=a,e.ts≥max(S,t−w),e.user_id≠NULL}|`.

`M_P(cart;u,i,t)=max{e.ts:e∈E_(u,i)(t),e.action=cart}`; пустой set→NULL. `R=t−M` в declared seconds/precision, `missing=(M IS NULL)`. Не ограничиватьM7d: old cart остаётся finite recency. Все timestamp peers ровноt исключены глобально, независимо от user/source row order; нижний window endpoint включён.

| Expected map | Точные outputs |
|---|---|
| DP | L02:3N_P(view/cart/purchase,24h); L06:R_P(cart),егоmissing |
| DU | L01:3N_U(view/cart/purchase,24h) |
| DI | L06:N_I(cart,24h); L05:D_I(view,24h),D_I(cart,168h),D_I(purchase,24h) |

Selected columns не category-conditioned: неизвестный current category не должен превращать их вNULL или удалять C-row. Metadata/B остаются в preserved-oldF scope. Все count/distinct known-empty keys получают0, отсутствующийcart→NULLrecency/true mask. Нельзя получить expected0 через отсутствующий expected-key: сначала LEFT domain→aggregates с проверенной полной domain coverage.

## Bounded source aggregation и every-row comparison

[DuckDB aggregate semantics](https://duckdb.org/docs/current/sql/functions/aggregates) закрепляют DISTINCT, NULL и FILTER; [semi joins](https://duckdb.org/docs/current/sql/query_syntax/from) фильтруют левую relation без размножения matches. Предложение: по одному exact anchor читать нужный source prefix, собственными явно написанными predicates строить U/I/P aggregates, используя domain membership/semi joins. Не join events кT до aggregation: один event пользователя с десятью candidates иначе станет десятью raw occurrences. User counts включают его действия с товарами внеC; item distinct audience включает пользователей внеQ. Только DP ограничивает pair keys нужными C-pairs; это semantic reduction independent oracle, а не копия005's user-wide physical plan.

Expected maps обязаны иметь ровноDU/DI/DP keys, без duplicates/missing/extra, даже при пустой истории. Затем many-to-one broadcastT→maps. Каждая actual physical row получает своё expected12-vector; нельзя проверять DISTINCT feature representatives producerF или случайный sample. Disjoint anchor/key chunks должны покрыть весьT ровно один раз; no full6134207×12 Python loop и no required giant flat expected export. Vectorized SQL/typed-array comparisons допустимы как transport/comparison, не источник formulas.

До значений проверяются exact names/order/physical types: countsBIGINT, recencyDOUBLE, maskBOOLEAN и unchanged old fields; floating coercion не лечит wrong schema. BIGINT keys/counts сохраняются exact, nullableInt64 задаётся **до** DataFrame inference, не SQLCAST после float rounding. NULL-safe equality отличаетNULL/0/NaN; recencyfinitepositive и mask consistency обязательны. Timestamp precision и float comparison policy фиксируются доoutputs, без расширения tolerance по failure.

Rowset/multiplicity сверяются в обе стороны, например [EXCEPT ALL semantics](https://duckdb.org/docs/current/sql/query_syntax/setops), плюс uniqueness и typed schema gate; hashes/rowcounts отдельно не доказывают значения. Любой wrong physical copy одного user/item value ловится через every-row comparison.

## Сохранность B и независимость доказательства

Для каждойT-row вся прежняя physicalF проекция сравнивается с acceptedoldF по exact keys, включая retrieval/query/context/coverage/masks, не только18cores. Это exhaustive **preservation/equality** относительно accepted artifacts. Оно не становится новым exhaustive manual18 source proof:018numeric formulas остаются sampled. B41model-derived fields/encoding наследуют тот же declared model assembly contract; actual matrix/model boundary proof — отдельный gate, не объявленный результат этого source oracle. ПолныйY/outsideC и evaluation denominator не изменяются collection verification.

[NoREC](https://www.manuelrigger.at/preprints/NoREC.pdf) мотивирует независимую вычислительную форму, [TLP](https://manuelrigger.at/preprints/TLP.pdf) — partition/metamorphic crosschecks. Они не гарантируют нашSQLoracle автоматически: source predicates могут быть одинаково ошибочны. Поэтому≤32-row pure-list/literal028goldens должны независимо проверить source SQL и transports: duplicatecart→count2/distinct1; lower-bound inclusion; ts=t exclusion; oldcart−8d→691200seconds; no-cartNULL; off-C user activity; off-Q item audience; unknown category; BIGINT2^60+1; одна wrong broadcast copy; omitted empty-domain key. Partition counts можно складывать по bag partitions, distinct — только объединять sets, не складывать sizes.

## Scope, ресурсный и terminal gate

Все восемь pool bundles проверяются symbolically для legality/closure; numeric source oracle вычисляет **только выбранные12**, без materialization198candidates/невыбранныхL. Evidence публикует domains/anchors/key coverage, checked rows/columns, mismatch counts, NULL/empty cases, exact pins и proof scope без raw user IDs. Fresh reseal wrong value/key/type/lineage не делает output accepted.

Source recompute, exact DISTINCT, oldF/newFreadback, hashing, literal faults, failed attempts, profiler/cleanup оплачиваются из существующего016shared2CPUh ledger; отдельная allowance не создаётся. Pair domain может быть размеромC, source scans могут доминировать; factorization не обещает speed/RSS. Read-only DB, bounded per-anchor/chunk memory/spill и remaining CPU/wall guards нужны до/после stages. Success только после close, final resource receipt и post-cleanup check; unknown usage→failed/STOP. Если exhaustive comparison не помещается, scope остаётся incomplete, нельзя молча заменить sample и написать exhaustive. Только после независимого review и полного evidence внешний reviewer решает acceptance; verifier не выдаёт себе approval fresh hashes.
