# Research lab, round030: минимальный schema→AST generator016

15 октября2026. **Prospective architecture/test specification**, не implementation. Прочитаны [026](round-026.md)/[029](round-029.md), actual [005 vocabulary](../../scripts/manual_features.py) и [manual18](../../configs/features/manual-18.json). Compiler/tests/Pool/data/fits не запускались, Root019 synthetic files не менялись. HYP137/138 остаются stable refinements002; P0 ниже — минимальный seam для review, не новое разрешение/бюджет или framework.

## Основание и ограниченный claim

[DFS2015](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) строит programs по entity relationships и field types. [Featuretools primitives](https://docs.featuretools.com/en/stable/getting_started/primitives.html) отделяют typed definitions от calculation; `features_only=True` возвращает definitions. Это обосновывает definition-only generation без198 materialized candidates. Numeric tags не угадывают units/availability. [OpenFE2023](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) отделяет generation и обучаемую оценку через FeatureBoost; последняя здесь отсутствует, а не считается бесплатной. Эти источники не доказывают качество нашего pool или реализации, которой пока нет.

Новый seam должен **исполнить parameterized rules**, а не прочитать восемь готовых registry JSON. Human-authored templates/windows остаются явными inputs; автоматизируются binding ролей, instantiation, legality, semantic signatures, dedup/closure и deterministic serialization. Это узкая typed generation из аннотированной schema, не самостоятельное понимание бизнеса.

## Один declarative schema contract

Предлагается версионированный объект: event relation; logical roles user/product→physical columns; номинальные exact key types; event_time/timezone/precision; action column и mapping семантических view/cart/purchase; bag multiplicity без invented eventID; source bounds/available-time assumption; explicit metadata capabilities. Q/C объявляют canonical `(query_id,user_id,anchor,product_id)` domain и uniqueness obligations. PK/FK/roles предоставлены reviewer, не доказаны именем столбца или sample.

Для current016 нужны U={user}, I={product}, P={user,product}; projection для breadth — opposite entity key. Optional category/code/price не открывает новые grammar operators. Нетviews/cart capability — соответствующая template rejected, не observed0. На invoice-only schema все восемь нынешних whole bundles могут оказаться unsupported из-заcart: нельзя автоматически invent replacement pool.

005 работает с canonical `events`/column names. Logical-role binding может породить canonical registry; ingestion произвольно переименованного raw source остаётся отдельным reviewed adapter, не незаявленной функцией frozen compiler. Unit/clock/availability changes меняют context identity, а не только labels JSON.

## Три общих template families → L01–L08

Обозначения N(g,a,w), D(g,a,w,k), R(g,a) соответствуют **существующим** count/count_distinct/recency_seconds. N использует column=null, D — canonical user_id/product_id, R — column=event_time/window=observed; count windows JSON integers24/168. Header policies005 сохраняются.

1. **ActionVector(g):** для g∈{U,P,I} перебрать ordered actions(view,cart,purchase), породить триN. Human window policy W(U)=W(P)=24h,W(I)=168h. ПолучаютсяL01–03.
2. **BreadthVector(g):** g∈{U,I}, projection=opposite entity role; триD по тем же actions. Human window vectors U=(24,168,168), I=(24,168,24). ПолучаютсяL04–05; type rule запрещает усреднять IDs и требует явного projected key.
3. **CartTiming(g):** g∈{P,U,I}; породитьR(g,cart) и его compiler missing mask. Human companion policy: P→N(I,cart,24); U→D(U,purchase,24,product_id); I→D(I,cart,24,user_id). ПолучаютсяL06–08.

Такое разветвление companion/window — disclosed human prior, не learned discovery. Deterministic family/grain order выше задаёт stable L IDs, semantic AST SHA не зависит от display name. После generation policy требует **ровно эти восемь** closures на current reviewed schema; меньше/больше или иной final-B alias→unsupported/mismatch до draw, без тихого rescope.

## Exact proposed names и physical delta

Имена ниже — deterministic lowering policy, новые относительно B names. ДляR mask не отдельный registry core:005 сам добавляет suffix `_missing`.

| ID | Три actual new output/model columns |
|---|---|
| L01 | `auto_user_view_24h`, `auto_user_cart_24h`, `auto_user_purchase_24h` |
| L02 | `auto_pair_view_24h`, `auto_pair_cart_24h`, `auto_pair_purchase_24h` |
| L03 | `auto_item_view_168h`, `auto_item_cart_168h`, `auto_item_purchase_168h` |
| L04 | `auto_user_distinct_view_items_24h`, `auto_user_distinct_cart_items_168h`, `auto_user_distinct_purchase_items_168h` |
| L05 | `auto_item_distinct_view_users_24h`, `auto_item_distinct_cart_users_168h`, `auto_item_distinct_purchase_users_24h` |
| L06 | `auto_pair_cart_recency_seconds`, `auto_pair_cart_recency_seconds_missing`, `auto_item_cart_24h` |
| L07 | `auto_user_cart_recency_seconds`, `auto_user_cart_recency_seconds_missing`, `auto_user_distinct_purchase_items_24h` |
| L08 | `auto_item_cart_recency_seconds`, `auto_item_cart_recency_seconds_missing`, `auto_item_distinct_cart_users_24h` |

ДляL01–05 три core definitions; дляL06–08 два cores плюсauto mask. Existing coverage24/168, metadata/context иB columns переиспользуются при expansion B registry; новых integer windows нет. Counts/distinct noncategory не создают masks. Слепое включение `_missing` как core rejected005; silent name truncation/collision запрещены.

## Definition-only algorithm и P0 seam

Предлагаемый pure interface `generate_pool(schema,grammar_policy,B_signatures,protocol)` возвращает definitions, reject trace, semantic signatures и exact closures. Сначала schema/capability binding, затем typed instantiation; canonical signature включаетgrain/keys/event/operator/projection/window/endpoints/unit/bag/context/NULL/availability, а не толькоname. Dedup сверяется с **полным** frozen B/retrieval и final009 schema019. Например distinct item purchase-users168h — retrieval alias; category-count mask — Bcategory-missing alias; coverage72 на current anchors — context duplicate. Эти branches отсутствуют в первом pool, не удаляются по scores.

Closure model зеркалит declared005 schema contract, но его доказательство отдельно подтверждается emitted schema в будущей tiny проверке. Unsupported arithmetic/log/sum/nested/nominal cross/SQL text/LLM отвергаются. Generated arm registry содержит B definitions+selected new cores; same005 вычисляет values. Definition generator не содержит numeric expected formulas; independent list oracle028 не вызывает generator/compiler для вычисления goldens.

Второй pure seam `select_arms(pool,policy,PRNG)` фиксирует I1=L02/I2=L06 и два uniform independent R draws с возвращением из sorted8. Collisions/invalid attempts consumed/no redraw;≤12 physical new columns/≤4 fits/≤2CPUh общий ledger. Pool SHA/order/seeds/state и JSON bytes фиксируются до metrics; learned/proxy fits отсутствуют.019 exact B/settings/population и retrospective/confirmation chronology не меняются.

## Минимальные future acceptance checks

P0 contract tests, **не исполнены/не финансируются автоматически**: schema-only генерация даёт exact8L/signatures/names/core counts/closures; dictionary order и корректное role renaming сохраняют role-normalized AST, хотя source/context hashes могут измениться; отсутствующийcart, неподтверждённыйclock, numeric-ID arithmetic, unknown operator, injected SQL, duplicate B alias и wrongmask count дают explicit rejection. Role renaming проверяет logical binding, не обещает raw ingestion.

Numeric stage — только frozen выбранные bundles на≤32-row fixture028,≤12new columns/0fits: emitted delta schema exactly3, sameQ/C physical rowset, literal/list expected counts/distinct/fullprefixrecency/NULL, peers/expiry/dups и exact transport. Все восемь programs symbolically inspected, не materialized для selection. Artifact handoff: schema/policy/B pins, generator version, reject trace, pool/closure manifest, frozen draw и evidence scope. Correct generation/calculation не обещает quality/speed/human-hours gain; отрицательный016 result сохраняется честно. Root code, new dependencies, runtime authorization и fit budget этим design не выданы.
