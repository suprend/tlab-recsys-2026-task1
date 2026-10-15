# Round063 — sparse external-sort replay fullY ranking без dense matrix

**Future-only reference strategy, 15 октября2026.** Прочитан accepted [ranking_metrics.py](../../scripts/ranking_metrics.py); данных, score files, моделей, SQL/EXPLAIN/tests и reserved targets не открывал. Предлагается одна механика replay существующих estimands, не новый metric, inference path или изменение016. Current006 API материализует rankings/scores в Python lists; описанный ниже external reducer ещё не реализован и не принят.

## Основание и входы

[DuckDB external-sort engineering article](https://duckdb.org/2021/08/27/external-sorting) описывает сортировку blocks и merge, способные работать за пределами RAM. Это исторический источник механизма, не performance guarantee текущего lock. [Current workload guide](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads) подтверждает spill и ограничения blocking plans. [Memory-limit docs](https://duckdb.org/docs/current/configuration/pragmas) прямо ограничивают buffer manager, а не все process allocations. Поэтому «out-of-core» не обещает низкий RSS, zero spill или бесплатный disk.

Достаточны sparse relations: Q(query,user,anchor,maturity,stable ordinal), C(query,item), S(query,item,finite rawscore), fullY(query,item). Это O(|C|+|Y|+|Q|) input records, без user×catalog matrix. Event duplicates относятся к upstream target construction; accepted fullY — unique query-item set. Replay не может silently DISTINCT исправлять дублирующий accepted output.

До label opening разрешён только предусмотренный prediction/seal workflow. Replay с fullY начинается **после** соответствующего существующего access gate; это не способ заглянуть в labels при score generation. Зафиксировать model/prediction/input/policy hashes до чтения Y. Ни fake-zero-Y training loader, ни новый callback не предлагаются.

## Конкретный sparse pipeline

**1. Key integrity.** External ordered merge по exact(query,item) подтверждает S keys == C keys, отсутствие duplicates/orphans/NULL keys, корректные physical types и finite scores. Q — независимый domain, не `DISTINCT S`. Empty-C Q сохраняется. FullY keys относятся к Q, но не обязаны принадлежать C, observed catalogue либо history. Raw IDs BIGINT читаются точно; float64→CAST BIGINT после rounding запрещён.

**2. Deterministic topK.** Сортировать S по(query,rawscore DESC,itemID ASC), затем потоково хранить первые K unique IDs каждой query. Query может пересекать reader batches/files: state сбрасывается только при смене query key, не на границе batch. Нельзя глобальный LIMIT K либо сортировку отдельно по файлам принять за per-query topK. `row_number OVER` — альтернативная SQL форма, однако [window documentation](https://duckdb.org/docs/current/sql/functions/window_functions) называет windowing blocking; фильтр rank≤K сам не гарантирует маленький intermediate state.

Score equality здесь точная для принятого score representation; selector tolerance1e−12 не является epsilon-bucket для ties. itemID comparison — numeric nominal key ordering, не float и не lexical string ordering. NaN/∞ отвергаются, +0/−0 как равные scores разрешаются declared ID tie. Native parallel scan order не служит tie-break.

**3. FullY reduction.** Отдельный bounded/external grouping fullY даёт `Nq=|Yq|` для каждой Q, включая zeroY. Join только topK с fullY даёт binary hit vector `h₁…hₖ`, сохраняя rank. Для membership эта малая relation достаточна, но denominator нельзя вычислять после join с C/topK. Такая компрессия не удаляет cold/outside-C misses: они остаются в Nq и ideal DCG.

**4. Query reducer.** При Nq>0 положить `Hᵣ=Σⱼ≤ᵣhⱼ`. Accepted006 definitions восстанавливаются из этих sufficient inputs:

- Recall = `Σhᵣ/Nq`;
- AP = `Σ(hᵣ·Hᵣ/r)/Nq`, именно full Nq, не min(K,Nq);
- NDCG = `Σ[hᵣ/log2(r+1)] / Σᵣ≤min(K,Nq)[1/log2(r+1)]`;
- RR = reciprocal первого hit rank либо0.

Nq=0 оставляет conditional query metrics undefined; existing zero estimands назначают0 при aggregation. Censored Q имеет targets=None/unknown, не Nq=0; входит только в censor counter. Empty-C при positive fullY даёт все четыре0. Новый reducer нельзя реализовать вызовом `QueryRanking` с урезанным Y: тот интерфейс требует full targets, и подмена изменила бы denominator.

**5. Aggregation.** Emit per-query scores в stable Q order, затем per-user sums/counts для четырёх existing estimands. Query macro весит queries, user macro — mean пользователя; их нельзя объединить одним AVG. Все mature users, включая zero-only, остаются bootstrap population. Для будущего paired replay models обязаны совпадать по Q/user/maturity/fullY и использовать один user multiplicity; новых bootstrap replicates сейчас не предлагается.

## Numerical replay не сводится к правильной формуле

В006 `_user_totals` складывает query values по user, а `_estimate` — user totals в порядке первого появления. External SQL SUM или иной partition order могут менять floating reduction. Для максимально строгого replay надо сохранить Q ordinal, порядок query внутри user и первый user ordinal, а scalar rank math выполнять тем же объявленным способом. Иначе нужно явно доказать соответствие **существующим** numerical/decision gates; нельзя автоматически расширить tolerance после disagreement. Exact topK IDs и metric agreement — отдельные obligations, как отмечено в [051](round-051.md).

[McSherry–Najork2008](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ecir2008.pdf) исследуют averaging over tied-score permutations. Это первичное доказательство значимости tie policy, но их tie-aware average — другой estimand: наш deterministic ID tie не заменяется им ради стабильности.

## Literal proof и цена

Future≤32row fixture: четыре Q, одна emptyC/positiveY, одна zeroY, одна censored, одна с двумя equal-score exact IDs2^60 и2^60+1 и третьим target внеC. При K=1 и попадании tie-first ID её Recall/AP=1/3, NDCG=1, RR=1. Перестановка files/batches не меняет результат; duplicateS/orphanY/roundedID обязаны fail. Изменение tie policy может изменить hit и не является rounding noise. Это conceptual gold, не выполненный новый test.

Оплачиваются обе сортировки/key audit, fullY aggregation, topK join, output hashing, disk/spill, cleanup и failed attempts; компактные results не доказывают дешёвый run. Предлагаемый путь нужен только при существующем replay/reproduction требовании и отдельном review, не вместо уже работающего observer. **No new HYP/task:** refinement существующего executable metric replay из050 и memory contracts062; current fits/looks/heldout policy неизменны.
