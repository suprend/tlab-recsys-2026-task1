# Round068 — portability contract: одинаковые actions не означают одинаковый B41

**Actionable schema-only adapter assessment, 15 октября2026.** Сопоставлены Retailrocket и Taobao UserBehavior с current005/016. Дедуп [031](round-031.md), [036](round-036.md), [040](round-040.md), [052](round-052.md): новое уточнение — **partial equivalence category-free primitives против допустимого различия metadata features**. Архивы/CSV/download endpoints, actual data/models/WIP не читались; jobs отсутствуют. Ни implementation, ни измеренное качество/переносимость не заявляются.

## Primary facts и неизвестное

[Publisher Retailrocket card](https://www.kaggle.com/retailrocket/ecommerce-dataset/home) проверена через индексированный текст того же URL; прямое представление пустое. Карточка описывает events(timestamp,visitorid,event,itemid,transactionid), properties(timestamp,itemid,property,value), category tree; actions view/addtocart/transaction. Property history получена из weekly snapshots удалением consecutive unchanged values. Раскрыты categoryid/available; остальные properties anonymized, не доказанные brand/price/title. CC BY-NC-SA4.0 — card claim. Пример Unix timestamp совместим с milliseconds, но формальная unit/availability guarantee не найдена. File contents/completeness не обследовались.

[Tianchi649](https://tianchi.aliyun.com/dataset/649) снова возвращает только заголовок. Не подтверждаю точные dates, units/timezone, size/license или полный publisher action dictionary. [Alibaba NANN README](https://github.com/alibaba/nann/blob/master/README.md) связывает demo с UserBehavior; [author converter](https://github.com/alibaba/nann/blob/master/NANN_impls/nann/data_provider/convert_UB_to_tfrecord.py), observed public master без immutable SHA, читает пять позиций user/item/category/behavior/time. Он игнорирует behavior и перезаписывает item→category по всему входу. Это подтверждает формат потребителя и показывает несовместимый для нас preprocessing, но не доказывает publisher completeness. pv/cart/buy mapping ниже — **proposal до подтверждения первичной семантики**, не установленный факт карточки; fav не подменяется cart.

## Compatibility obligations

| Предпосылка005/016 | Retailrocket | Taobao UserBehavior |
|---|---|---|
| Raw countable bag | Event rows; transactionid не доказанный eventID; duplicates сохранять | Пятиколоночные rows; tuple(user,item,time) не доказанный PK |
| Clock/global peers | Units/UTC и available-time policy объявить; timestamp ties не упорядочивать rowid | То же; integer/string timestamp без unit annotation недостаточен |
| Historical event category | Нужен declared as-of-event join к PropertyState | Event-attached category при explicit availability assumption |
| Current category | Latest eligible bucket отдельно на(item,property), carry-forward наблюдённого state | Current005 latest global past event bucket; не whole-file map |
| Candidate domain | Prior-observed events proxy; properties-only items/available flag не автоматически C | Domain трёх mapped actions; fav-only history отдельно либо исключена явно |
| FullY | Distinct transaction-items[t,t+H), не orders/fulfilled units | Distinct buy-items — после подтверждения action semantics |
| Maturity/coverage | Нужны declared complete source interval/delay, не min/max timestamps | То же; короткий/unknown calendar может не вместить наш split |

Available=1 — наблюдение state, не доказательство stock на всём промежутке между weekly snapshots. Добавить properties-only items в C или фильтровать Y по available означало бы изменить retrieval/target protocol. FullY вне C остаётся miss; zeroY и emptyC Q сохраняются. Brand/price/code и unavailable action — unsupported, не zeros. Event-time-as-availability — явное offline допущение, не online guarantee.

## Минимальный future adapter contract

Три roles из040 достаточно: EventFact(countable bag), PropertyState(noncountable update), Query(Q/C,time). Contract фиксирует source/schema identity, nominal exact keys, source units→UTC, action predicates и excluded tokens, observed coverage, event/state availability, multiplicity, metadata grain/tie/NULL rule, history `[S,t)`, windows `[t−W,t)`, target `[t,t+H)` и maturity. При unknown availability либо отказ от строгого knowledge claim, либо заранее названное offline assumption.

PropertyState **не превращается в view/cart/purchase**. Historical event category вычисляется по отдельной утверждённой knowledge-at-event policy; current category — knowledge-at-query. Late metadata не может задним числом заполнить прошлое. Known+NULL в последнем допустимом bucket даёт unknown, без older-backoff; per-property carry-forward не равен current005 global-event-bucket resolver. Для current generator exact canonical schema/bindings required: field renaming/new metadata backend fail closed. Это future adapter seam, не drop-in возможность current016.

## Одна source-free fixture,22input rows,0fits

Предложить source bounds S=T−9d, complete_end=T+4d, H=24h. EventFact10rows: U2/I20/cart вT−8d; U1/I10/cart вT−2h; два exact duplicate U1/I10/view вT−1h; U2/I20/view и U2/I50/view вT−1h; U1/I10/cart ровноT; U1/I30/purchase вT+1h; U1/I20/purchase ровноT+H; U3/I40/fav вT−30min как excluded/unsupported channel witness.

PropertyState6rows: I10/categoryA вT−3h иB вT−30min; I20/categoryA иNULL одним bucketT−4h; I30/categoryC вT+30min; I50/categoryA observed вT−2h−1min, available толькоT+10min. Остальные state rows доступны при их stated time. Q3: (U1,T),(U2,T),(U1,T+2d). C3: первойqueryI10/I20, второйI20, третьяempty. Keys включая≥2^60 задаются exact integers в отдельном rename variant, без float conversion.

Literal expected obligations: pair(U1,I10) count24(view,cart,purchase)=(2,1,0), distinct viewed items=1. U2/I20 cart recency=691200s при cart24=0; globalT peer не попадает ни в чью историю. Первая fullY={I30} внеC; purchase наT+H исключён. Вторая/третья mature zeroY сохранены. Fav-only U3 не получает known view/cart activity из fabricated zeros.

**Критический non-equivalence gold:** у I10 нет события послеT−1h. Embedded-event categoryA остаётся последним past bucket; Retailrocket propertyB наT−30min уже доступно доT. Current category A противB — правильное различие observation contracts, не adapter bug. I20 mixed-NULL property bucket unknown; I50 late state unknown наT. Нельзя требовать равенства category shares/current cohorts двух encodings, скрыв различную информацию. Сравнивать равенство category-free counts/distinct/recency и отдельно literal metadata expectations каждого backend.

## Claim и backlog reconciliation

Успешный future drill подтвердит typed transport, bag/clock/NULL/metadata semantics на22literalrows; не полноту файлов, реальную cardinality/cost, matching B41 или predictive quality. Для отчёта сейчас допустимо «проведён source-backed compatibility analysis; synthetic adapter test предложен, перенос не выполнен».

Это refinement HYP-002/TLAB-016 generation contract и TLAB-005 semantics; независимая проверка относится к existing018 capability scope, taxonomy IDs/readable labels — к010, source research — к014. HYP046 про compute equality/speed не превращается в portability-quality claim. **Новых tasks/HYP/бюджетов нет:** сначала закончить current reproduction/report; future adapter требует своего review и не меняет нынешний legal pool/12cols/4fits.
