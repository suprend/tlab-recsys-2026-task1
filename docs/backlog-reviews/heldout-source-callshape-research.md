# Heldout oracle: один tiny callshape probe

15 октября2026. Выполнен **один** разрешённый synthetic probe, exit0: существующий `RAW` из [test fixture](../../tests/test_heldout_source_audit.py),21raw rows, один25Oct день, branchR2. TestCase не создавался, unittest suite не запускался. Accepted producer/oracle не менялись. Real DB/архивы/события, queryY, модели, native predictions, fits и actual-source EXPLAIN отсутствуют. Это уточнение [статического cost critique](heldout-source-cost-critic.md), не quality experiment или actual-source acceptance.

## Как посчитано

Tmp-only `tlab-heldout-source-callshape-probe.py` импортирует fixture constants и `definitions`, создаёт `:memory:` DuckDB, явно2threads/128MB memory/spill0, вставляет21строку. Один producer `build_day` создаёт synthetic Q/C/F, затем четыре маленькие таблицы actual output; Y не строится. Его inherited helpers выполняют три штатных **tiny EXPLAIN** для eligibility/popularity/recent до начала oracle recording; эти setup calls не входят в97. Oracle EXPLAIN/profiling не выполнялся. Synthetic lock/refs — fixture placeholders, не исторические approvals.

После setup proxy connection записывает каждый `execute` **только единственного** `oracle.audit_day`. SQL текст и function stack сохраняются без bound user/item/query values. `fetchmany` считает возвращённые строки `_rows`; `fetchone`/`fetchall` counters не называются scanned rows. Guard проверяет300CPU/300wall/512MiB tiny ceiling; acceptance/fits разрешений не выдаёт.

Исполненная форма команды из подготовленного repo: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B <probe.py> <project-root>`, stdout сохранён как `tlab-heldout-source-callshape-log.json`. Повторного probe, других branches/days или adversarial test run не было.

## Фактический результат

| Наблюдение | Число |
|---|---:|
| Raw fixture / days |21 /1 |
| Expected/actual Q / C |6 /9 |
| Unique selected B18 pairs |5 |
| B18 core comparisons |90 |
| Exhaustive chosen3 scalar comparisons |27 |
| Всего oracle SQL calls |97 |
| Metadata DESCRIBE/settings |6 |
| Создание raw-prefix VIEW |1 |
| Прямые SQL evaluations с `_hsa_raw` |33 |
| SQL без прямого raw reference, по derived relations |57 |
| Source calls внутри `_sample_values` |24 |
| Из них row streams / scalar queries |10 /14 |
| Streamed result rows суммарно |40 |

33direct-raw calls состоят из24sample-formula calls и9остальных: Q, popularity, recent, catalog check, три metadata/age computations, chosenR2 aggregate и source support для strata. Derived-only classification основана на SQL text и данном dependency shape; это не универсальный анализ lineage произвольного provider.

Bottom hash выбирает4pairs из9. Ещё по одному выбираются view support, missing category, ambiguous category, purchase support, old-recency strata; пересечения дают **пять**, не девять unique pairs. Available populations соответственно9,3,7,6,1,1; sampled counts4,1,1,1,1,1. На пяти pairs выполнено20обязательных source queries плюс4category queries для двух known-category samples. Ten stream lengths:4,2,7,8,4,8,4,1,1,1. Повторяющиеся returned events не являются дополнительными raw inputs: fixture остаётся21строка.

`baseline_formula_values_complete=false` сохранён. Этот probe не расширяет sampled B18 до exhaustive proof; complete chosen3 значения относятся только к девяти synthetic C rows, не к actualheldout.

## Почему97calls/33raw references не равны full scans

Metadata6 не сканируют event rows; CREATE VIEW1 не материализует prefix. Views раскрываются в запрос, а [DuckDB docs](https://duckdb.org/docs/current/sql/statements/create_view) прямо говорят, что view query исполняется при обращении. Однако predicates `product_id=?`, `user_id=?`, action/time bounds и join domains могут проталкиваться к source; physical scan может читать меньше данных благодаря storage layout/zonemaps. Несколько source refs в одном плане тоже не задают автоматически столько же full-table passes. [Официальные performance docs](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads) отдельно различают filter pushdown и physical profiling.

40streamed rows — результат filters, а не rows examined движком. И наоборот, один `count(DISTINCT ...)` возвращает одну строку, но может обработать много source rows и держать hash state. Warm buffers могут уменьшать IO без устранения scan/filter CPU. Поэтому ни `33×42m`, ни `40rows/0.2s⇒fullmonthtime`, ни «14 scalar results почти бесплатны» из этого опыта не следуют. Physical full-scan counts здесь **не измерены**.

После imports весь tiny setup+producer+oracle+close+terminal source repin занял0,20553wall/0,22433processCPU seconds, peakRSS141623296bytes. Это body-only mechanical receipt на маленьком fixture, не внешний full-process lifetime/throughput benchmark; отдельное время oracle не измерялось. Ни производительность позднего month prefix, ни достаточность900CPU/1200wall/7GiBRSS/2GiBspill этим не установлены.

## Обсуждение batching и решение scope

Coordinator получил actual counts. C11, автор independent core, согласился: менять accepted core сейчас по callcount оснований нет. Его позиция — отдельная future-reviewed batching delta только при concrete admission/cost concern, сохраняя sampled pairs, NULL/category policy, full-prefix recency, counts и caps. Она не должна незаметно потребить повторный actual oracle attempt.

Вывод именно probe: callcount сам по себе не обосновывает обязательную замену принятого v1. Shared extraction для unique sampled users/items может сократить повторные evaluations, но добавит свои join/state/cache costs и нуждается в equivalence proof. Никакой speedup или обязательная оптимизация здесь не утверждаются. Ближайший actual gate остаётся reviewed owner/provider/lifetime plan, не новый framework или расширение sample.

**Последующий coordinator amendment:** после получения counts Root отдельно согласовал pre-runtime v2 engineering delta sampled kernel; C11 поручена tmp-only реализация с сохранением v1, исходных tests, того же sample и независимой raw arithmetic. Это самостоятельное инженерное решение, не вывод о недостаточности900CPU, не новое actual испытание и не увеличение бюджета. Настоящий probe измерял только указанный v1; результата, acceptance или speedup v2 здесь нет. Семантика, sample/caps и preserved v1 evidence не подменяются.

## Immutable evidence

Семь public source/fixture files проверены SHA до/после, все совпали; полная map находится в log. Producer SHA `c864bec3a3aefa946b7759993505bcde9dcd9c9edb7cb9ce03216d6ebddeafbb`; oracle `056f9b73eca546552b782141c9c37ba060bd1ba5fc75890b48a35b937ddf81cd`. Tmp probe SHA `fb2c10f32ab0307a7ef9721d9f99835a1ce174143241741ae5d639eeec4e0c3c`; log SHA `916ec54a9a3ab50976ad1dd85a044fcdcd9aecb6daf2d4415bc3b1c4afaa1295`. Repo files, data/environment/Git/approvals не менялись;0TestCases,0fits,0native predictions и0real-source reads.
