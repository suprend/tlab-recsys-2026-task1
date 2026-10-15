# Research lab, round028: reference interpreter для pool026

15 октября2026. **Концептуальный design, без implementation, compiler/test execution, scans, Pool или fits.** Прочитаны [026](round-026.md)/[027](round-027.md), actual [005](../../scripts/manual_features.py) и [018 workflow](../experiments/verification-workflow.md). Root019/009 и frozen artifacts не меняются. HYP137/138 — прежние refinements002/closure; новых IDs, operators или execution budgets нет.

## Три первичных основания, три разных проверки

[Claessen–Hughes, QuickCheck2000, оригинальная статья](https://www.cs.tufts.edu/~nr/cs257/archive/john-hughes/quick.pdf) отделяет property specification от управляемого tester distribution и допускает custom generators. Это основание фиксировать edge-bank и preconditions, не обещание universal proof по finite examples. QuickCheck/Hypothesis dependency не предлагается.

[Rigger–Su, NoREC2020](https://www.manuelrigger.at/preprints/NoREC.pdf) сравнивает optimized query с переписанным reference path, затрудняющим соответствующие оптимизации; [TLP2020](https://www.manuelrigger.at/preprints/TLP.pdf) использует partitions по TRUE/FALSE/NULL predicate. Их эквивалентности помогают тестировать engine, но две SQL формы могут одинаково реализовать неверное бизнес-условие. Поэтому здесь absolute literal goldens + самостоятельный list interpreter первичны; metamorphic/SQL consistency — дополнительные gates. Empty/constant-zero implementation может пройти permutation/future invariance и всё равно неверна.

## Предлагаемая чистая граница

Концептуальный вызов: `reference(eventbag,Q,C,selected_registry,Γ) → expected_rows,expected_delta_schema,coverage_account`. Γ содержит source interval/clock, protocol/endpoints, availability assumption, semantic units, full frozen-B signature map и oracle version. Входы — typed immutable Python tuples/lists, не producer intermediate tables; user/product IDs — exact integers, nullable fields отдельно. Q/C уже независимо закреплены: interpreter не пересэмплирует queries, не придумывает C и не смотрит Y для выбора AST.

Спецификация ограничена восьмью bundles026 и их N/D/R; другие005 operators/grains не аппроксимируются. Registry parsing/public manifest validators можно переиспользовать для mechanical boundary, но формулы не вызывают `_expression`, `_grain_sql`, producer counters/resolver или compiler. Expected key domain берётся из validated C JOIN Q, **не** из наличных F rows. Duplicate C/Q, orphan, unknown signature и source/context mismatch требуют exceptions. Output grain — каждый `(query_id,product_id)`; один user/item ожидаемый scalar broadcast на все соответствующие физические rows, без representative-row shortcut.

Для q вt interpreter сначала формирует **глобальный** допустимый source prefix `S≤event_time<t`. Затем фильтрует type и U/P/I keys: N — длина bag на `[max(S,t−W),t)`, D — размер множества non-NULL explicit projected user/product keys, R — `t−max(event_time)` по всему prefix конкретного event type. Нет события — count/distinct0, recencyNULL и flagtrue. Duplicate строки не удаляются. Для N/D этих noncategory grains дополнительных missing flags нет; coverage24/168 переиспользуется изB.

Source coverage вычисляется геометрическим пересечением declared intervals, не из first event. Это не доказательство completeness/exposure. Missing candidate category не обнуляет noncategory N/D/R. Для существующих category-conditioned B fields сохраняется иной контракт: неизвестная category→NULL, known empty→0; latest **global** past metadata bucket рассматривается целиком, mixed-NULL/conflict не лечится older backoff. Эти context witnesses не объявляются полным numerical B oracle; taxonomy/root/STOP operators в pool вообще отсутствуют.

## Literal witness bank ≤32 input rows

Предложение использует026 fixture:9 event rows,4 Q и5 C, S=1Oct,T=10Oct00UTC. Events: UviewX−1h; два одинаковых UcartX−2h; UpurchaseX−3h; VcartX−8d; VviewY−2h; VpurchaseY−25h; UcartY ровноT; UpurchaseY послеT. C={(U,X),(U,Y),(U,Z),(V,X),(V,Y)} приT; две Q следующего дня имеютemptyC. Z не имеет прошлого. Literal expected anchors:

| Bundle / keyed row | Три expected values в порядке026 |
|---|---|
| L01 / U,X | 1;2;1 |
| L02 / V,Y | 1;0;0 |
| L03 / U,Y | 1;0;1 |
| L04 / U,X | 1;1;1 |
| L05 / U,X | 1;1;1 |
| L06 / V,X | 691200;false;2 |
| L07 / V,Y | 691200;false;0 |
| L08 / U,Y | NULL;true;0 |

Таблица — бумажные goldens, не materialization24columns. Symbolic closure проверяется для всех восьми definitions; numerical producer/reference сравнение выполняется только для уже frozen выбранных slots,≤12 новых physical columns. Для каждого выбранного bundle заранее дописать literal **все пять** expected keyed rows. Проверка пяти F rows и четырёх Q отдельно сохраняетemptyC; zero-Y Q остаются source/evaluation population, хотя Y не является входом formulas.

Оставшиеся≤14 input rows резервируются под нижнюю границу24h/168h и по секунде снаружи, два пользователя на одном item, старый cart вне7d, all-NULL/mixed latest metadata и nullable exact BIGINT `2^60+1`. Boundary rows заменяют/расширяют fixture с отдельными goldens; прежние числа нельзя молча переносить на изменённый bag. Сравнение одного item при двух users ловит pair→item grain substitution, а одинаковый user наX/Y — user→pair.

## Metamorphics и обязательные mutants

Перестановка всех same-timestamp peers не меняет past features; literalT cart ловит ошибочное `≤t`, которое permutation само не обнаружит. Future suffix не меняет строки старогоT, но может изменить более поздние anchors/Y — whole-bundle byte invariance не обещается. Добавление exact past duplicate увеличивает соответствующие raw counts, сохраняет D и timestamp R; expiry последней копии меняетdistinct, промежуточной — нет. Разделение bag на disjoint rows позволяет сложить counts, но D объединяет ключи; TLP-style NULL partition нельзя отбросить.

Typed key bijection сохраняет keyed values при fixed mapped Q/C, не hash sampling/rankingIDties. Literal transport roundtrip сравнивает Python integers/NULL до nullable Int64 construction и SQL/Parquet BIGINT; float64 inference доCAST запрещён. Boolean masks не заменяются numeric0 при transport. Model float32/NaN — следующий отдельный stage, не основание принять rounded source IDs или считать AST aliases.

Named mutants: wrong event,24→168 window, exclusive lower bound, include globalT, sum dailydistinct, dedup rawbag, recency clipped7d, pair aggregate replaced item, missing flag dropped/NULL→0, extra coverage/category mask, missing/duplicate F row и freshly resealed wrong one-row value. Каждый должен быть убит указанным golden/schema/key gate; ordinary checksum mismatch недостаточен для semantic test. SQL common transport допустим, shared expected formulas — нет.

## Acceptance scope и evidence

Для выбранных additions требовать exact delta schema ровно3 columns/slot, expected C rowset, types/order/NULL/integers/booleans и every-row numerical comparison; floats tolerance объявляется заранее. Evidence отдельно считает Q/C/F cover, goldens/mutants, actual formula comparisons, failed/unattempted stages и measured resources после cleanup. Fresh reseal не авторизует входы; pins и external decision остаются отдельными gates.

018 сегодня exhaustive QYC/F rowset, но **numeric manual18 F sampled** и новый registry unsupported. Tiny proof additions не превращает baseline B в exhaustive source-verified matrix и не доказывает real throughput. Future implementation/source execution требует review и existing resource allocation; ошибки →failed partial evidence, не acceptance/retry. Ни universal correctness, ни quality/speedup claim этим дизайном не выданы.
