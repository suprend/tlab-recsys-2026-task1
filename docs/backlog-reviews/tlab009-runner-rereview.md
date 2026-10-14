# TLAB009 runner: targeted P1 re-review

Вердикт: **ACCEPT CODE ONLY на exact newfreeze ниже.** Воспроизведённый P1 terminal resource seal устранён. Это re-review ограниченной правки, не actual100Q executionapproval, source/cost/data acceptance, full export или fit permit. Реальные source/Q/Y/C/F/model files не читались, fits0; production files не изменялись. Старые review/harness/results сохранены отдельно без перезаписи.

| Файл | SHA256 |
|---|---|
| scripts/metadata_price_features.py | 596f137e5f41649c99c568f03333e1517bc1a72b9e1dfbf7d51d8a881fa652b4 |
| tests/test_metadata_price_features.py | e3d92fc1a8497bdd0a758a1e6ea41aa9a6b234788e7fcf5c1fd52e5ca590d11d |
| configs/features/metadata-price.json | 20c11d9bc2e752816c07fe894e975a93a94fd81926ce5de20e250c31283fa2b8 |
| docs/experiments/metadata-price-features.md | 09289f58018163398062a78d50ed527ee81d809bc0ae98d5cba4017c5c53bbd7 |

Новые pins совпали до и после проверок. [Исходный changes-requested review](tlab009-runner-review.md) сохранил SHA256 `3dc9883fe94c22a204fd7bf2171e47f0548de85463b20f1a69e26145d0831b48`; его finding относится к прежнему fa4172/b170freeze и не удалён.

## Проверенная правка

Finalization теперь собирает terminal cleanup/CPU/manifest errors, переводит status в failed, сохраняет terminal_errors и повторно выбрасывает ошибку. Если уже была первичная ошибка, её reason/exception сохраняются; secondary close error остаётся отдельным audit evidence. Guard вызывается после connection close/CPU read/manifest serialization, а затем ещё после report write до успешного return. Поэтому прежний успешный SQL stage больше не достаточен для окончательного complete при late resource violation.

Воспроизведены **те же исходные probes**, без sleep/больших allocations: close добавляет700 к fake monotonic либо поднимает измеряемый RSS до8GiB+1. На новом freeze оба сохраняют failed и выбрасывают соответственно TimeoutError/MemoryError. Report retains elapsed700.3513s иRSS8589934593 для diagnosis; это injected counters, а не реальная стоимость теста.

## Независимые regression/fault результаты

Отдельный [re-review harness](tlab009-runner-rereview-harness.md) создан из сохранённого исходного harness, с новыми pins/отдельным result path и дополнительными assertions. [Новый evidence JSON](tlab009-runner-rereview-results.json) содержит10cases:

- Один healthy synthetic baseline:100Q на13days, exactbalanced8×9+7×4, independently recomputed query-key hash,200pairs и4exports; complete_produced_unreviewed.
- Девять fault cases: late-close wall/RSS, terminalCPUfailure, partialexport, helperdrift послеapproval, close error, primaryexport+close error, manifest write error, late audit-write wall overrun. Все failed, successful return отсутствует, exceptions сохранены.

В primaryexport+close case наружу вышла исходная `injected independent export fault`; она же осталась report.error. `injected terminal close fault` сохранена в terminal_errors. В audit-write probe первый auditwrite добавляет fake700seconds; post-write guard переписывает report в failed и не возвращает success. Частичные outputs при ошибках не скрываются и не принимаются.

Собственные fixtures — synthetic DB/Parquet/mock approvals только под temporary directories; verify_collection transport mocked, поэтому это не повторное доказательство actual017 acceptance. Независимые expected source features в этих transport tests не вычислялись; pure-core direct-list/source checks остаются отдельно. Никаких реальных approvalfiles не создавалось.

Полная текущая scoped suite28tests также независимо воспроизведена: **PASS, unittest1.640s**, включая три добавленных author regressions. Own fault suite measured actualwall3.7761s, user2.596757s/system1.623610s, peakRSS152256512bytes. Fake700seconds не включаются в actual runtime. CPU author-suite отдельно не экспортировался; не объявляется точный totalCPU всего review.

## Сохраняющиеся границы

Code acceptance распространяется на train-only100Q diagnostic runner: exactexternal approval, unchanged accepted collection/source lineage, fixedscope/caps, immutable outputs, no labels parsed/no Pool/predict/fit и complete_produced_unreviewed после успешного terminal seal. Она не заменяет coordinator exactplan executionapproval.

Actual100Q run затем требует независимой reconstruction full latest global buckets, past dictionary, **полного outsideC R** и всех selectedpair3nominal+15numeric с declared float tolerances. Source-oracle scalability preparation пока только PLAN; tiny fullprefix×products oracle не запускается на42m. Full exports, full-train4096/cardinality/CTR evidence, mixed59-input integration и ≤1Loglossablationfit требуют отдельных gates. Повторный runner запуск/новый namespace не становится бесплатным retry.
