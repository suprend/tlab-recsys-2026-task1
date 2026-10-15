# metadata_ablation independent review — CHANGES REQUESTED

Дата2026-10-15. Scope: точный frozen ablation runner и tiny synthetic/mocked boundary checks; **0 actual matrices, native Pool, native fits, real source scans, actual approval writes**. Repo read-only. Ни actual008 models/scores, ни новые full009 outputs не читались. Control sealer/реальный114-pin record и будущие actual arrays этим review не приняты.

Frozen SHA256 до и после всей проверки:

| Файл | SHA256 |
|---|---|
| scripts/metadata_ablation.py | 380288844d7a2b5133acf9b1c29a92a33814d2a0e67a53826a6df73ed423372f |
| tests/test_metadata_ablation.py | d3a4a6a83c69acbb228733ea85acd8dcd2355cf664863d575bf76b8086d452d8 |
| docs/experiments/metadata-ablation.md | 6316e73ba72c931bc81a82fc4fd39b98c236833404f3125326a96f38bef24125 |

## P1 — terminal failure сохраняет ошибочное решение retain

`metadata_ablation.py:188–246`: обработчики resource→base41 и integrity/API→STOP находятся **внутри** `with ExecutionAudit`. Они не охватывают ошибки `ExecutionAudit.__exit__`, где проходят manifest/report persistence, final CPU/wall/RSS guards и receipt rewrite. К этому моменту `decision=retention(metrics)` уже записано в report (`:235–237`).

Независимые cases `runtime_terminal_resource` и `runtime_terminal_write` воспроизводят проблему на synthetic healthy trajectory с outcome retain=true. Full planning, Pool, model fitting mocked; synthetic4000 selection Q имеют несколько candidate rows, scores/evaluate/bootstrap исполняются реально, входы реальных коллекций не открываются. Это lifecycle fault, не оценка качества модели.

- Подменён writer только для `run.json`: MemoryError(`TERMINAL resource during manifest`). Run бросает исходный MemoryError, durable report `status=failed`, claim сохранён, mocked fit calls=1, **decision.retain_metadata_block=true / feature_choice=base41_plus_metadata18**. Ожидался base41/no replacement.
- Подменён writer только при final report `status=complete_produced_unreviewed`: OSError(`TERMINAL final receipt`). Исходная ошибка проброшена; durable failed marker имеет `status=failed`, но **то же retain=true**. Ожидался STOP/no replacement.

Shared reviewed audit корректно fail-closed по status и известному failed receipt; false-success acceptance не воспроизведено. Дефект — именно несогласованная durable pipeline decision и неполное покрытие принятой failure policy. Before execution approval нужна локальная terminal-failure policy, отражённая в durable failed receipt, с сохранением primary exception, secondary evidence и consumed claim. Не менять frozen shared full009 runtime незаметно: его producer/acceptance — отдельный scope. Recheck после нового exact freeze должен включать healthy retention, оба этих mutants и отсутствие retry.

## Что подтверждено в текущем scope

`verify_control` заново выводит unchanged008 plan через original `prepare_fit_plan`, сравнивает manifest identity/runID, проверяет фактические2complete50tree/checkpoint outputs, exact4CBM/NPZ paths, consumedclaim, executionapproval и3фиксированных independent proof paths. Required map складывается из expected dependencies и обязательных outputs, а не только из self-declared approval keys. На tiny freshly resealed approvals удаление source, третьего proof и PairLogit NPZ отвергнуто; версии true/1.0 и approved=1 отвергнуты. Свежепересчитанный manifest/claim SHA не спасает executionapproval с bool-version. Реальный expected103+11=114 map не открывался/не подтверждался этим harness; актуальный receipt обязан выпустить независимый sealer.

Plan использует strict canonical14 collection validation и accepted-full-export consumer, связывает его collection IDs с теми же train/selection, merge конфликтных pins запрещён; export consumer ре-выводит принятую100Q scope и full113 dependencies. CODE включает chunk loader, ablation, ranking metrics и reviewed full/core зависимости; old control pins содержат unchanged008 loader/environment lock. Config snapshot проверяется до/после control derivation; loaded/installed CatBoost/NumPy/DuckDB и pandas сравниваются с uv lock. Это static verified call path и synthetic scope evidence, не actual93/113 approval.

Global claim фиксирован по проекту и создаётся `open('x')` после exact executionapproval, до old/new/mixed matrix preparation. Own harness проверяет существование claim **в каждом** вызове chunk loader. Bad approved=1 не допускает ни claim, ни matrix, ни mocked fit. Audit attempt directory появляется раньше approval/claim для failed-attempt evidence; model outputs/matrix preparation до consumed claim не производятся. Immutable runID directory плюс fixed claim исключают бесплатную смену proposal/output directory. Resource preparation failure сохраняет claim/count0/base41; integrity failure — claim/count0/STOP.

Оба role проходят unchanged008 reference→chunked BASEONLY exact comparison→mixed base-prefix exact comparison. Собственная числовая мутация BASEONLY отвергнута до fit. Saved control NPZ требует exact field set/group/product keys; мутация keys либо fullY metrics отвергается после claim, **до fit**. Sampling/fullY/NaN/BIGINT transformation independently принят отдельным model_data review; текущий runner дополнительно требует6000/4000Q и exact frozen names. Actual selectedTRAIN encoded4096 gate вызывается до nativePool. Future016 arbitrary columns здесь не разрешаются:56numeric фиксируются через accepted collection/control/schema и fixed15+3; unsupported grammar не реализована.

Fit один Logloss50 с fixed depth6/LR.05/L2=3/seed2026/CPU2/Plain/bootstrapNo/Newton10/AnyImprovement/randomstrength1/boostavgFalse; без eval_set/OD/best model. Row weights1/|Cq| сохраняют allnegative/allpositive группы. FeaturesData имеет explicit numeric/categorical names; train/selection Pool и prediction явно2threads. After fit проверяются ровно1attempt, model feature order,50trees/effectiveparams against control и отсутствие features_info.ctrs/OnlineCtr в saved JSON. Native API behaviour на реальных данных не проверялось.

External006 fullY four estimands и paired user bootstrap вызываются без insertion positives. Strict retention Recall≥.5792133072407045 AND NDCG>.41444755081727774+1e−12 реализован правильно; ties/worse→base41. Screening CI не объявляется post-selection valid superiority. Final input/executionapproval re-pin выполнен; исключения native API в основном body ведут STOP, неизвестная native RuntimeError не выдаётся автоматически за OOM. Terminal-policy defect выше остаётся единственным обязательным изменением, найденным в этом review.

## Evidence и ресурсная граница

14 собственных cases завершены PASS как assertions наблюдаемых результатов; **два PASS доказывают P1 defect**, это не14passed product acceptance. Helper `tlab-metadata-ablation-independent-faults.py`, raw `tlab-metadata-ablation-independent-results.json`:2.016343wall/1.955644CPU, peakRSS135921664bytes; эти internal counters начинаются после imports. Scoped author13 tests reproduced PASS, unittest0.666s; fresh child0.835498wall/0.615005user+0.118077systemCPU/RSS139247616bytes, включая imports. Native fitting и nativePool creation замоканы во всех случаях; FeaturesData construction разрешён и выполнен synthetic-only.

Raw author replay: `tlab-metadata-ablation-author-tests-replay.json`. Файлы review/harness не перезаписывают предыдущие evidence. Runtime budget1200wall/900actualCPU/cooperativeRSS8GiB покрывает body stages и reviewed audit persistence boundary; fresh-process imports/minimal final receipt/stdout tail требуют внешнего parent ledger, не превращаются в нулевую стоимость. Actual fit approval и acceptance полностью pending.
