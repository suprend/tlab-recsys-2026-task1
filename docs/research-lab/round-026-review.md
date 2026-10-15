# Round026 independent static review — ACCEPT DIRECTION WITH EXPLICIT GATES

2026-10-15. Проверены raw026, actual005 registry/compiler и004 retrieval code. Compiler, tests, materialization, source/model reads, Pool и fits **не исполнялись**. Это принятие конкретного prospective pool как implementable design; не code/execution approval и не расширение016budget.

Скрытого четвёртого нового physical column или semantic duplicate с текущим B в L01–L08 не найдено. Принципиально важно, что вывод проверен по emitted closure, а не по числу definitions. В [manual_features.py:200](../../scripts/manual_features.py#L200) counts/distinct coalesce0; [flags:226](../../scripts/manual_features.py#L226) создаёт missing для recency/ratio/category-conditioned features. Некатегориальные count/distinct таких flags не создают. [coverage:207](../../scripts/manual_features.py#L207) выводит одну колонку на integer window;24/168 уже присутствуют в принятом manual18/B41.

| Bundles | Registry additions | Exact physical delta относительно полного B |
|---|---:|---|
| L01–L05 |3 count/distinct definitions|3BIGINT values;0новых masks;0новых coverage |
| L06–L08 |1observed recency+1count/distinct|1DOUBLE recency+1BOOLEAN auto `_missing`+1BIGINT value |

Model float32 conversion не добавляет columns и не отменяет source integer/BOOLEAN/NULL contract. Для L06–08 mask нельзя подавать как отдельный registry core с именем `_missing`: validator резервирует этот suffix, flag должен быть автоматически выведен из recency definition. Registry extension должна сохранять все18B definitions и exact inherited C/context; отдельный new-only registry не удостоверяет заявленную reuse closure. До выбора/исполнения нужен named schema-delta artifact против actual FINAL B, с уникальными safe names, а не только символическая таблица.

Все предложенные grains/actions/operators поддержаны [validator:21](../../scripts/manual_features.py#L21) и [_expression:114](../../scripts/manual_features.py#L114). Count означает raw bag rows; distinct — exact SQL distinct указанного user/product key, не сумму daily uniques; recency — максимум action timestamp на полном observed `[S,t)`, включая старше7d. Outer filter исключает все global peers вt; lower count boundary включена. Никаких новых log/threshold/nestedmean/learned operators этот pool не требует. Count0 при unknown Z здесь корректен для **безусловного item/pair/user grain**; NULL conditional-category semantics не подменены.

Оба duplicate traps подтверждены. [candidate_pilot.py:61](../../scripts/candidate_pilot.py#L61) считает purchase distinct users за7d, а final popularity join [на93](../../scripts/candidate_pilot.py#L93) распространяет score наrecent-only candidates. Поэтому D(item,purchase,168h,user_id) не новый feature. Новый category-count mask был бы exact alias candidate_category_missing, но compiler физически всё равно его выдаёт: отложить такой bundle до reviewed projection/reuse правильно.72h coverage=1 доказуемо только при объявленном source1Oct/anchors≥8Oct context; это не универсальная algebraic alias для других источников/ранних anchors.

Полная ручная проверка5candidate rows для выбранных staticI L02/L06 ниже. Это literal arithmetic, без запуска compiler; исходные пять опубликованных examples верны, но не заменяют полный expected rowset для каждого выбранного bundle.

| Pair | L02(view24,cart24,purchase24) | L06(cart recency,missing,item cart24) |
|---|---|---|
| U,X |(1,2,1)|(7200,false,2)|
| U,Y |(0,0,0)|(NULL,true,0)|
| U,Z |(0,0,0)|(NULL,true,0)|
| V,X |(0,0,0)|(691200,false,2)|
| V,Y |(1,0,0)|(NULL,true,0)|

Два UcartX duplicates увеличивают rawcount2; VcartX−8d=2Oct лежит послеS и даёт observed691200, но не count24. VpurchaseY−25h не входит24h; UcartY ровноT и futurepurchase исключены глобально. EmptyC queries следующего дня остаются вQ/coverage, не порождают Frows. Для случайно выбранных других bundles необходимы их literal expectations **до исполнения**, как уже требует026.

StaticI=L02/L06 использует schema prior; он не learned selector и не blind к человеческой истории007/008. Prospective freeze относится к следующим неизвестным outcomes. Uniform independent R draws с возвращением из полного sorted L01…L08, включая I choices, не противоречат общему pool: исключить I изR означало бы другой draw law. До freeze уточнить «collision» как semantic equality **whole3-column bundle** среди всех уже выделенных I/R slots; repeated draw потребляет slot без redraw/refill, с явным статусом до fit. Если предполагается иной collision scope, его надо принять заранее. Seed без pool SHA/order и PRNG/version/state недостаточен.

Ни одинаковые values на sample, ни overlap популярности/recency не доказывают прочие aliases: witnesses с repeated users и events24–168h их различают. Final-B alias/closure failure означает STOP, не metric-driven replacement bundle. Symbolic проверка всех8 допустима без вычисления8×3columns; numeric phase только frozen selected bundles≤12новыхphysicalcolumns. Fits/proposer/preparation/cache/failures/scoring остаются внутри исходных4attempts/2CPUh, без бесплатного learned ranker или replacement. Existing018manual18 acceptance новые definitions автоматически не покрывает. HYP137/138 остаются reserved refinements; quality/speedup/generalization claims пока отсутствуют.
