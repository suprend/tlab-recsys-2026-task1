# Round015: exhaustive F verification через typed source domains

15 октября2026. **Research/proposal,0data scans/fits/downloads/benchmarks; frozen files/repo/approvals не менялись.** Прочитаны actual[manual18](../../configs/features/manual-18.json), [protocol](../../configs/protocols/clock-48h.json), current018scope и rounds[011](round-011.md)/[013](round-013.md). Вывод: факторизация **ожидаемых source values** возможна; проверка EVERY physical Frow сохраняется. Это предложение для будущего018regeneration/016, не новая реализованная exhaustive guarantee. HYP115/116 reserved: refinement verification/002/046.

## Четыре первичных основания

PostgreSQL описывает GROUP BY/functional dependencies и признаёт ограниченное правило по primary key. Это различает доказанный determinant и произвольно выбранную representative row; разрешение конкретного SQL engine не доказывает наш feature FD. [SELECT/FD](https://www.postgresql.org/docs/current/sql-select.html).

Bakibayev et al. показывают factorisation/partial aggregation с сохранением query semantics. Это основание сокращать повторный расчёт; опубликованный FDB speedup не переносится на DuckDB/manual18. Flattening/enumeration остаётся отдельной работой, зависимой от размера результата. [Авторская работа](https://arxiv.org/pdf/1307.0441).

DuckDB set operators безALL удаляют duplicates, сALL используют bag semantics. Поэтому rowset/multiplicity comparison требует bidirectional EXCEPT ALL плюс отдельную exact schema check: implicit casting не должен скрывать неверные physical types. [Set operations](https://duckdb.org/docs/current/sql/query_syntax/setops).

В Featuretools1.31.0 tests есть literal expected arrays для cutoff endpoints, проверки reordered cutoff IDs и approximation binning. Разные binning/endpoints действительно дают разные counts. Это полезные образцы tiny contracts, не готовая независимая гарантия нашего oracle; approximate cutoff нельзя назвать exact factorisation. [Tagged author tests](https://raw.githubusercontent.com/alteryx/featuretools/v1.31.0/featuretools/tests/computational_backend/test_calculate_feature_matrix.py).

## Полный determinant и18core features

Предлагаемый общий contextΓ включает source SHA/interval, adapter/availability contract, registry/oracle version, timezone/endpoints, metadata/null/multiplicity policy и simulated as-of clock. Нижеt — **точный** anchor; параметры окон/operator входят в определение каждой feature. Cache keys безΓ/t недопустимы.

| Domain key внутриΓ | Core expectations из source |
|---|---|
| `(t,u)` | user view/cart/purchase7d; distinct viewed items7d —4 |
| `(t,u,i)` | pair view/cart/purchase7d; view/purchase observed recency —5 |
| `(t,i)` | item view/purchase24h; distinct viewers7d —3 |
| `(t,u,c)` | user-category view7d, share, observed recency —3 |
| `(t,i,c)` | item-category view7d и share —2 |
| `(t,c)` | category view7d denominator —1 |

Это18определений actual registry, не предложение новых features. Для F сначала независимо получается current candidate category `c=MΓ(t,i)` из **полного global past timestamp bucket всех пользователей**. Same known+NULL bucket ambiguous; older backoff запрещён. Исторические numerator counts используют category_id **каждого события**, не current product category. Source `M` уникален по(t,i), включая explicit missing/ambiguous status; исторические IC/UC keys сохраняютc, даже если в конкретном context оно функционально определяется item.

`UCshare=UCview/Uview`, `ICshare=ICview/Cview`; denominator охватывает полный соответствующий source population, включая товары внеC. Known conditional key с пустой историей даёт0count; неизвестныйc даётNULL conditional values. Denominator0→NULL, recency без событий→NULL. Все masks выводятся из expected values, не копируются изF.

Observed recency и user/item first-seen age требуют `[source_start,t)`, не7d. Metadata/history/age flags зависят от(t,i)/(t,u); coverage24/168h — отΓ,t,window иsource interval, не user age. Все45physical columns, включая retrieval inputs/query binding/supports/masks, остаются в заявленном comparison scope, а не только18cores.

## Как получить exhaustive proof — proposal

Сначала independently verified/acceptedQ/C с exactpins задают target relation `T=C JOIN Q`, уникальную по(query_id,i). DomainU строится из **всехQ**, включая zero-C queries; остальные необходимые domains — projectionsT и independently resolved metadata. DISTINCT применяется к **keys**, не к produced feature values и не к raw source events. Sampling queries/bottom-SHA/eligibility остаётся отдельной exhaustive QYC обязанностью; factorisation не позволяет выбрать толькоpositive или удобные queries. FullY внеC сохраняется в evaluation, F не становится новым label-conditioned subset.

Затем собственные SQL/Python formulas агрегируют source raw bag на каждом domain. Unconditional count domains содержат также known-empty keys: LEFT domain→aggregate и явный0. Для unknown metadata F-row сохраняется с conditionalNULL; её нельзя потерять INNER JOIN к известнымc. Expected relation обязан иметь ровно domain keys — uniqueness и bidirectional missing/extra checks **доbroadcast**. Наличие только keys, найденных в source aggregate, недостаточно.

Broadcast — many-to-one joinT→каждая expected-domain table. Проверяются exact final rowset/multiplicity=C, retrieval/query columns и **каждое поле каждой physical Frow** относительно reconstructed expectations. Структура сравнивается EXCEPT ALL; numerical values — NULL-safe equality, exact bool/integer, finite policy и заранее declared float tolerance. Checksum дополняет evidence, не заменяет semantic comparison. Producer DISTINCT representative запрещён: он может скрыть единственную испорченную копию user/item feature.

Independence означает собственные source predicates/category resolution/формулы без production counters/compiler/materializer. Общими остаются JSON/hash/schema definitions. Tiny direct-list oracle проверяет сам factorised verifier; unsupported registry/016AST требует отдельного oracle rule/review, не произвольного исполнения producer expression.

Actual audit clock2026 проверяется отдельно: input/decision artifacts sealed+hashed до открытия reserved query targets сейчас. Simulated anchors/availability2019 задают функцию expected values; физического вычисления в2019 не требуется. Decision lock pin и audit-access evidence связывают проверку с внешними ожиданиями, но actual wall timestamp нельзя использовать вместо simulated cutoff или для восстановления прошлого. Это два различных obligations, не один скрытый cache-clock.

## Четыре counterexamples и будущий gate

**Wrong FD:** два пользователя имеют одногоcandidateitem, но user/pair views1и2. Item-key representative скрывает различие. Даже одинаковые user values сегодня не доказывают FD наitem.

**Mixed bucket:** старое categoryA, latest peersB+NULL. Source-derivedM обязан датьunknown; producer categoryA/B нельзя использовать для формирования UCdomains.

**Omitted key:**Qимеетknown user безview; aggregate не выдаётrow. Если INNER JOIN теряетkey, wrongFcount7 остаётся несравнённым. Exactdomain cover создаёт expected0 и ловитfault; zero-CQ остаётся вQcoverage.

**Bad broadcast copy:** из двух Frows одного(t,u) только одна имеетwrong user count. Проверка одной representative проходит; EVERY-row join comparison отклоняет. Дополнительно нужны duplicate-source multiplicity, last-distinct expiry, future suffix/peer reorder и off-C denominator faults.

Prospective synthetic gate:≤32events/8Q/24C, все18cores+metadata/supports, literal tables иfresh-resealed faults,0fits; execution/budget требуют отдельного решения. Evidence перечисляет domain sizes, exact key cover, physical rows×columns checked, unknown/missing cases и source scope. Existing018sampled F evidence не переименовывается exhaustive.

Стоимость неизвестна. U/Idomains могут быть существенно меньшеF, Pdomain в худшем случае равенF; source recomputation, exact DISTINCT и EVERY-row comparison/readback могут доминировать. Не строить Q×всеsourceevents crossproduct или materialise огромныйexpectedflatfile без cost gate; возможен bounded per-anchor/shard comparison с exact cover. PeakRSS/CPU/wall/spill/cleanup/failures оплачиваются одним будущимledger. Это способ сделать exhaustive proof структурно возможным, без quality/latency/generalisation claim, нового framework или автоматически выданного бюджета.
