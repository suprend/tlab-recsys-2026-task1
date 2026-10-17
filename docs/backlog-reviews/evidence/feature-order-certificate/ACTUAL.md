# Wave099 B — synthetic representation certificate: actual PASS, review pending

Одна исходная попытка завершилась exit0/reaped (`3fd2bf`), без повторов, сигналов или ремонтов после запуска. Проверены **64 production registry materializations**, включая все L01–L08 в двух мирах и четырёх случаях. Это real compiler execution на вымышленных строках, без исходного датасета, labels, моделей или ML.

Предварительно запечатанные hand literals и отдельный row-list oracle согласованы до первого producer import/output. Проверены2688 raw-closure literal cells и2816 окончательных model cells. Для каждой projection удостоверены порядок44, SQL FLOAT всех колонок, float32 matrix1×44, NULL→NaN masks и две точные label-free source expressions из model_data/train_baselines. Полные Y-aware loaders не вызывались. Source projections основаны на supplied fixed candidates; retrieval не пересчитывался. В sensitivity last_user_event_time честно обновлён доT−1800s.

Во всех четырёх случаях — **352 межмировых cell comparisons**, всего1408; различий0. Row reversal и excluded global peers atT/futureT+1h дали ещё1408 within-world invariance cells. Все16 sensitivity checks изменили pair-view recency7200→1800s. Area literals: исходный/reverse/excludedH1=3,H2=1; sensitivityH1=1,H2=−1 — все8 выполнены. Поэтому финальные44 координаты каждого из восьми bundles на этой паре миров совпадают, а area различается. Area не добавлялась к модели и не оценивалась по target.

Один explicit generate_pool и одна allocate_slots; последняя внутри повторяет generation для проверки identity, поэтому фактически2 generation calls, один pool/одна allocation,0search/redraw. Slots остаютсяL02/L06/L01/L05; никакого fit.

Ресурсы reaped child: **1.078544 CPU-с**, parent prefix0.034366CPU-с; wrapper1.099073wall-с, peak child RSS131039232bytes. Это внутри выбранных10CPU/20wall/512MiB/5MiB. Engine1thread/128MiB/no spill. RSS и aggregate output наблюдались на границах, не выдаются за hard OS caps; parent CPU1/child9 — hard limits, wall constrained alarm/waits. Child resource_prefix исключает final write/shutdown, receipt включает reaping. Before-receipt output+source256197bytes; итоговая карта вfreeze даёт точный финальный размер. Все19 prepared Source/FIRST/skeptic pins свежи. FIRST immutable.

Первоначальная implementation SOURCE поправка до запуска: parent hardCPU1 наследовался бы ребёнком и запретил child9; поставлен parent soft1/hard9 доfork, hard1 сразу послеPopen. Никакого runtime failure/test rerun по этой причине не было. Два read-only discovery вызова ссылались на отсутствующие guessed source paths; source найден поинвентарю, это не producer attempts.

**Граница вывода:** это конечный certificate HYP-142/002 на заданных fixtures и exercised compiler/projection seam. Он не устанавливает prevalence, utilityarea, отсутствие всех утечек, причину seed2027 reversal, перенос на dataset или приростNDCG. Текущая bounded автоматизация работает; новая feature-quality задача не допускается автоматически. Canonical/Git не изменялись. Независимый reviewer назначаетсяRoot; автор остановлен.

Артефакты: `certificate.py`/`launch.py` source; `prepared.json` pins; `expected-before-producer.json` oracle seal; `result.json` complete ordered rows/types/areas; исходные `stdout.txt`/`stderr.txt`; `receipt.json` reaped lifecycle; `actual.json` compact aggregate; `pins.json`/`freeze.json` final fingerprints.
