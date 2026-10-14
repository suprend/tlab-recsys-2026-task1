# Round012 / prospective019: independent material review

15 октября2026. **ACCEPT research direction с обязательными amendments ниже; никаких execution/code/fit approvals.** Проверены rawRound012, prospective019incumbent amendment, [backlog](../backlog.md), relevant005code и009design. Первичные DuckDB docs и Kalibera–Jones прочитаны непосредственно. Benchmarks, real scans, fits, code/repo/acceptance writes не выполнялись; frozen018 и исходная011 не менялись. HYP109/110 остаются reserved: это refinement002/046, не новый predictive mechanism.

## 1. Основная automation seam должна оставаться центральной

Round012 правильно отвергает сравнение автоматизации с намеренно медленным correctness oracle. Actual005 `_grain_sql` объединяет FILTER aggregates по grain/anchor, использует общий metadata state и SEMI JOIN restrictions; «manual=один независимый full scan на feature» фактически неверно. [Current005](../../scripts/manual_features.py).

Однако фиксированный AST speed experiment сам по себе не закрывает016. Canonical main scope — автоматическая **generation/selection typed AST и корректный calculation** при matched search budget. Дополнительный speed test разрешён только для одинакового заранее выбранного AST против current005, optimizerON у обоих, одинакового полного sink и внутри остатка existing budget. Manual18-only допустим как узкий physical test; он не сравнивает intelligent selection с random и не доказывает нового recommendation gain. Optional H-plan лучше оставить deferred, если он конкурирует с центральной работой за остаток. Bespoke extension для unsupported nested AST не считается unchanged005control.

Нужны две независимые записи: generation/search register с2I+2seededR×3actualcolumns и execution workload manifest с exact AST/closure. Invalid/duplicate attempts оплачиваются без replacement; supports/masks/coverage и дедупликация относительно всего frozen B входят в physical schema. Успешный shared calculation без quality gain остаётся полезным ограниченным результатом; отсутствие speedup не отменяет automation generation.

## 2. Source claims о планах корректны; profiling scope надо уточнить

DuckDB документирует default materialized CTE, возможный inlining и ограничения hints. Common-subexpression extraction относится к projection/filter внутри optimized tree; это не доказательство cross-statement cache. Поэтому repeated SQL text не равен repeated physical scans. Сохранить optimizer симметрично включённым и сравнить реальные plans в pinned1.5.6; current docs описывают механизм, не измеренный результат проекта. [WITH](https://duckdb.org/docs/current/sql/query_syntax/with), [optimizer](https://duckdb.org/docs/current/internals/overview).

**Материальное дополнение:**005 — multi-statement pipeline. Default profiling coverage=`SELECT` не охватывает все statement types; один `profiling_output` перезаписывается каждым новым query. Один JSON последнего SELECT не удостоверяет стоимость подготовки/CTAS/export всего pipeline. Для диагностического run нужен заранее перечисленный statement inventory, coverageALL там, где требуется, отдельное сохранение каждого profile и связь с этапами. Это proposal instrumentation, не выполненный profiling. [Profiling](https://duckdb.org/docs/current/dev/profiling), [output/coverage semantics](https://duckdb.org/docs/current/configuration/pragmas).

`CPU_TIME` — cumulative operator timings, без parsing/planning. `EXPLAIN ANALYZE` действительно исполняет запрос; operator times при parallelism могут суммарно превышать query wall. Их нельзя назвать process user+system или бесплатной инспекцией. Round012 это различает правильно. [Metrics](https://duckdb.org/docs/current/dev/metrics), [EXPLAIN ANALYZE](https://duckdb.org/docs/current/guides/meta/explain_analyze).

Полный common sink должен потреблять все required fields; count-only wrapper может удалить вычисления. Keyed semantic comparison обязателен поверх checksum, поскольку одинаковая hash-схема не доказывает значения, а Parquet bytes могут различаться при равной семантике. Целые/NULL/flags точные, float tolerance frozen заранее. Нельзя ускорить category denominator через C-only restriction или урезать observed prefix ради recency.

## 3. Measurement amendment: failures не превращаются в speedup

AB/BA blocks, fresh workers, одинаковые setup/sink и видимый OS-cache policy разумны. Один warmup перед fresh workers прогревает иной state, чем повтор внутри одной engine session: назвать, что именно остаётся тёплым, без cold-cache claim. Hashing source тоже прогревает страницы; эта стоимость симметрично включается либо отдельно раскрывается в общей подготовке.

Для complete matched blocks ratio `ΣCPU_M/ΣCPU_A` имеет понятное направление: больше1 означает более быстрый A. Engineering gate A≤0.8M соответствует ratio≥1.25; это не population inference. Если медленный M timeout, нельзя удалить его вместе с незавершённой парой и объявить успешные surviving blocks representative. Сохраняются censored/failed attempts, partial costs и completion status; общий вывод может быть cost-inconclusive. Не дополнять серию новыми запусками до красивого результата.

Kalibera–Jones обосновывают repetitions на уровнях реальной вариативности и uncertainty эффекта; четыре пары не получают автоматически надёжный95%CI. Даже их рекомендации зависят от workload/platform. Raw timings, order sensitivity и ограниченный descriptive ratio допустимы; precision недостаточна — inconclusive, без расширения бюджета. [Авторский manuscript](https://kar.kent.ac.uk/33611/45/p63-kaliber.pdf).

ProcessCPU включает user+system всех threads/workers, startup/prep/export/cleanup и failed attempts. `RUSAGE_CHILDREN` учитывает завершённые **и waited-for** children; running child не покрывается одним таким snapshot. Worker kill/reap и partial accounting надо проектировать явно, без doublecount с child self-metrics. [Python resource](https://docs.python.org/3/library/resource.html). Proposed20CPUmin — часть016≤2CPUh, не сверху; отсутствие остатка закрывает optional speed branch. Human-hours reduction неизвестно: число AST или сокращение SQL не заменяет engineering-time audit.

## 4. Обязательная correction retention009 до metrics

В019amendment предложено NDCG≥base−1e−12. Это расходится с принятым более строгим canonical predicate. Его заменить до просмотра009scores:

`retain009 = all_source_cost_encoded6000_card_noCTR_effectiveparam_gates_PASS AND Recall20≥0.5792133072407045 AND NDCG20>0.41444755081727774+1e−12`.

Все значения конечны и получены на exact same selectionQ/C/fullY/evaluator. Иначе schema=base41; tie предпочитаетbase. Semantic/lineage fault означает STOP, а не допустимый fallback слабого блока. Encoded cardinality проверяется на actual6000train включая sentinels, не100Q/raw categories; noCTR/effectiveparameters подтверждаются существующим разрешённым ablation artifact, без дополнительного proof fit. Accepted artifact и retained useful block — разные решения.

Это point-estimate screening, не practicalΔ, noninferiority, CI promotion или доказательство превосходства. Retention включает уже просмотренный selection; bootstrap не устраняет adaptivity. Raw proposal сохранить с этой explicit amendment, не переписывать как будто strict rule существовало первоначально.

## 5.019incumbent и matched016

Eligible incumbent — existing accepted6000pipeline **финального выбранного schema**:008base либо009retained; refit запрещён. Одна prospective cost/cardinality gate выбирает26000для всех четырёх новых GridCfits при PASS; иначе6000только по объявленной resource/cardinality причине, с собственными checks и достаточным остатком. Exhausted totalCPUcap не финансирует fallback. Semantic/API/lineage failures→STOP. После PASS нельзя индивидуально спасти неудачный fit сменой population.

Выбор incumbent плюс completed GridC checkpoints — conditional pipeline selection, не чистый population experiment. Feasibility/Recallguard, deterministic global tie-set и порядок попыток закрепляются заранее. Partial grid раскрывает failed/unattempted configurations; reused incumbent после bounded search не становится заново обученным globally optimal B.

Frozen winner задаёт всем016arms exact population/Q/C/Y hashes, final features/encoding/order, weights/objective/effectiveparams/checkpoint/seed; incumbentwinner означает исходные6000, не новую sample. Базовый B не переобучается. Confirmation/final закрыты: решение и model availability должны предшествовать первому confirmation anchor с положительным compute gap; calendar collision нельзя устранить молчаливым переносом anchors. Actual019code/source/resource approvals и реализация016 остаются будущими gates. Эта review принимает только ограниченную исследовательскую постановку и явные policy corrections.
