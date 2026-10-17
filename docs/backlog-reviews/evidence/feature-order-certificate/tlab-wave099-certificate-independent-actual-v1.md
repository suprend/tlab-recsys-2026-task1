# Wave099 B — независимый ACTUAL review synthetic certificate

**PASS в заявленных пределах; actionable findings не найдены.** Review завершён 2026-10-17T09:49:07.446341+00:00. Я не автор certificate/materializer. Исходный suite не повторялся. Новый literal/area пересчёт выполнен только стандартной библиотекой над вымышленными строками и готовыми JSON, без producer imports.

Проверен exact `freeze-v2.json` SHA256 `db709a1da8be753478ae13320e46a5e339d1d11c0c7b858e15d210962110ae6f`. Все13 перечисленных artifacts и19 prepared pins свежие при начальном и финальном чтении; пересечение списков учтено, это не32 независимых исходника. FIRST и раздел B skeptic прочитаны как контракт. Применён code-review; дополнительный read-only reviewer отдельно проверил oracle/source axis и также не нашёл поддержанных дефектов.

## Независимость ожидаемых значений

`certificate.py:26–69` задаёт B41/EXTRA и отдельную row-list интерпретацию. Значения не извлекаются из `create_manual_features`, generated registry outputs или полученной матрицы. В `:181–194` все64 expected rows и8 area значений вычисляются/сверяются и expected-before-producer.json сохраняется **до** imports DuckDB/NumPy/producer в `:196–200`.

Row-list oracle сравнивается с заранее заданными literals; generated schema/order затем сравнивается с тем же независимым contract, а не используется для исправления ожиданий. В JSON seal достаточно H1-таблиц: перед sealing H2 тоже построен и проверен против одинаковых gold literals; после materialization обе реальные projected matrices дополнительно сравниваются напрямую. Dependency independence подтверждена; это узкий oracle одного user/item/category fixture, без утверждения о независимой общей реализации всех grains.

## Production и окончательные44 inputs

В `certificate.py:239` действительно вызывается production `scripts.manual_features.create_manual_features`, включая его registry validation, global metadata bucket, aggregates, ratios/flags и strict-past predicates. Код compiler (`manual_features.py:126–153,156–270`) читает invented `events`, supplied Q и supplied C; loader `manual_features.run` не вызывается. Никакого нового retrieval нет. Query имеет synthetic label_is_mature=True, но Y-таблицы/target values не создаются. Future purchase — excluded invented event, не target label.

Raw schema48 состоит из6 context/key columns и42 проверяемых physical numeric/flag columns: B39+3. B41 включает дополнительно две label-free source projections. Поэтому raw42 и final44 различаются корректно: **64×42=2688 raw literal cells,64×44=2816 final literal cells**. Сравнивать только raw closure с B41+3 было бы ошибкой, но данный certificate отдельно исполняет обе ступени.

`certificate.py:162–178` использует exact `CAST(... AS FLOAT)` expressions, включая epoch(anchor)−epoch(last_user_event_time) и IS NULL flag, затем masked NULL→NaN и float32. Сопоставлены production expressions `train_baselines.py:254–265` и `model_data.py:157–180`. Final order берётся из независимо заданных B41+3 и проверяется против bundle model_feature_order; SQL result names/types FLOAT44, shape1×44,dtypefloat32,NULL mask и каждое literal значение проверяются в `:236–255`.

Это реально исполненная custom label-free projection с теми же expressions/transport. Полные Y-aware prepare/loaders **не вызывались**, общий loader или downstream model training здесь не валидируются. `baseline.numeric_feature_names` вызывается только для B41 naming/order validation. ML import blocker и финальный imported-module check не обнаружили CatBoost/Torch/TensorFlow/sklearn/tsfresh; в inspected exercised call graph ML/score calls нет.

## Числа и независимая дополнительная арифметика

Оригинальный result/receipt подтверждают64 materializations=2worlds×8bundles×4cases. Cross-world проверки —4×8×44=1408; within-world original↔reverse/excluded —2cases×2worlds×8×44=1408. Sensitivity16=2worlds×8bundles проверяет recency7200→1800 seconds.

Собственная stdlib проверка заново построила шесть событий из контракта, независимо посчитала area через chronological prefix balance, counts/distincts/recencies/ages, все2816 expected final values и IEEE float32 transport через struct, затем сравнила с сохранёнными final rows. Сверены1408 cross-world и1408 within-world cells,16 recencies,8 areas; всё PASS. Это **не второй compiler/suite run**: SQL,NumPy,DuckDB,project/backend imports не запускались.

| Encoding case | H1 area | H2 area |
|---|---:|---:|
| original |3|1|
| physical row reverse |3|1|
| excluded global peers atT / futureT+1h |3|1|
| sensitivity: finalV moved after finalC |1|−1|

Строгое сравнение timestamps делает reverse invariant и исключает оба peers atT. Sensitivity обновляет не только view recencies, но и supplied last_user_event_time доT−1800; это отражено в source projection. Остальные assigned fields остаются совместимыми между мирами. Следовательно одинаковые44 vectors здесь сосуществуют с различной area; deterministic scorer только этих44 inputs не может различить два экземпляра.

Дополнительная арифметика: original tool completion chunk8a5025,exit0; CPU self-prefix0.046752s,wall0.002902500s,maxRSS18006016bytes. Выбраны hardCPU2s/wall alarm5s, observed RSS<64MiB. Отдельного runtime ошибки/повтора этой проверки не было.

## Оригинальный lifecycle, generation и errata

Прочитаны unchanged launch.py, child stdout/stderr,receipt.json,actual.json и оба freezes. В pinned actual записан original terminal3fd2bf/exit0; receipt непосредственно сохраняет `p.wait` exit0,reaped=true,attempt1,retries0,pid54821. Child stdout COMPLETE_PRODUCED_UNREVIEWED,stderr empty. Я не воспроизводил исходный terminal command и не выдаю чтение его идентификатора за новый tool execution.

Source содержит один explicit generate_pool и одну allocate_slots. В production allocate_slots:168 выполняет generate_pool для проверки identity; итого2generation calls,1pool/1allocation. Это не redraw/search; allocation slots L02/L06/L01/L05 не менялись, а materializer всё равно проверил все8 bundles. Числа generation не просто приняты из констант result: static call graph также просмотрен.

Recorded reaped child CPU1.078544s,parent CPU prefix0.034366s,wrapper wall1.099072792s,maxRSS131039232bytes. Limits parentCPU1+childCPU9 hard, child18s alarm,parent finite waits; DuckDB1thread128MiB/no spill. RSS/output checks staged, это **не hard OS RSS/aggregate disk cap**. Receipt включает reaping; child result resource_prefix исключает final write/shutdown. Не смешиваю эти диапазоны и не заявляю измеренную person-time.

Сумма original files_before_receipt —**248197bytes**. Исходный ACTUAL.md ошибочно пишет256197; ERRATA.md исправляет именно эту prose арифметику. Original ACTUAL.md/freeze.json сохранены побайтно; result/lifecycle не переписывались. Freeze-v2 содержит266220 bytes перечисленных files перед записью самого freeze-v2; это отдельная сумма. Errata не является новым suite attempt или скрытым runtime repair.

## Граница приёмки

Это finite informational certificate для объявленных fixtures и ordered44 projection seam. Он не показывает частоту такого blind spot, utilityarea для24h purchases, качество ranker, отсутствие всех возможных утечек, причину seed2027 reversal, arbitrary-schema automation, labour savings или выигрыш NDCG. Новый area/source/support/quality pilot автоматически не разрешён; дополнительных обязательных gates нет.

Только read-only inspection и разрешённая tiny stdlib арифметика. Real rows/data/model bodies, suite reruns, project imports, SQL execution, fits, model loads, predictions, downloads, canonical/Git writes —0 в этой проверке. Source materializer runtime64 относится исключительно к одной исходной авторской попытке. Final freshness/readback выполнен; **READY_STOP**.
