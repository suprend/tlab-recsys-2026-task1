# Round012: честная стоимость автоматического расчёта

15 октября2026. **Research/proposal,0benchmark runs/real scans/fits.** Прочитаны rounds002/003/009, draft011 и текущий manual_features.py. Центральный вывод: HYP046 следует сравнивать с существующим общим планом005. Независимый медленный oracle нужен для correctness; преимущество над ним ещё не означает преимущество над сильным calculation control. Это refinement002/046; HYP109/110 остаются reserved. Frozen code/artifacts не менялись, исполнения записка не разрешает.

## Первичные основания и фактический baseline

**DuckDB:** обычный CTE по текущей документации материализуется по умолчанию, но может inline по эвристикам; `MATERIALIZED`/`NOT MATERIALIZED` влияют на выбор, однако не гарантируют лучший результат. Следовательно, число повторённых SQL fragments само по себе не доказывает число физических scans. [WITH/materialization](https://duckdb.org/docs/current/sql/query_syntax/with).

Официальное описание optimizer включает common-subexpression extraction из projection/filter. Это локальная возможность, не обещание общего кэша между отдельными SQL statements. Current005 действительно создаёт несколько statements: общий DAG может помогать между ними, но optimizer уже способен устранять часть повторений внутри statement. Нужны physical plans обоих вариантов, optimizer включён симметрично. [DuckDB internals](https://duckdb.org/docs/current/internals/overview). Lock проекта закрепляет1.5.6; current documentation описывает механизм, а конкретные APIs/plans следует проверить в этой версии перед опытом.

**Kalibera, Jones, ISMM2013:** повторения нужны на уровне, где возникает неопределённость, например отдельных запусков, а не только внутренних итераций одного процесса. Авторы рекомендуют оценивать величину изменения с uncertainty и учитывать стоимость повторений. Их DaCapo/SPEC methodology не предоставляет готовой гарантии для двух запусков SQL. [Author Accepted Manuscript, University of Kent](https://kar.kent.ac.uk/33611/45/p63-kaliber.pdf).

**OneBM** кэширует общие joining prefixes и освобождает их при обходе других ветвей; статья отдельно использует subsampling большого join, меняющий точность. В нашем exact опыте допустим первый принцип, но history truncation запрещён. **F-IVM** показывает materialized/intermediate sharing и incremental maintenance для определённых joins/aggregates; это основание исследовать reuse, не доказательство скорости snapshot compiler или rolling distinct. [OneBM, IV](https://arxiv.org/html/1706.00327v1), [F-IVM, author paper](https://arxiv.org/pdf/2303.08583).

**Local fact:** `_grain_sql` и `create_manual_features` уже группируют features по grain/anchor, совместно вычисляют FILTER aggregates, переиспользуют metadata и distinct user/item sets через SEMI JOIN. Представлять005 как заведомо независимый scan на каждый feature было бы неверно. Сильный predictive B определяется tuning/selection; сильный physical control определяется планом расчёта. Одна характеристика не удостоверяет другую.

## P0: лестница контролей

| Уровень | Назначение и допустимый вывод |
|---|---|
| O: независимый direct-list/per-expression oracle | Correctness на tiny source и bounded samples; не primary timing competitor |
| M: unchanged005 shared compiler plan | Реалистичный primary calculation control для реально поддержанных AST |
| A: automatic typed/shared DAG | Те же определения/outputs; проверяется added reuse поверх M |
| H: optional hand-shared plan | Дополнительный ориентир; стоимость разработки и tuning раскрывается, оптимальность не заявляется |

O не вызывает production resolvers/counters. M использует текущую группировку005, стандартный optimizer и тот же input wrapper/sink. A может менять physical sharing, но не operator semantics. H не обязателен для P0 и не получает отдельный budget: если его невозможно закончить внутри остатка, оставить prospective. Нельзя отключить optimizer только у M, искусственно материализовать ненужные промежуточные таблицы или сравнить A с намеренно слабым oracle под названием manual baseline.

Fixed workload — manual18 плюс **один заранее зафиксированный допустимый three-column bundle из существующих четырёх016 arms**, либо manual18-only как явно более узкая проверка. Не вводить новый диагностический bundle сверх12columns. Ровно одинаковы Q/C/source pins, AST, dependency closure, output schema, windows/endpoints, raw/distinct multiplicity, metadata/NULL/coverage policy. Выбор workload label-independent, не по наиболее выгодному speedup. Nested HYP045 не поддержан005: сравнение с новым hand-coded extension требует отдельного scope, его нельзя приписать этому контролю.

## P0: завершённый результат вместо dead code

`SELECT count(*) FROM (feature projection)` недостаточен: optimizer может удалить неиспользуемые expressions. Оба плана должны материализовать **все** required columns в одинаковый sink: например одинаковый Parquet export с одинаковыми options, затем полный keyed comparison/checksum чтения всех полей. Первичный endpoint включает export; readback/semantic validation отдельно показывается и оплачивается общим ledger. Не смешивать SQL-to-table у A с Python-object fetch/export у M.

Schema/keys/integers/NULL/masks совпадают точно; float tolerance фиксируется заранее. При different summation order byte-level Parquet equality не заменяет semantic comparison. Обязательны duplicate/fanout, expiry последней distinct-копии, global peers, mixedNULL metadata, category move, empty support, future suffix и candidate reorder. Полный category denominator нельзя сузить до C ради ускорения. Count source/intermediate rows и actual plan topology объясняют механизм; AST dedup ratio или cache-hit counter без consuming output недостаточны.

## P1: ограниченный measurement protocol

Предложение внутри **прежнего** HYP046 subbudget и016≤2actualCPUh/4fits/12columns: не более20actualCPUминут на calculation comparison, включая tiny oracle, preparation, warmup, profiling, failures и cleanup; не новый allowance. Два DuckDB threads, RSS≤8GiB и общийwall-stop сохраняются. Если остаток меньше, расходуется остаток, без free retry/refill; fits здесь не нужны.

После correctness заранее максимум четыре парных запуска: **AB, BA, AB, BA**; анализировать полный заранее разрешённый набор либо завершённые balanced blocks, сохраняя все незавершённые/failed attempts. Каждый вариант запускается в новом worker с одинаковым setup, временные generated outputs очищаются до run. Один declared warmup каждого варианта оплачивается. No persistent A-only feature cache; внутри run shared state разрешён. Для search-wide cache отдельно раскрыть общий оплаченный setup и доступность для I/R arms, без скрытого бесплатного обслуживания intelligent selector.

Primary cost — end-to-end process user+system от worker start до close/serialization; compile, binding, input validation и sink входят. Parent orchestration/awaited child accounting должно исключать doublecount, но охватывать всех workers. Wall измеряется отдельно; wall×threads не CPU. PeakRSS измерять для каждого fresh worker, engine buffer/spill — дополнительная диагностика. Lifetime high-water одного reused процесса не позволяет честно приписать память второму плану.

DuckDB `CPU_TIME` — сумма operator timings, без parsing/planning; `EXPLAIN ANALYZE` исполняет запрос, а суммы operator times при parallelism могут превосходить query wall. Эти counters не заменяют бюджет процесса. Отдельный profiled run оплачивается; instrumentation либо одинакова у обоих, либо оба primary runs без неё. [Metrics](https://duckdb.org/docs/current/dev/metrics), [EXPLAIN ANALYZE](https://duckdb.org/docs/current/guides/meta/explain_analyze).

Cache policy объявить честно: fresh engine не означает cold OS page cache; предварительный source hashing сам может прогреть страницы. Не очищать системный cache скрыто. Фиксируются version/settings/process/thread count, порядок, concurrent workload и thermal/order drift. Если порядок меняет вывод, timing inconclusive. Для четырёх пар публиковать все CPU/wall/RSS, ratio суммарных matched CPU M/A и разброс; псевдонезависимые operator rows не дают множество наблюдений. Предложенный002 engineering threshold «A≤0,8×M CPU; RSS≤1,2×M» сохраняет смысл gate, но не превращает малую серию в доказанную population effect или гарантированный95%CI.

## Какие claims остаются полезными

Без quality gain можно подтвердить выполнение typed AST без bespoke per-feature SQL, semantic preservation shared execution и bounded cost на указанном workload. Если A и M физически совпали после optimizer, корректный результат — automation достигла существующего плана, added speedup не найден. Если A быстрее только O, доказан выигрыш над oracle implementation. Если быстрее M, вывод ограничен pinned engine/input/schema/cache policy и measured boundary.

Не доказаны универсальный speedup, меньшая стоимость разработки без engineering-time audit, online incremental availability, качество feature selection, portability на другом dataset или recommendation gain. Проверка renamed synthetic schema подтверждает adapter contract; quality generalization требует отдельного temporal experiment. Эта линия закрывает часть calculation task1, сохраняя tuned predictive B и cost-matched016 selection отдельными обязательствами.


## Coordinator critic appendix — 15 октября 2026

[Independentcritic](round-012-review.md) принимаетresearchdirection, неновыйexecutionbudget. Main016—automaticGENERATION/selectiontypedAST+correctcalculation; optionalcomputecomparisonиспользуетsamefixedworkloadvsunchanged005sharedplan,optimizerON/fullcommonsink.005multi-statementprofilingнуждаетсявstatementinventory/coverageALL/separateprofiles;lastqueryJSONнеfullpipelineCPU. CPU_TIMEнеprocessCPU. Timeout/censoredpairsневыбрасываютсядляsurviving-speedupclaim;human-hoursнеизмерены. Canonical009retentionstrictNDCG>base+1e−12/Recallguard/tiebase отличаетсяотraw019proposal>=;точноеправило зафиксировановbacklogдо009metrics.
