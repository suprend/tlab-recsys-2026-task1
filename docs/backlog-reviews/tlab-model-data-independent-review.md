# Независимое review model_data: ACCEPT CODE ONLY

Дата: 2026-10-15. Проверен отдельный transformation API для **уже внешне проверенных** development collections и metadata exports. Материальных P0/P1-дефектов в этом scope не воспроизведено. Это не acceptance реальных matrices, не разрешение Pool/fit и не подтверждение source/full009. Proposal ablation runner остаётся отдельным будущим review и execution approval.

Точные SHA256 проверены до и после собственных synthetic checks и повторно после scoped tests:

| Файл | SHA256 |
|---|---|
| scripts/model_data.py | 89766e3a07a631caac91ec007849aaf4ecc5176caa911764372e10da0678108f |
| tests/test_model_data.py | 69d05ed5dcd9fafdbc72448aa4c6c3c0df6199d5e949e5f538445a13519a8427 |
| docs/experiments/model-data.md | f4751cc996c9d4c3cc6672d643dd2423b960a1f5f3b736c52866605813ecb4cd |

## Независимые evidence

Собственный fixture создан непосредственно SQL в временном каталоге, без producer helpers: 12Q, 2420C, одна emptyC query, полные targets с двумя miss вне C; product IDs выше2^53, отдельная проверка int64 min/max. Expected Q/C/groups/items/y и первые три float32 columns заданы Python lists, bottom-SHA вычислен отдельно hashlib. Healthy mixed/base arrays дополнительно точно сравнены с неизменённым008 loader. Это tiny transformation evidence; реальные6000/26000 arrays не читались.

22 основных и4 дополнительных собственных cases PASS. Connection trace подтверждает один execute итогового row SQL, затем последовательные fetch с сохранением cursor; chunk_vectors=1 дал2048+372rows, chunk_vectors=32 дал один2420-row chunk и empty terminator. Ограничение65536 проверяется кодом до копирования; полного65536-row synthetic benchmark не выполнялось. Официальная [DuckDB conversion documentation](https://duckdb.org/docs/current/clients/python/conversion#pandas) описывает vector_multiple×2048 при default vector size, поэтому фиксированная проверка является явным контрактом данного loader, а не обещанием любой будущей версии API.

На втором chunk независимо внесены duplicate boundary, reverse order, пропуск строки, float product transport, выход group за Q domain и Inf. Все отвергнуты. До allocation и до открытия labels отвергнуты row/byte caps; duplicate/missing/orphan metadata, user/anchor mismatch, retrieval на anchor, duplicate fullY, неверная namespace и mask тоже отвергнуты. Float32 overflow отвергнут DuckDB уже в CAST. NULL→NaN сохранён; NaN с согласованными missing flags допустим. UTF8 bytes русского значения переиспользуются по identity из общего cache. Отдельно сохранены exact int64 −9223372036854775808 и9223372036854775807. All-emptyC и zeroQ дали пустые массивы правильной формы; Q/fullY при emptyC сохранены. Selection-only nominal проходит без обучения encoder.

Реплей только `tests.test_model_data`: **10 PASS**,0.586s внутри unittest; измеренный child process0.719666wall,0.678816user+0.115572system CPU, RSS138117120bytes. Другие suites с реальными fits не запускались.

## Существенные границы для будущего runner

`prepare_model_data` не проверяет external acceptance, exact registry/approved feature grammar, actual TRAIN cardinality или baseline equivalence автоматически. Документ это описывает честно. Собственная наблюдательная проверка добавила `future_unreviewed` numeric column в supplied `collection.feature_columns`: loader её принял. Это допустимо только при заявленном preverified-input contract; API **не является** разрешением произвольных016 AST/columns. Runner должен bind exact принятую005 schema/registry и фиксированный порядок41→56numeric+3nominal, без произвольных column additions и без raw-ID aliases. Текущие raw key columns исключаются из numeric; JOIN IDs не входят в X.

Перед единственным009fit будущий runner обязан вызвать actual selected TRAIN encoded-cardinality gate≤4096 с sentinels, затем Pool. Helper boundary4096/4097 подтверждён синтетически; ни100Q, ни selection, ни full26000 diagnostic не заменяют нужные6000 TRAIN values. Selection unseen допустимы. Сам loader не выбирает CTR fallback.

До fit нужны оба exact comparisons: BASEONLY против unchanged0086000, затем base prefix mixed против того же reference, включая Q/fullY, group/items/y, names и equal-NaN float32. Tiny equality не доказывает actual equality. Exact metadata key multiset проверяется до row query; сортировка/целочисленный транспорт/final fill проверяются после. Source BIGINT schema и per-query≤220 гарантирует внешний accepted collection: здесь cap≤220×Q агрегатный, а dtype transport допускает integer representation, не заменяя physical schema acceptance.

Byte estimate включает numeric/object-pointer/group/item/y buffers; он не включает Python target sets, UTF8 payload/cache, pandas chunks, SQL working memory или native Pool. Это не hard RSS guarantee. Callback и внешняя audit boundary должны охватить preparation/close, counters, failures и финальные receipts; standalone loader ничего не записывает и не выдаёт execution approval. Future grammar и real memory/time feasibility не исследованы этим review.

## Failure/resource audit и raw evidence

Первый собственный запуск имел21PASS/1harnessFAIL: overflow безопасно вызвал DuckDB ConversionException, assertion ожидал ValueError. Исходные helper/results сохранены; второй helper исправил только ожидаемый тип исключения, после чего22PASS. Ошибка не замалчивается и не является product defect. Initial0.636030wall/0.740780CPU/RSS154402816; corrected0.697108wall/0.817584CPU/RSS161513472; supplement0.249365wall/0.275835CPU/RSS140525568. Эти собственные counters начинаются после imports и не выданы за полный fresh-process budget; scoped-tests child counters выше включают imports. Real source/model/matrix/Pool/fit operations:0.

Raw files: `tlab-model-data-independent-faults.py`, `tlab-model-data-independent-results-initial.json`, `tlab-model-data-independent-faults-v2.py`, `tlab-model-data-independent-results-v2.json`, `tlab-model-data-independent-supplement.py`, `tlab-model-data-independent-supplement-results.json`, `tlab-model-data-author-tests-replay.json`. Repo/frozen source не изменены.
