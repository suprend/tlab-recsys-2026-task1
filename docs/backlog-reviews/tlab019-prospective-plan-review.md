# TLAB019: независимый critic prospective GridC

Вердикт: **направление GridC допустимо; changes_requested к двум правилам gate/fallback до code approval**. Это bounded review плана, не разрешение четырёх новых fits, full26000gate или016. Прочитаны round010 raw note, текущий backlog,008aggregate и relevant loader source. Counterpart review не читался. Fits, real scans, data/code/acceptance writes не выполнялись; создана только эта временная записка. HYP105/106 остаются reserved.

## Почему выбранный scope честнее исходного objective grid

Предлагается Logloss depth{4,6}×L2{3,30}, LR.05, максимум300trees, external checkpoints50/150/300: четыре attempts, максимум12новых looks. Это первый ограниченный tuning одного manual objective. Logloss выбран по уже просмотренному008screening; нельзя назвать выбор objective prospective blind или сравнение tuned BCE/PairLogit. Одновременно он устраняет необходимость притворяться, будто одинаковые libraryL2 сопоставимы между двумя различными рисками.

008aggregate подтверждает actual Newton10/AnyImprovement/random_strength1/boost_from_averageFalse/Plain/bootstrapNo, также score_functionCosine, border_count254, nan_modeMin, SymmetricTree, seed2026. Все эти effective values нужно явно сохранить/pin, кроме объявленных depth/L2/iterations. AnyImprovement — backtracking leaf estimation по обучающему loss, а не validation early stopping; его сохранение совместимо с отсутствием nativeOD. [CatBoost common parameters](https://catboost.ai/docs/en/references/training-parameters/common).

Контроль после019 корректно называется «manual Logloss, выбранный bounded grid», с описанными ненастроенными осями. Четыре точки не доказывают global optimum/достаточный search. Исходная smoke-стоимость22.663swall/RSS1.788GB не даёт фактического CPU production и не позволяет умножением получить уверенный forecast300trees/fulltrain.

## P0.1: определить допустимый FAIL→6000

Один full26000no-fit gate и irrevocable выбор population по его результату — разумная prospective развилка. Но blanketFAIL→6000 смешивает разные причины.

- **Resource fail:** wall/RSS/остаточный CPU превышены при корректном pipeline — допустим заранее объявленный6000fallback, без повторного26000gate.
- **Full-population cardinality fail:** actual encoded train field>4096 — fallback допустим как объявленный выбор меньшей population, если на6000новый actual check проходит. Нельзя незаметно менять encoding/threshold или допускать CTR.
- **Semantic/lineage/API fail:** неверные keys/schema/flags/masks, изменённые pins, неполный addon, invalid Pool input — остановка и исправление/review. Уменьшение population не делает испорченный pipeline приемлемым.

Immutable gate identity, reason, partial costs и выбранная population фиксируются один раз project-wide. Нельзя повторять gate через другой outputroot. Успех выбирает26000для всех019arms и будущего сравнения016; ошибка любого fit после этого не переключает оставшиеся arms на6000. Решение не использует новые selection metrics. После006/009семантических gates отдельный approval всё равно необходим.

## P0.2: PASS означает ingestion, не гарантированную обучаемость

Gate должен включать реальные выбранные train arrays **и selection arrays**, их одновременную lifetime, labels/1-C weights, exactkey/order/schema, собственные NULL/UTF8/mask проверки и Pool construction без fit. Feature set окончательно задаётся009decision: если блок отвергнут, не навязывать mixed59schema; sizing ниже относится к варианту56numeric+3nominal.

Для accepted5317058train rows числовой float32matrix56 требует1191020992bytes; три object-pointer columns на64-bit —127609392bytes. Selection817149rows добавляют183041376+19611576bytes. Это нижняя граница buffers: не включены Python bytes payloads, labels/weights/indexes, DB intermediates, temporary lists/copies, Pool holdings и training workspaces. Особенно опасно масштабировать009`fetchall()` без изменения physical loader: Python tuples/objects могут доминировать. Предпочтителен reviewed batch/preallocation путь с измеренной peakRSS; это предложение, не speedup claim.

FeaturesData требует float32 numeric и object UTF8 categorical и не выполняет полного собственного validation. Порядок numeric→categorical одинаков на train/inference. [Tagged FeaturesData docs](https://github.com/catboost/catboost/blob/v1.2.10/catboost/docs/en/concepts/python-features-data__desc.md). В source1.2.10 Pool передаёт thread_count в in-memory builders; feature-order путь удерживает исходный FeaturesData и делает arrays readonly. Нельзя предположить, что `del` локальной ссылки освободит весь buffer. `Pool.get_features()` поддерживает только numeric-only, поэтому им нельзя проверять mixed roundtrip. [Tagged Cython source](https://github.com/catboost/catboost/blob/v1.2.10/catboost/python-package/catboost/_catboost.pyx#L4107-L4382).

Actual count≤4096 включает sentinels и **все encoded values выбранного train**, а не100Qsubset/raw metadata/selection union. В Pool сверяются shape/names/categorical indices/weight alignment. Pool construction ещё не проверяет будущие numeric quantization, Newton10/backtracking/one-hot training allocations и runtime300trees. Поэтому каждый разрешённый fit сохраняет RSS/CPU/wall stop gates; PASS не обещает четыре завершённых fits. В уже разрешённом fit проверяются effective one_hot_max_size4096 и model JSON CTR evidence, без дополнительного proof fit. [Categorical documentation](https://catboost.ai/docs/en/features/categorical-features).

## Критерий выбора и честная статистическая граница

Recall guard относительно pinned008Logloss сильнее popularity guard и соответствует сохранению уже достигнутого development поведения: threshold=`0.5812133072407045−0.002=0.5792133072407045`. Pin должен включать exact008model/scores, selectionQ/C/fullY,006evaluator/version и estimand, а не только скопированную цифру. Guard — point-estimate feasibility policy, **не доказанная noninferiority** при73positive queries.

Сначала eligible semantic/resource/Recall checkpoints, затем максимум external conditional macro-query full-Y NDCG20; ties — меньше trees, depth, configID с заранее объявленной tolerance. Y внеC остаётся misses, zero-purchase Q остаются в secondary estimands. Если ни один checkpoint feasible — noeligible019winner; нельзя ослабить guard, перейти на popularity reference или добавить fit. Нужно также заранее описать случай, когда лучший feasible NDCG ниже008smoke: сохранять008 как известный reference/report limitation, не объявлять degradation улучшением и не прятать более сильный manual result при будущем016claim.

Имеющиеся development looks007/008, будущий009ablation и12новых019looks ведутся в общем журнале истории, хотя бюджеты задач различаются. Три checkpoints одного300-tree fit не три fits, но три selection choices. Failures расходуют attempt; failed partial checkpoints не становятся eligible без заранее принятого правила. Нельзя получить четыре успешных fits за неопределённое число retries. CI/bootstrap после winner selection не устраняют adaptivity, power guarantee отсутствует.

## Бюджет, API и chronology до исполнения

Old008validator ограничивает6000Q/1.32mrows и остаётся immutable;019нужен отдельный reviewed plan/code/identity с фактическими большими caps. Ровно один26000gate≤10minwall/2threads/RSS8GiB, его prep/cardinality/Pool/oracle/failures, все fits, checkpoint prediction/scoring/serialization входят в предложенные≤60**actualCPUminutes**, не добавляются сверху. Actual user+system родителя и reaped children суммируются без двойного учёта per-worker metrics; running worker/kill требует измеряемой partial cost. Wall×threads не является CPU. [Python resource API](https://docs.python.org/3/library/resource.html).

Остаточный CPUcap может остановить phase до четвёртой конфигурации; порядок четырёх попыток фиксируется заранее, а исчерпание не выдаётся за полную grid. PASSfullmatrix не открывает016 автоматически: его exact3physicalcolumn arms/owncost gates/shared2CPUh остаются отдельными, при той же population. Общий исторический6CPUh remainder нельзя вывести из wall-only017/008production.

Grid/population/Recall policy фиксируются до009metrics; после009замораживаются feature manifest и accepted addon lineage. Confirmation25-only остаётся отдельным calendar proposal: реальные selected-model/decision availability должны предшествовать первому anchor, с положительным compute gap. Final26+ не помогает принять сетку. При отсутствии019code/current exactapproval разрешения на новые fits ещё нет; новый четырёх-fit budget должен быть явно принят после измеренного smoke.
