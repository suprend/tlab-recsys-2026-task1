# TLAB-017: независимая приёмка train/selection collections

15 октября 2026. **Приняты обе реальные коллекции для008 smoke** после source/formula/provenance checks. Это завершает017, но не принимает008 training code/fit, не объявляет trained strong B и не открывает confirmation. [Runtime fault review](tlab017-runtime-review.md) и [re-review](tlab017-runtime-rereview.md) предшествовали исполнению. Новый dependency-lock не переписывает старые artifacts.

| Роль | Q | Positive Q | Full Y | C=F rows | Retrieved targets |
|---|---:|---:|---:|---:|---:|
| Train8–20 |26000|496|619|5317058|444|
| Selection22–23 |4000|73|96|817149|65|

Это immutable daily bottom-SHA sampling до labels, fixed200+20/no-refill, все зрелые zero-purchase queries сохранены. Targets вне C остаются misses. Число покупок ограничивает precision будущих comparisons; эти counts не означают качество ещё не обученной модели.

## Что независимо проверено

Для всех13+2UTCдней отдельный coordinator source oracle заново построил past-eligible population, exact bottom-SHA query set/IDs, eligibility/history counts/distinct/active-days/last-time/coverage и maturity. Production query helpers не использовались в формулах. Полный distinct Y реконструирован из source purchases с firsttime/rawcount/same-second/catalogseen/pairseen diagnostics; independent bidirectional relation comparisons дали0различий.

Для всех6134207candidate rows заново вычислены distinct purchase-user popularity7d, source ranks/ties, recentdistinct20 all-type last-times, union membership/no-refill/overlap flags и score даже для recent-only item. Каждый output row совпал, per-query target/source coverage reconcile. Train source verification49.139s/peakRSS995868672bytes, selection8.349s/1004896256bytes. Выданы6externalshardapprovals по14actualpins, только после этого runtime произвёл F.

Final F checks сверили каждый complete output/input/code/registry/selection/acceptance pin,45physical columns/18core, exactfullCkeys и8retrievalcolumns, queryuser/anchor, no duplicate keys, range/NULL rules. По78train и12selection source-selected verification pairs проверены18формул — **1620comparisons**: user/pair/item counts, exactdistinct, full-observedprefixrecencies/ages, latestglobalbucketcategory resolution, historicalitem×categorynumerator, fullcategorydenominator иshares. Verification sampling применяется только к проверке уже произведённого F, не к training/evaluation population. Tiny2-shard oracle предварительно прошёл Q4/Y2/C8/F8.

Feature verificationtrain9.906s/peakRSS2482683904bytes, selection2.556s/1277018112bytes. Full rowset checks exhaustive; numeric spotchecks не объявляются exhaustive numeric proof. Meaningful synthetic expiry/metadata/peers/suffix oracles приняты в005, producer code/hash unchanged.

## Реальная стоимость и lineage

| Роль | Q/C firstpass, s | F/aggregate resume, s | Cumulative invocation wall, s | Peak processRSS, bytes | Max reported enginebuffer, bytes | Engine spill |
|---|---:|---:|---:|---:|---:|---:|
|Train|40.0279|59.3348|99.3627|2702147584|3651680328|0|
|Selection|7.5820|12.1861|19.7681|2110455808|3143284808|0|

Обе роли использовали2threads, requestedengine2GB/spill2GB иcooperativeRSS8GiB/deadline gates; все recorded stages complete. Engine high-water выше requested2GB, поэтому hard memorycap claim отсутствует; причина counter/setting divergence не установлена. RSS gate пройден. Wall включает prep/cache/retries, межзапусковой reviewwait исключён; независимые проверки оплачиваются отдельно. Actual CPUuser/system seconds не были отдельно сохранены этим producer, wall не выдаётся за CPU time или точный остаток6CPUh.

Train collection `5fdc4dce06cac52a592e0ec8e77fb4631baf04f6170c347b51689098a4e8b918`; selection `c2c6ba099b4cffad131638cd33feba14db7232e78ced6c141a7f9c88d4c81b74`. External collection approvals pin82/30paths соответственно: exactstate/plan/namedcompleteattempt, source/config/newlock/producercode, allQ/C/Fseals, externalshardapprovals икаждыйdeclaredinput includingfeatureselectiondefinition. Physicalreports имеют complete_produced_unreviewed, а externalcoordinatorapproval — отдельный reviewed_development_collection scope; freshhash сам по себе неsemanticapproval.

Current sourceDBSHA `3575c76b9afec9be26f8a216b548c43b0dd837960a96aea739628f76dfe195b2`; uv.lock `4675021f74063889ffb596325b9e608a3a5776a29f967d052b86923e40485eab`; runtimecode `d3d811e7987812366d36163537bdd8784ccb55ef3e1596ba7bf6d02338f80f3c`. Approvals hash train `47b71f4ee8942c6b17508747f9f492e9b741707876934267e9b0d6cd31639903`, selection `45af326c2a71bbc0a12ba0753c0701dafc9e75d366150169a90aac164e51de7b`. Data/run/approvalfiles ignored, user/session IDs не публикуются. Послеseal новыйcache/resume меняетacceptedstate и требует новойreview; существующиеoutputs не перезаписываются.

Confirmation по-прежнему закрыта. Actual selection decision availability/positivecompute gap, strongB tuning, metadata009gate иautomation016 остаются отдельными задачами. Model code approval иявныйtwo-fit consumption permit требуются до любых real008fits.
