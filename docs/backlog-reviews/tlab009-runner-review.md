# TLAB009 frozen runner: independent substantive review

Вердикт: **CHANGES_REQUESTED — один воспроизведённый P1 до real100Q approval.** Pure-core acceptance остаётся в своей прежней границе; новый runner не принят для исполнения, source/cost/model acceptance не выдавались. Counterpart review не читался. Прочитаны весь runner/test/spec/docs, archived runner proposal/coordinator design review, reused008 collection-verification interface и StageLedger/RunDeadline/hash helpers. Реальные source/Q/Y/C/F/model files не читались; fits и repo writes отсутствуют. Все fault fixtures создавались/удалялись только в temporary directories.

## Exact reviewed freeze

| Файл | SHA256 |
|---|---|
| scripts/metadata_price_features.py | fa4172acc1a45487ca0083cbe3c1a141acb2f66dd847fd85bdfd133f439b9d09 |
| tests/test_metadata_price_features.py | b170838de52ca08d734bdb4b7cb8478d76e81c8b120d0c911bcf99cc56974206 |
| configs/features/metadata-price.json | 20c11d9bc2e752816c07fe894e975a93a94fd81926ce5de20e250c31283fa2b8 |
| docs/experiments/metadata-price-features.md | e16cb7b647fe7b5c0823a6273f995d610d52f2b6bc99d7918b27c781b6603b4b |

SHA проверены до/после fault suite. Авторские25tests независимо воспроизведены: PASS, unittest1.316s. Это не отменяет дополнительный дефект ниже.

После подготовки этого отчёта заключительный read-only hash check обнаружил начавшийся repair: code596f137e5f41649c99c568f03333e1517bc1a72b9e1dfbf7d51d8a881fa652b4/tests e3d92fc1a8497bdd0a758a1e6ea41aa9a6b234788e7fcf5c1fd52e5ca590d11d. Это **новая, здесь не принятая ревизия**. Результаты и finding выше/ниже относятся только к исходному fa4172/b170freeze; для repair требуются отдельный exactfreeze и re-review. Старое evidence не переписано.

## P1: complete seal не проверяет terminal cleanup resource usage

После `reverify_all_reviewed_inputs` runner присваивает `complete_produced_unreviewed`. Затем в `finally` отменяет timer, закрывает DuckDB, измеряет totalCPU/wall/RSS и сохраняет report/run.json. CPU measurement failure корректно переводит результат в failed, но превышение deadline/RSS/spill в terminal cleanup не проверяется. Указанный scope обещает total600wallseconds/8GiBRSS включая preparation/export; `cooperative` допускает обнаружение после операции, а не complete при явно нарушенных финальных counters.

Независимый [fault harness](tlab009-runner-fault-harness.md) оборачивает только `con.close()` на synthetic DB. Без sleep или большой аллокации:

1. После настоящего close fake monotonic получает+700seconds. Runner возвращает успешно и записывает **complete_produced_unreviewed при seconds700.355793**.
2. В отдельном процессе того же fixture после close измеряемый RSS заменяется на8GiB+1. Runner снова возвращает complete и записывает **process_peak_rss_bytes8589934593**.

Результаты сохранены в [JSON evidence](tlab009-runner-fault-results.json). Это deterministic fault injection в конечный resource boundary, не утверждение, что реальное закрытие DuckDB занимает700секунд или выделяет8GiB. Оно показывает, что terminal resource violation не препятствует seal. Похожий fault totalCPU measurement в той же точке, напротив, правильно сохраняет failed и выбрасывает ошибку.

Минимальный требуемый repair: не повышать статус до complete до terminal cleanup/финальных counters; после close применить deadline/RSS/temp checks, сохранить failed audit и не возвращать successful report при нарушении. Report/manifest finalization также должна иметь явно описанную timing boundary; не требовать невозможного OS hard-kill. Добавить regressions для late-close clock/RSS, terminalCPUfailure и сохранения первоначального exception/partial artifacts. Новый exact freeze нужен до re-review; старые failed reports/outputs не переписывать.

## Что проверено и выглядит корректно

**Identity/authorization.** Public prepare_gate_plan остаётся proposal-only. Existing008verify_collection проверяет внешние accepted pins, source/config/registry/code bindings, exact shard refs и prior child seals. Runner train-only/lockfalse, sourcepath/bounds берёт из verified collection; spec snapshot bytes/body и reused/new code/lock входят в fingerprints. External gate approval требует exactscope/runID/pins/schema/types. Internally refreshed pins не становятся approval. Конечный rehash включает все approved inputs и сам approvalfile; altered input препятствует complete.

**Immutable attempts.** Fixedroot artifacts/metadata-price, audit создан до plan/environment/DB work. После exactapproval directory получает runID; повтор существующего ID отвергается и сохраняет старые outputs, ранний failure остаётся отдельным attempt. Нет полномочий на fullphase/fit или configurable expanded caps. Отчёты preparation failures оплачиваются отдельно и не считаются бесплатными retries.

**Selection без labels.** Query sample читает только accepted Q: SHA256(query_id)/queryID rank внутри anchor, затем dayrank/anchor/queryID global ordering LIMIT100. Независимый synthetic fixture13days×12Q подтвердил **8Q на первых9days и7Q на последних4**, exact query-key SHA пересчитан отдельным Python ordering. Unequal-day handling/label-invariance покрыты авторскими tests. F pairs присоединяются SEMI JOIN к выбранным Q; core проверяет key/category identity и22000cap до model-array allocation. Accepted train label bytes могут хешироваться verify_collection, но target relation для feature computation не создаётся.

**Output boundaries.** Exact20feature columns, provenance16columns и fullR4columns проверяются по именам/типам/порядку, keys bidirectionally, duplicate/orphan/reference/membership/strict-past resolution boundaries. Model arrays retain declared NaN/masks/UTF8 namespaces. Cardinality100Q — только diagnostic, не full-train4096/CTR proof. Separate features/provenance/fullreference exports нужны последующему independent source oracle; сам report пока produced_unreviewed.

**Resource/accounting.** Persistent deadline+SQLinterrupt,2threads/requested2GBengine/2GiBspill и cooperative8GiBRSS gates действуют между этапами. Actual process user+system измеряется отдельно от wall. Nested stage CPU overlaps не складывать: authoritative total задаётся process delta. No Pool/predict/fit вызывается. Engine memory_limit не является hard RSS guarantee. Finding выше касается именно final boundary после последней cooperative проверки.

## Дополнительные независимые faults

Собственный harness использует synthetic source+Q/F Parquet и mock acceptedcollection transport под temporary directories; mock не выдаётся за повторное доказательство всего017semantic acceptance. Production expected values/source semantics здесь не подменяются этим mock: они уже отдельно исследованы pure-core list oracle, а actualsourcegate ещё закрыт.

Из шести собственных cases baseline завершился с100Q/200pairs и4exports; helperbyte drift после approval отвергнут до DB/export; injected provenance-export failure сохранил failed иpartialqueries/features; finalCPUcounter fault сохранил failed/NULL CPU/error. Два terminal resource cases выявили P1. Фактическая стоимость всего fault harness≈2.219wallseconds, user1.565629s/system0.936922s, actualpeakRSS151470080bytes. Число700s — injected reported elapsed одногоfault, не израсходованное wall/CPU. Fits0; реальные approvals не создавались.

## Следующая граница

После repair/newfreeze/re-review coordinator может отдельно рассмотреть exact executionapproval одного100Qgate. Даже successful real runtime ещё требует всех selectedpair3nominal+15numeric и полного outsideC R source/list oracle. Scalable source-oracle PLAN сохранён отдельно в [source-oracle design](tlab009-actual-source-oracle-design.md); новый helper/actualextract пока не реализован/не исполнен. Full export, mixed59-input training integration, actualfulltraincardinality и единственный009Loglossablation остаются отдельными reviewed разрешениями. Pure-core test success и25runner tests не открывают эти scopes.
