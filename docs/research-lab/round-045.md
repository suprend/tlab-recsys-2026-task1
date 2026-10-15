# Round045 — инварианты находят дефекты, oracle задаёт правильное значение

**Design-only refinement rounds018/043/044.** Никаких installs, code/tests/jobs, source scans, models или WIP019/016reads. Текущий016 scope не расширяется. Новых HYP нет: это уточнение independent verification, не новая feature-quality mechanism. Отличие от018 — явная матрица предпосылок и surviving mutants: property test полезен ровно настолько, насколько корректно сформулирован law и способен его нарушить конкретный дефект.

## Четыре первичных основания

[Claessen–Hughes, QuickCheck2000](https://www.cs.tufts.edu/~nr/cs257/archive/john-hughes/quick.pdf) разделяют проверяемую specification, генерацию cases и контроль их распределения; conditional properties имеют предпосылки. Большое число random inputs без нужных boundary cases не гарантирует полезное покрытие.

[Chen–Cheung–Yiu1998](https://www.cse.ust.hk/~scc/publ/CS98-01-metamorphictesting.pdf) выводят follow-up tests из отношений между inputs/outputs. Такой relation дополняет oracle problem, но само отношение должно следовать domain semantics, а не удобному поведению текущей реализации.

[NoREC](https://www.manuelrigger.at/preprints/NoREC.pdf) сравнивает фильтрацию с отдельным вычислением истинности predicate. [TLP](https://www.manuelrigger.at/preprints/TLP.pdf) использует partition по TRUE/FALSE/NULL. Это способы находить DB logic/optimization defects; два SQL paths не доказывают, что общий business predicate или source contract правильный. Их benchmark bug counts не переносятся на нашу вероятность обнаружения.

## Закрепить объект проверки

Чистая feature function получает raw event bag, fixed Q/C, typed registry и explicit context: source bounds/coverage, UTC anchors, availability assumption, category resolver, NULL/duplicate/window policies. Результат — exact keyed physical rows с core/support/coverage/masks. Transformations применяются к этому объекту; они не обещают сохранить query sampler, Y, retrieval ranks, trained model или все manifest hashes.

«Универсальный» ниже означает «для всех допустимых inputs закреплённого contract». Это не означает отсутствие предусловий на типы, полный source prefix или metadata scope. Нельзя выдавать bag за set, known empty за unknown conditional key либо coverage за user observed age.

| Преобразование | Корректный law и предпосылка | Что неверное может пройти |
|---|---|---|
| Перестановка rows/global timestamp peers | Keyed counts/distinct/MAX-recency и whole-bucket metadata неизменны; peers не получают rowid-order | Неверное окно или constant-zero function |
| Future suffix≥t | F(t) неизменно при fixed source/context/Q/C; будущие anchors/Y не фиксированы | Ошибка lower bound, count×2 |
| Одна точная копия eligible event | Соответствующие raw counts+1; exact projected distinct, recency и bucket value-set неизменны | Дефект другой action/grain/window, не затронутый witness |
| Uniform doubling всего bag | Counts×2, distinct/recency неизменны; matching shares прежние при fixed metadata/coverage | Raw counts×2 вместо правильныхcounts также соблюдают scaling law |
| Partition/merge | Raw counts складываются; distinct — cardinality union sets; last-time — MAX; ratio из восстановленных supports | Одинаково неверный predicate в обеих ветвях |
| Nominal ID bijections | Обратное mapping fixed Q/C/output сохраняет equality-based values; NULL отдельно | ID-dependent sampler/ranking не подпадают под law |
| Action renaming | Bijection одновременно переименовывает source tokens, registry predicates и capability annotations | Неверное matching окно остаётся неверным |

User/item bijections выполняются отдельно внутри roles. Обмен ролями user↔item не является универсальной симметрией: Q адресует пользователя, C товар, а registry/retrieval grains различны. Renaming actions не создаёт нового разрешённого action в current016; это conceptual interpreter law, current validator вправе отвергать неканонические tokens.

## Где простые laws особенно опасны

Distinct partition totals нельзя складывать: один user в обеих частях даёт1+1, но union cardinality1. Raw partition сохраняет exact duplicates; `UNION DISTINCT` незаметно меняет count. Среднее partition ratios неверно при разных supports; нужен `Σnumerator/Σdenominator` при общей classification/null policy, причём denominator0 остаётсяNULL. Unknown category нельзя «восстановить» самостоятельным resolver каждой partition: latest global bucket должен вычисляться на полном согласованном metadata context.

Coverage24h при fixed S/T не меняется от duplication. Для merge разных observed intervals нужна длина их union, а не сумма при overlap; source completeness из event min/max не следует. Future suffix law нарушается законно, если одновременно передвинуть declared source bounds/coverage. Поэтому metadata, coverage и sampling context фиксируются явно.

Константная0реализация проходит permutation/future-suffix и некоторые пустые merge проверки. `N'=2N` проходит additivity и whole-bag scaling; окно48h вместо24h проходит эти же laws. Share с denominator толькоC может оставаться в[0,1] и быть permutation-invariant. Global first-row metadata иногда пройдёт peer permutation, если fixture содержит одинаковые значения. Эти surviving mutants делают literal expectations необходимыми, а не доказывают бесполезность metamorphics.

## Independent spec-derived oracle

Минимальный direct-list oracle вручную фильтрует `[max(S,t−W),t)`, считает raw rows/non-NULL sets и MAX full-prefix timestamp, разрешает весь latest metadata bucket и вычисляет matching-count shares. Predicate/window/category/denominator helpers compiler не импортируются. Public schema/hash/path transport validators можно разделять механически, но oracle не должен использовать producer F для expected-domain discovery или готовый producer category resolver.

Literal gold отдельно фиксирует ненулевые counts, lower-bound/cutoff,8d recency, zero denominator, known-empty и unknown-category NULL, off-C denominator. Поэтому общий semantic bug двух expected paths обнаруживается третьей явно заданной таблицей. Typed transport проверяется отдельно: exact BIGINT/null bitmap до float32 model encoding; shared rounding не должно дать согласованный false pass.

## Один будущий≤32row acceptance experiment

Proposal: заранее записанный bank; исходный и каждый transformed input имеют≤32synthetic rows, включая повтор event/entity, off-C event, global mixed-NULL peers, события ровноlower/cutoff и older-prefix recency. Fixed legal005 ASTs,0fits; derived permutations/duplications не читают новые source данные. Evidence заранее перечисляет применимые laws/предпосылки и exact expected tables, не только count generated tests.

Required defect classes: boundary `<`→`≤`, wrong24/168window, raw dedup, summed distinct, truncated recency, candidate-only denominator, NULL→0, first-peer/backoff metadata, missing empty key/physical row и rounded BIGINT. Accept: ноль literal/oracle mismatches и каждый non-equivalent mutant отвергнут содержательным gate; stale hash rejection сам по себе не detection formula fault. Surviving mutant означает reject предложенного test adequacy claim, не автоматический production defect.

Generation, comparisons, minimized witnesses, failures и cleanup входят в отдельно разрешённый future CPU/wall/RSS ledger; бюджет сегодня не предоставлен. Passing tiny tests не является математическим доказательством, full source approval или exhaustive B oracle. Current018 numeric scope остаётся sampled, а selected016 source proof требует своей отдельной реальной приёмки.


## Source-audit appendix —15Oct2026, recency merge

Исходный текст сохранён. Сокращение «MAX-recency» в таблице означает recency, вычисленную из MAX eligible timestamp: R=t−max(event_time). При partition merge максимум берётся по last timestamps; если объединять уже вычисленные recencies для одинакового t, нужен MIN non-NULL recency, с NULL для полностью пустой eligible history. MAX самих recencies был бы ошибкой. Laws предполагают допустимые physical ranges после transformation, без BIGINT overflow. Это уточнение собственной формулы, не вывод из testing papers.
