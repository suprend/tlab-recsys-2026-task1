# Research lab, round026: маленький common legal pool для016

15 октября2026. **Proposal, не implementation или execution approval.** Прочитаны continuous research context, актуальный [backlog](../backlog.md), [compiler005](../../scripts/manual_features.py), [registry](../../configs/features/manual-18.json) и опубликованный [B41 schema](../backlog-reviews/tlab008-smoke-aggregate.json). Compiler/Pool/fits/tests/materialization не запускались; code/data/deps/Root artifacts не менялись. HYP137/138 предлагается оставить reserved refinements HYP002/closure, без новой novelty quota. Ниже конкретизация уже разрешённого направления, а не новое predictive family.

## Первичные основания и actual seam

[DFS2015, авторский текст](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) обосновывает программы по relational paths и field types; [ExploreKit2016](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf) отделяет generation от learned candidate ranking и classifier evaluation; [OpenFE2023](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) обучает FeatureBoost и выполняет pruning/attribution. Заимствуются разделение definitions/calculation и явная стоимость отбора. Их learned selectors, recursive vocabularies и published benchmark gains здесь не реализованы. Static intelligent rule ниже не называется ExploreKit/OpenFE, не имеет скрытых proxy fits.

005 принимает1–64 definitions, шесть grains, count, exact count_distinct по user_id/product_id, observed recency и matching-count shares. Auto output добавляет coverage каждой integer-window, recency/ratio missing flags и missing flags для category-conditioned cores. Метаданные/age/context и inherited C fields также присутствуют. Closure считается **относительно полного frozen model B**, а не только18 names: принятый008 имеет41 numeric input, уже включая retrieval flags/scores/ranks/age. Если009 retained, финальный019 schema тоже входит в dedup gate.

## Signature и два выявленных duplicate traps

Каждый core имеет signature `(source/protocol/context,grain,keys,event,operator,projection,window/endpoints,rawbag/unique,unit,metadata/null/availability policy)`. Для pool ниже общий contextΓ: одна accepted Q/C population, global `<t`, source `[S,t)`, counts `[max(S,t−W),t)`, category rules005, exact integer/NULL до modelfloat32. Префикс имён не создаёт новизну. Обозначения: U=user, P=user×item, I=item; N=count, D=distinct по явно указанному key, R=recency_seconds по observed prefix.

**Trap1:** `D(I,purchase,168h,user_id)` совпадает с retrieval `popularity_distinct_users`, включая recent-only candidates после полного popularity join. Он исключён. Raw item purchase168h не alias этого distinct count.

**Trap2:** новый category-count missing flag совпадает с B `candidate_category_missing`: known category coalesce count0, unknown category→NULL. При этом005 физически автоматически выдаёт новый именованный flag. Нужно различать semantic alias и actual emitted column; без отдельно reviewed reuse/projection нельзя считать его бесплатно исчезнувшим. Аналогично72h coverage на accepted anchors≥8Oct/source1Oct равен1, как B coverage24/168: context-bound duplicate, а не найденная sample correlation. Поэтому naive72h two-count+coverage bundle и category-count/share bundles пока **deferred из первого pool**. Это уточняет ранние примеры009, не исправление pinned005.

## Proposed fixed pool: восемь whole bundles

Во всех строках integer windows только24/168h, поэтому existing coverage переиспользуется. Некатегориальные counts/distinct не создают missing flags. R создаёт ровно один новый value и один новый missing flag. Registry мысленно расширяет B definitions; ниже перечислены только **три новые physical model/output columns**.

| ID | Exact new closure |
|---|---|
| L01 | N(U,view,24h); N(U,cart,24h); N(U,purchase,24h) |
| L02 | N(P,view,24h); N(P,cart,24h); N(P,purchase,24h) |
| L03 | N(I,view,168h); N(I,cart,168h); N(I,purchase,168h) |
| L04 | D(U,view,24h,product_id); D(U,cart,168h,product_id); D(U,purchase,168h,product_id) |
| L05 | D(I,view,24h,user_id); D(I,cart,168h,user_id); D(I,purchase,24h,user_id) |
| L06 | R(P,cart,observed); его missing flag; N(I,cart,24h) |
| L07 | R(U,cart,observed); его missing flag; D(U,purchase,24h,product_id) |
| L08 | R(I,cart,observed); его missing flag; D(I,cart,24h,user_id) |

Это proposal signatures, не новый JSON/API. Одинаковые values на конкретной выборке не объявляются aliases: например raw count и distinct buyers различаются при повторениях;24h и168h различаются при expiry. Recency-missing не alias recent retrieval missing или cart7d=0: old cart за пределами7d сохраняет observed recency. Все восемь bundles должны пройти final-B signature/closure review до выбора; отсутствие ровно3 новых columns закрывает этот prospective pool, без metric-driven repair.

## Механизмы, контргипотезы и один общий draw

L01/L02 различают короткую активность/намерение от7d totals; counter — это только recent-repeat/popularity proxy. L03 отделяет длинную item mass от24h; counter — head-item popularity уже объясняет сигнал. L04/L05 отделяют breadth/audience от multiplicity; counter — sparse uniques добавляют noise. L06–08 показывают cart timing и полный observed prefix; counter — view/purchase/retrieval recency уже достаточны. Это competing refinements existing counts/windows, без обещания качества.

Предложение static I1=L02,I2=L06 фиксируется сейчас по schema semantics. Random R1/R2 — uniform independent draws **с возвращением** из всего sorted L01…L08, включая выбранныеI bundles; PRNG/version/state/seed и pool SHA закрепляются до новых metrics. Collision/invalid/duplicate consumes attempt, без redraw/refill. Нельзя заранее удалить I winners только из random pool или после score заменить неудачный bundle. Общее≤12 новых columns/≤4 fits/≤2CPUh; shared calculations/cache могут переиспользоваться с видимым ledger, но не создают дополнительную попытку. Две random draws не доказывают превосходство стратегии.

## Exact future synthetic closure-check protocol

Только после отдельного review: ≤32 input rows суммарно,0fits. Symbolic phase проверяет все восемь closures без вычисления features; numeric phase исполняет только уже frozen выбранные bundles, максимум12 новых columns, не198 candidates. Fixed T=10Oct00/S=1Oct; raw fixture: UviewX−1h, два одинаковых UcartX−2h, UpurchaseX−3h, VcartX−8d, VviewY−2h, VpurchaseY−25h, UcartY ровноT и UpurchaseY послеT. Две Q вT с C={(U,X),(U,Y),(U,Z),(V,X),(V,Y)} плюс две eligible Q следующего дня с emptyC; source/metadata annotations заданы literal, Z unknown.

Literal anchors: L02(U,X)=(1,2,1), L02(V,Y)=(1,0,0); L06(U,X)=(7200,false,2), L06(V,X)=(691200,false,2), L06(U,Y)=(NULL,true,0). EmptyC Q сохраняются вQ coverage, F ровно5 physical rows; labels в generation/closure не читаются. Проверяются exact emitted delta schema, integer/BOOLEAN types, NULL masks, frozen-B alias rejection, lower boundary/expiry, duplicates, global peers/future suffix и old-prefix recency. Остальные выбранные signatures требуют собственных literal expected rows до исполнения, без producer-derived oracle.

Провал closure/schema/source — STOP, не fit failure rescue. Independent formula coverage и resource/evidence gates нужны отдельно: manual18-only acceptance018 не удостоверяет новый registry автоматически. Primary contrast остаётся full-Y против точного tuned B с одинаковыми019 settings/population; selection history/confirmation lock сохраняются. Сейчас не выданы execution budget, code changes, новый operator, quality/speedup claim или human-hours benefit.
