# Heldout source: статическая оценка формы затрат

15 октября2026. Read-only сравнение [producer core](../../scripts/heldout_source.py), [independent oracle](../../tests/oracles/heldout_source_audit.py), вызванных005/003/004 helpers и опубликованных016/017 evidence. Никаких реальных DB, SQL/EXPLAIN, exports, targets, models или jobs не открывалось/исполнялось. Наблюдавшиеся SHA256: producer `c864bec3a3aefa946b7759993505bcde9dcd9c9edb7cb9ce03216d6ebddeafbb`, oracle `056f9b73eca546552b782141c9c37ba060bd1ba5fc75890b48a35b937ddf81cd`. Это cost critique exact snapshots, не новый execution approval или доказанный resource failure.

**Вывод:** существующая partition architecture устраняет известный016 wide-inspector OOM. Найдены два конкретных участка, чья стоимость не ограничена числом final C rows: pre-sampling/history aggregate state и многократные source queries для sampled B18. Достаточность предложенных900CPU/1200wall на producer и900CPU/1200wall на oracle при7GiBRSS/2GiBspill остаётся **неизмеренной**, но статический код не даёт основания объявить эти caps заведомо невозможными.

## Что действительно ограничено

`build_day` обрабатывает один anchor, выдаёт≤2000Q и≤440000C/F rows; только B45+chosen0/3, а не union12/F57 всех arms. Seven-day output bound —≤14000Q/3080000C. Oracle проверяет каждый день отдельно; cross-day Python set содержит только≤14000 query IDs. Его expected domains `du/di/dp` выводятся из независимо реконструированных Q/C, численные selected3 factorized по нужным grains. Ни один core не создаёт whole-period wide CTAS.

У oracle≤9 sampled pairs/day,≤63 за семь дней. `_rows` fetches chunks8192; выборка не загружается Python `fetchall` целиком. Но эти bounds относятся к выходу/sample count/Python transport, **не** к размеру engine intermediates, scanned source bytes или длительности одного blocking SQL.

## Два риска с конкретным механизмом

**1. Q/C caps применяются после более крупной работы.** Oracle `_expected_qc`(88–102) сначала группирует всех пользователей7d, вычисляет DISTINCT products/days и ранжирует eligible population; ограничение2000 действует после этого. `_hsa_pop` содержит всех purchase items7d до top200. Recent state содержит все seen products выбранных пользователей до top20. Producer использует аналогичные inherited helpers.

Ещё важнее005 `_grain_sql`(124–143): для `pair` и `user_category` SEMI JOIN идёт по **user_id**, не exact C pair/category domain. Full-prefix recency включает все historical products/categories выбранных пользователей. Число aggregate groups может значительно превышать440000C, хотя join обратно в F корректен. Это не candidate fanout или leakage: корректная existing005 calculation, но более слабая memory bound. Для category denominator source внеC нужен намеренно; ограничение толькоcandidate rows исказит shares.

Oracle metadata(111–126) также читает полный prefix для candidate items и all-Q users. Его `_sample_pairs`(184–190) строит source support для всех expected C pairs **до** выбора девяти. Из-за unique query-user/day и unique pair domain matching event не размножается на200 candidates; обвинение в C×source Cartesian explosion неверно. Однако matching events и grouped/hash state по-прежнему зависят от source history.

**2. Sampled B18 — небольшой результат, но много source evaluations.** `_sample_values`(210–234) для каждого selected pair выполняет два filtered full-prefix row streams, два rolling7d DISTINCT scalar queries и при известной category ещё два rolling7d count queries. Верхняя граница —126 full-prefix и252 rolling source-query evaluations за период,378 суммарно, помимо expected Q/C/metadata/chosen/support. Это собственный статический подсчёт calls, **не** измеренное число физических full-table scans: predicate pushdown/zonemaps/cache могут сокращать работу. Тем не менее `_hsa_raw` — VIEW, не сохранённый prefix cache. [DuckDB CREATE VIEW](https://duckdb.org/docs/current/sql/statements/create_view) прямо различает definition и materialization.

В streaming Python loops один популярный sampled item может дать много строк; chunk8192 не ограничивает их суммарное число/CPU. Sample часто содержит того же пользователя/item несколько раз, а текущий code не переиспользует independent extracted rows между pairs. `_structural_base` отдельно выполняет18 scans supplied daily B, что ограничено дневным F, но тоже не «одна проверка».

## Что говорят исторические evidence

| Published evidence | Измерение | Допустимый вывод |
|---|---|---|
| [017 collection verification](tlab017-collection-verification.md) | Train13days: Q/C40,03s + F/resume59,33s; peakRSS2,70GB; selection2days19,77s total; producer CPU отдельно не сохранён | Такой daily/shared005 путь ранее работал; wall нельзя выдавать заCPU или масштабировать линейно на поздний prefix |
| [016 original failure](../experiments/feature-program-source-recovery.md) |15daily exports уже готовы; OOM в terminal whole-phase wide CTAS, memory_limit2GB/spill0; failed prefix107,42CPU | Причина конкретна: wide consolidation, не доказанный провал дневных formulas |
| [016 recovered proof](tlab016-recovered-source-verification.md) |6134207pairs×12values,70,30CPU,43,57wall; oracleRSS2,06GB; source+recovery177,72CPU | Factorized daily proof оказался выполним; это другой oracle/source-prefix/sample workload, не benchmark current heldout core |

Late25–31 prefixes длиннее historical8–23; actual distributions/cardinalities/IO и Python streamed sample cost неизвестны. [DuckDB tuning docs](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads) предупреждают о памяти комбинаций blocking joins/grouping/windowing даже при spilling. Они не доказывают OOM здесь и не обещают hardRSS по memory_limit.

## Максимум три узких действия до большого запуска

1. **Зафиксировать daily relation-provider/lifecycle в owner plan.** Raw input — read-only relation/view; output loader не делает full-month raw CTAS, whole-seven-day B48 CTAS или `fetchall` F. Предыдущие дневные output tables освобождаются перед следующими; scratch states заменяются. Tiny multi-day fixture должен проверить inventory/предел одновременно живых partitions и forbidden-wide-materialization sentinel, не throughput.
2. **Оценить именно sampled-oracle callshape до freeze.** Tiny query-recording fixture с несколькими pairs одного user/item подтверждает верхнюю структуру calls и strict-prefix/window predicates. Если cost concern требует оптимизации, рассмотреть один independent batched extraction для unique sampled users/items и grouped category supports с теми же list formulas — без producer expected helpers. Такой code change требует отдельного review, не обязателен по одному статическому подозрению. Не материализовать полный prefix в RAM ради cache.
3. **Owner admission не основывать на Q/C caps как на RSS proof.** В already-required ledger различать eligibility/popularity, fullprefix metadata/grains, support/sample, exports/hashes и final cleanup. Сохранить interrupt и неизменный deadline во время длинного SQL, terminal reserve и внешний lifetime receipt. Tiny fake stalled-SQL/spill/cleanup faults проверяют fail-closed механизм; реальные900/1200 sufficiency они не доказывают. Если фактический run исчерпывает cap — paid failure/STOP, без refill или самовольного увеличения.

Новых framework/HYP/benchmark jobs не предлагается. Статический итог — конкретный uncertain-throughput risk, а не повод возвращать уже устранённый whole-phase inspector или заявлять заранее full-scale acceptance.
