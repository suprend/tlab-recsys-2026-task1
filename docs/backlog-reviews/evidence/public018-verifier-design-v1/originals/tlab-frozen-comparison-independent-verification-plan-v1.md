# Thin actual-output verifier for frozen B/W reproduction018

Статус: source-only proposal, не runtime grant. Будущих outputs ещё нет. Публичный producerV1 и recipe3a26fed… прочитаны; adapter пишется только после фиксации V2schema. Никаких raw/DB/parquet/NPZ/CBM открытий, native imports, обучения или tests сейчас не было.

## Граница и независимость

Verifier принимает отдельный внешний expected digest закреплённых V2recipe/code и полного нового output closure, наблюдаемый terminal receipt конкретного producer invocation и собственный ресурсный предел. Не импортирует producer conclusions, prepare_matrix, rankings, evaluate или bootstrap. Малые JSON читает однократно в ограниченный snapshot: проверенный raw становится parsed input. Пути строго внутри нового exclusive output, без symlink/подмены/посторонних файлов. Сам verifier выполняет0fits и не касается heldout. Публичный CLI не требует старых approvals, отчётов, экспортов или CBM.

## Источник, коллекции, матрицы

После отдельного разрешения сверяются bytes/SHA исходного gzip с recipe, import evidence и новой DB; output file inventory и hashes до/после проверки, source/code/environment binding и завершённая операция. Повторное хеширование/сканирование оплачивается. Импортkernel считается ранее reviewed компонентом, но флаг producer не заменяет binding фактических байтов.

Независимый SQL adapter проверяет15 daily manifests, exact UTC anchors: train08–20 и selection22–23;26000/4000 зрелых уникальных Q,2000/day, cohort keys/users/maturity и строгую историю. Для каждого export проверяются types/order/schema, null/duplicate/orphan constraints и bidirectional full C/F/extra key cover. FullY извлекается из fresh source purchases по query/horizon независимо от C; сохраняются zero-Y и off-C targets. Ожидаемые counts: C5317058/817149, fullY619/96, positiveQ496/73, retrieved444/65. Несовпадение останавливает историческое соответствие, без изменения рецепта. Проверка Q/C может повторно использовать reviewed independent017/heldout source mathematics через явный calendar transport; это не producer helper.

Матрицы строятся отдельно: global query_id groups, product_id ascending, точные integer keys, float32 X, int8 relevance, B41/W44 ordered names; W имеет ровно R2/L05 chosen3. Проверяются одинаковые B/W Q/groups/items/fullY/y, вся B41-prefix W, и независимые row weights1/|Cq| (float64), суммарная масса и пустые/информативные группы.

## Два реальных новых обучения

JSON consumed slots нужны, но сами ничего не доказывают. Достаточный инженерный witness: заранее закреплённый concrete CatBoost producer без runtime backend seam/старых CBM inputs, наблюдаемый один новый exclusive invocation, ровно две заранее потреблённые native fit попытки B/W и их возврат, последующее сохранение новых файлов, полный external completion/cost. К этим событиям привязываются independently reconstructed train identities/weights и загруженные outputs. Отсутствие такого свидетельства означает training provenance unconfirmed. SHA нового CBM может совпасть со старым при детерминизме; различие SHA не требуется и не доказывает fit. Native training weights задним числом из CBM не восстановить: остаётся доверие к проверенному concrete fit path и наблюдаемому исполнению.

## Native outputs и метрики

Из нового closure загружаются только B.cbm и W.cbm. Проверяются numeric-only schema41/44, exact feature order,300 trees/trained/scored, фиксированные constructor/effective parameters и допустимая только уже reviewed serialized Bayesian alias через independent native_equal. Полный набор параметров и типы проверяются, не только depth/seed.

Own selection matrices дают собственные RawFormulaVal scores для всех817149 строк каждого arm. Сверяются полные group/item keys, finite float64 saved scores, atol1e−12/rtol0 и точный ranking с product_id tie-break. Независимые math core functions считают Recall/NDCG/AP/MRR по fullY во всех четырёх estimands; сверяется каждое опубликованное поле. Paired user-cluster bootstrap:200 fixed draws,seed2026,3995 users; сверяются каждый conditional-NDCG draw, estimate/undefined count/percentile CI, а остальные estimands можно сохранить как independent evidence без нового выбора. Никаких selector/refit/retuning.

## Повторное использование и предел feature proof

Подходящий нижний core: tests/oracles/feature_program_model_audit.py — read_matrix/group_weights/rankings/summarize/paired_bootstrap/matrix_proof. read_matrix требует тонкой адаптации historical collection transport и F57extra к fresh B45/extra5; старый orchestration/approval loader не используется. Metric/bootstrap core сохраняет независимость от production ranking_metrics.

Дополнительный INTERNAL-only режим пересчитывает старый canonical matrix_proof для всех fresh train/selection значений и сравнивает bound accepted R2 worker503c434… witnesses: W44 X, Q/groups/items/Y и trainweights. NaN canonicalization, little-endian dtypes, ordered dictionary-Q/ISO encoding восстанавливаются точно: V1 raw matrix_identity имеет другой формат и его hashes напрямую несопоставимы. Own B41-prefix equality связывает B с этими W44 входами. Это полная parity материальных матриц, а не новое исчерпывающее доказательство manual18 formulas. Старый источник Q/C/fullY принят исчерпывающе, manual18 formulas проверялись выборочно; selected12 ранее проверены полностью. Без INTERNAL режима честный публичный вывод: fresh pipeline использовал reviewed compiler; native/transport/metrics проверены полностью, source-formulas не пересчитаны независимо на каждой строке. Старые binary exports не нужны для сравнения canonical witnesses.

## Ресурсы и следующий конечный шаг

Предложение verifier отдельно от producer:600CPU/900wall/8GiB RSS, DuckDB2GiB+aggregate spill8GiB, sequential matrices,2CBM loads,2 full selection predicts,0fits/heldout/children; полный startup/hash/SQL/native/persistence/exit включён, external supervisor обязателен для actual grant. Это planning ceiling, не измерение: ориентиры prior016 source oracle70.30CPU и bounded matrix/native observers, а точный расход нового adapter неизвестен. INTERNAL canonical parity помещается в тот же проход; превышение прекращает попытку без refill. Producer import/features/2fits и verifier расходы имеют отдельные ledger homes, без parent/child doublecount.

Далее: получить frozenV2schema, подготовить один TMP adapter+точные output expectations, затем Root решает отдельный конечный actual verification grant. Публичная воспроизводимость — новое исполнение уже выбранного development recipe, не независимый quality validation и не расширение scientific fit/selection budget.
