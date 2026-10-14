# Fixed-C heuristic baselines: development smoke

15 октября 2026. TLAB-007. Измеренный exploratory результат на принятом B48h pilot, без обучения и подбора параметров. [Код](../../scripts/heuristic_baselines.py) прошёл [независимый review](../backlog-reviews/tlab-007-verification.md); coordinator отдельно проверил production provenance, all-C rankings и все четыре estimands независимым source/metric oracle.

Входы неизменны:6000 зрелых queries8–10октября,104 positive queries,5988 зрелых пользователей,121 distinct target pairs и1 226268 candidate pairs. Ground truth — полный независимый Y, retrieval тот же [top200 +recent20/no-refill](candidate-pilot.md). Все5896 mature empty queries остаются в population; targets вне C остаются misses. Это более плотная provisional аудитория для smoke, не окончательно выбранный deployment target.

## Три точных scorer

- Popularity: distinct purchase-users7d по убыванию, product ID по возрастанию.
- Recent-source-first: существующий recent-source rank по возрастанию, NULL после известных; затем popularity/ID. Это source recent20 по всем типам событий.
- Last-view7d: последний view строго в [t−7d,t) для **всех** fixed C pairs, NULL после известных; затем popularity/ID.

Каждый scorer возвращает весь прежний C, без вставки positives, удаления прошлых покупок или дополнения короткого списка. Last-view materializer нашёл35143 поддержанные пары. Shared pool покрывает92/121 targets; micro candidate Recall76.033%, positive-query macro78.365%. Это retrieval ceiling для Recall при достаточно длинном ранжированном списке, не NDCG ceiling.

## Измеренные top20 результаты

| Scorer | Conditional query NDCG20 | Conditional query Recall20 | All-query zero NDCG20 | All-query zero Recall20 |
|---|---:|---:|---:|---:|
| Popularity |0.073133|0.187500|0.001268|0.003250|
| Recent-source-first |0.489135|0.649038|0.008478|0.011250|
| Last-view7d |0.489135|0.649038|0.008478|0.011250|

Conditional user-macro совпал с conditional query-macro в этом sample: каждый из104 positive пользователей имеет один positive query. All-user zero NDCG/Recall: popularity0.001270/0.003257, recent/last-view0.008443/0.011189. Эти величины не заменяют друг друга и не являются вероятностями покупки.

Recent и last-view получили одинаковые агрегаты/positive-query scores, но их rankings не идентичны: у одного positive query top20 отличается, сохраняя те же попадания/discounts. Нулевой ΔCI между ними относится к наблюдённой метрике этого sample, не доказывает эквивалентность scorer.

| Target-unit slice | Popularity hits/targets | Recent-source-first | Last-view7d |
|---|---:|---:|---:|
| Все full-Y targets |23/121|76/121|76/121|
| Repeat pair |17/73|70/73|70/73|
| New pair |6/48|6/48|6/48|

Repeat pair определяется по любому past событию пары, не только покупке и не только7d. New pair не означает новый catalog item. Recent-выигрыш здесь сосредоточен на повторном интересе; покрытие/ранжирование new pairs остаётся bottleneck. В этом Bsample cold targets нет; отсутствие cold ошибок не обобщается на исходный месяц.

## Uncertainty и предел вывода

User-cluster bootstrap использует5988 mature users,1000 draws, seed2026; все1000 draws определены. Для recent minus popularity: conditional ΔNDCG20=0.416002, percentile95% CI[0.334521,0.493214]; ΔRecall20=0.461538, CI[0.370672,0.553402]. Интервалы описывают эти exploratory данные; user clustering не покрывает общий временной шок, population selection и дальнейший validation search. Это не locked confirmation и не promotion автоматизации.104 positive queries недостаточно для тонких feature/loss conclusions.

## Cost и воспроизводимость

Run identity:12e8f035f62ffb3fe01dcb3b8fe633c56837d866562182b70f43acbb491b97a8. Exact accepted003/004 lineage, output/input/code/uv.lock pins и scorer spec входят в identity; ignored acceptance version1 проверяется до computation.

Полный runtime29.551s, process peak RSS921387008bytes≈878.7MiB; engine peak buffer1030749836bytes≈983.0MiB, engine peak spill0. Counters не складываются. Время включает source/provenance preparation, view scans, rankings,24 bootstrap summaries и export. Limits1800s/6GiB, DuckDB2threads/2GB/spill2GB — cooperative gates, не OS hard kill. Профили вложенных stages отражают последний SQLstatement, их нельзя наивно складывать как complete scan ledger.

17 scoped synthetic tests приняли independent code review. Coordinator source oracle заново вычислил last-view для всех C и сравнил каждый элемент всех18000 exported lists:3 678804 ordered pairs совпали с тремя независимыми comparator правилами. Hand-formula oracle заново посчитал Recall/NDCG/AP/RR и четыре query/user estimands; все совпали. Actual canonical run identity, upstream/current code/input hashes, output SHA и complete status всех stages проверены. Labels не использовались при ranking; идентификаторы/списки остались в ignored artifacts.

Следующий этап —100-query cost gate ручных features, versioned label-independent expansion train/selection population и сильный настроенный boosting контроль. Эти эвристики дают необходимый sanity baseline, но не закрывают требование task1 об automation либо превосходящем tuned boosting методе.


## Fixed reference на принятой selection collection — 15 октября 2026

Те же три заранее определённых scorer выполнены без новых learned fits на017selection22–23:4000matureQ,3995users,73positiveQ,96fullYtargets,817149fixedCrows. C содержит65/96targets; candidate microRecall=.677083, positive-query macro ceiling=.684932. Catalogproxyпокрывает96/96. [Aggregate artifact иbootstrap](../backlog-reviews/tlab007-selection-aggregate.json) сохраняет все четыреestimands, slices и200user-cluster draws.

| Scorer | Conditional query NDCG20 | Conditional query Recall20 | All-query zero NDCG20 | All-query zero Recall20 |
|---|---:|---:|---:|---:|
| Popularity |0.105936|0.233855|0.001933|0.004268|
| Recent-source-first |0.388390|0.571429|0.007088|0.010429|
| Last-view7d |0.388390|0.571429|0.007088|0.010429|

Recent/last-view одинаковы наpositive top20 этого sample; это неуниверсальнаяэквивалентность. Target-micro hits:pop24/96 (repeat18/58,new6/38),recent/last53/96 (repeat50/58,new3/38). Conditional query Recall учитываетполныйY поquery и неравенtarget-micro53/96.73positiveusers имеютпоодномуpositivequery; conditionaluser/query metrics здесьсовпадают.

Run c6e7cedb100aa1650e3ab7ce06f6c225d7b69b954d246f27d157d5382368be9f complete:7.359517s/RSS749092864bytes, engine spill0. Независимый sourceoracle проверил22804last-viewpairs, все12000rankingrecords/2451447positions иliteralRecall/NDCG/AP/RR во всех4estimands. Canonicalidentity/currentacceptedinputs/code/outputSHA иcomplete stages сверены. Это3fixeddevelopmentlooks/0learnedfits;200bootstrapdraws неустраняютadaptiveselectionbias. Значение0.388selection нельзясравниватьс0.489старого6000Qpilotкакmodeldrift:querydays/populationразличны.

Audit: первыйCLIoutputroot отклонёнexisting-pathguard доattempt/computation; исправленлишьCLI. Послеsuccessfulimmutableexecution summarywrapper получилKeyError дляневерного report['evaluations']; underlyingcomplete report не менялся/неперезапускался, wrapperпрочиталactual nestedmetrics. Двеошибкиподготовки/чтения сохранены, ихнеизмеренное времянеприравниваетсянулю и нечислитсяновымvalidationlook.
