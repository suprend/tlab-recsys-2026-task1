# Round062 — memory-bounded verification: partitions не заменяют proof полноты

**Первичные documentation sources и prospective pattern, 15 октября2026.** Никакие exports/source SQL, EXPLAIN, tests, модели или WIP не исполнялись. Прочитан только accepted [018 workflow](../experiments/verification-workflow.md). Это design refinement существующей проверки/воспроизведения, не найденный дефект текущего016 и не разрешение переразбить его run. Текущие policy/caps не меняются.

## Что реально сокращает materialization

[DuckDB CREATE VIEW](https://duckdb.org/docs/current/sql/statements/create_view) хранит запрос, а не физически материализованную relation; он выполняется при каждом обращении. Поэтому view над pinned Parquet может избежать предварительного `CREATE TABLE AS` всего широкого F, но повторные assertions способны повторять scan. Это обмен peak resident state на I/O/CPU, а не бесплатный cache или speedup. TEMP table тоже создаёт данные; слово temporary задаёт lifecycle, не доказательство отсутствия большого allocation.

[DuckDB workload guide](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads) описывает larger-than-memory execution/spill для grouping/join/sort/window и ограничения сочетаний blocking operators. `list()`/`string_agg()` не получают общего обещания spill. Следовательно, заменить table на view, затем выполнить большой join+window+EXCEPT — не доказательство bounded RSS. Равно неверно назвать маленький returned count маленьким execution state.

[Arrow ParquetFile.iter_batches](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetFile.html) выдаёт streaming RecordBatches с maximum record count и optional projected columns/row_groups. Это полезный transport: не превращать iterator в list или whole Table/Pandas. Но record count не byte cap для variable-width fields; decompression, reader metadata, buffers и собственный expected-state тоже занимают память. Указанный API — возможность будущего backend, не новая dependency и не measured capability нашего runner.

[DuckDB partitioned writes](https://duckdb.org/docs/current/data/partitioning/partitioned_writes) предупреждает о цене множества маленьких files и настраивает число открытых файлов. Storage partitions и verification work units поэтому не обязаны совпадать. Частое дробление может уменьшить один join, но увеличить scans, metadata opens и cost. Выбирать размер надо по существующему cost gate, а не из compressed file size или произвольного обещания RAM.

## Практический pattern для feature export

Пусть Q — independently accepted query domain, C — accepted unique(query,item), F — physical exported rows. Определить до сравнения total deterministic функцию `p(query)` на Q, например anchor плюс bounded диапазон ordinal из **accepted Q**, а не список существующих producer shards. NULL/unknown query и строки вне домена — errors, не молча отсутствующие partitions.

Для каждого p ожидаемые keys выводятся из `C WHERE p(query)=p`. Expected values строятся из exact source context на этих keys независимо от F. Factorized user/item/pair maps допустимы, если их grains/FD доказаны и broadcast проверяет **каждую physical Frow**. Нельзя получить expected domain из `DISTINCT F`: потерянная producer строка тогда исчезнет с обеих сторон. Source windows остаются `[t−W,t)`, recency — full observed prefix; partition по query day не означает разрешения ограничить историю этим днём. Global timestamp peers и category denominators вне C сохраняются.

Projection минимальна: exact keys, нужные physical feature columns, соответствующие expected values. Typed int/null/bool сохраняются до comparison; DataFrame inference и cast после округления BIGINT не восстанавливают исходное значение. Schema/type/order проверяются **до** union/cast. Сопоставление по keys не должно превращать duplicates в незаметный many-to-many join.

[DuckDB set-operation semantics](https://duckdb.org/docs/current/sql/query_syntax/setops) различают set и bag variants; `ALL` сохраняет multiplicity, positional unions могут приводить типы. Для exact relations нужны bidirectional bag equality либо отдельно uniqueness+bidirectional key equality. Для floating features отдельно применяется уже объявленная tolerance и NULL policy; нельзя заменить whole-row formula comparison approximate aggregate checksum.

## Cross-partition certificate

Локальный PASS каждого блока даёт глобальное утверждение только при следующих обязанностях:

| Обязанность | Независимое основание |
|---|---|
| Полный partition domain | Accepted Q со всеми queries, включая zeroY/emptyC; явно перечислены ожидаемые блоки |
| Disjointness/ownership | Каждая physical row принадлежит ровно одному допустимому p; file placement сам не является истинным p |
| Полный key/bag cover | Expected C и actual F совпадают в обоих направлениях внутри каждого p; orphan/duplicate отвергаются |
| Физическая полнота | Manifest exact file set, bytes hashes, schema каждого file и сумма реально просмотренных rows; нет ignored extra file |
| Единый смысл | Same source/protocol/AST/context/base identity во всех blocks; никакой смены cutoff/coverage после resume |
| Terminal evidence | Все required blocks complete, pins перепроверены, cleanup и cumulative resources завершены до promotion |

Row counts нужны для reconciliation, но недостаточны: пропустить один key и продублировать другой можно при том же count. «Все существующие файлы проверены» также не доказывает отсутствия ожидаемого потерянного файла. Если два files содержат один и тот же query partition, comparator обязан читать оба, а не выбрать первый. Empty-C Q не обязан порождать Frow, но обязан оставаться в query coverage certificate.

Hashes связывают проверенные bytes, а не доказывают semantic truth. Resume certificate принимает только complete previously verified work с теми же identities; failed/partial evidence сохраняется и оплачивается. Не предлагается новый retry/free-recovery policy.

## Три маленьких контрпримера и scope

Literal future fixtures: (1) две partitions имеют одинаковый total count, но query A пропущен, B продублирован; global expected domain отвергает. (2) NULL query key отфильтрован predicate и все видимые partitions PASS; ownership gate отвергает. (3) F содержит оба правильных values, но одна partition использует новый source cutoff; context identity отвергает даже без числового расхождения. Добавить BIGINT2^60+1 сNULL и empty-C Q можно в тот же≤32row fixture. Это proposal без выполнения/нового allowance.

Итоговый claim должен называть exact rows/partitions/formulas и completeness certificate. B preservation против старого F не превращается в source oracle B; sampled018 остаётся sampled, даже если sample прочитан streaming. Возможный memory-bounded транспорт — refinement существующих018/reproduction gates. **No new HYP/task:** сначала завершить утверждённый source/output proof, не менять работающий016 под видом оптимизации.
