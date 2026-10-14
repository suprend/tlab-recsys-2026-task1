# Candidate feasibility: popularity200 + recent20

15 октября2026. TLAB-004. **Измеренный development pilot принят: независимый synthetic review, final guard/provenance и полный source reconciliation C.** Генератор и14 synthetic checks приняты logic/guard prereview; это не обучение или качество модели.

Development population B48h:00:00UTC8–10октября,2000past-eligible hash-sampled users/day,6000mature query-days. Это более плотный smoke выбранный по003diagnostics, не финальный выбор population. Full distinct purchase target `[t,t+24h)` не зависит от кандидатов.

## Контракт

Popularity: до200товаров по distinct purchase-users в `[t−7d,t)`, ties по product_idASC. Raw дубли одного покупателя не добавляют голоса. Recent: до20distinct товаров из view/cart/purchase пользователя за тотже7d, по max timestampDESC, затемproduct_idASC. Ранее купленные товары сохраняются.

Объединяем источники, сохраняем оба flags/ranks при overlap, **не добираем** после dedup. Если popular source пуст, остаётся recent; если оба пусты,Cпуст. Времени/показов/stock не выдумываем. Общий C≤220perquery; генератор не читаетY, что проверяется тестом с удалённой label-table. Полные Y присоединяются после материализацииC. Независимый past first-seen scan проверяет C⊆U(t).

## Actual result

| Показатель | Результат |
|---|---:|
| Query-days / положительные |6000 /104|
| Candidate rows / unique(query,item)|1226268 /1226268|
| Candidates/query: min / mean / max|200 /204.378 /220|
| Targets в полномY / прошломU|121 /121|
| Targets вC|92|
| Candidate Recall, micro по всем targets|92/121=76.033%|
| Candidate Recall, macro по104positive queries|78.365%|
| Popular source hits|50/121|
| Recent source hits|70/121|
| Пересечение source hits|28targets|
| Repeat-pair targets retrieved|71/73=97.260%|
| New-pair targets retrieved|21/48=43.750%|
| Queries с ranking-pair signal|84|
| Empty C / censored queries|0 /0|
| Full runtime, fingerprints/export включены|1.476s|
| Process peak RSS|666189824bytes≈635.3MiB|

Repeat-pair означает любое прошлое событие этой пары по всей наблюдаемой истории, не обязательно прошлую покупку и не только7d. New-pair не означает новый товар в каталоге. Остальные20positive queries потеряли все targets при retrieval;5896queries не имеют будущей покупки. Для pairwise training только84queries содержат хотя бы один retrieved positive и хотя бы один candidate без positive label. Остальные группы сохраняются в evaluation, не объявляются подтверждёнными отказами от показа.

| UTC anchor | AllY | Retrieved | Micro Recall | Positive queries | Informative |
|---|---:|---:|---:|---:|---:|
|2019-10-08|36|24|66.667%|30|21|
|2019-10-09|41|31|75.610%|37|30|
|2019-10-10|44|37|84.091%|37|33|

Вывод: observed catalog не ограничил этот Bsample, но простой retrieval уже потерял29/121targets. На new-pair targets покрытие заметно слабее. Это причина для отдельного retrieval experiment; менять C внутри feature/model ablations нельзя. По одному маленькому sample не утверждаем оптимальные quotas или прирост finalquality.

## Проверка/ресурсы/provenance

14scoped synthetic testsPASS: independent Python set/count oracle, source ties/overlap/no-refill, raw duplicates→distinct buyers/history, lower-inclusive/upper-exclusive windows, bought-items retained, empty sources,Cmissing/Yfull, censored≠negative, future suffix/peer permutation, независимость генерации отY, строгий catalog verifier и invalidQ/Y fail-closed. После execution actual parquet counts/uniqueC и coverage aggregation проверены; первоначальная ad-hoc aggregate query имела reserved-alias syntax error, исправленная проверка завершиласьexit0. Это не failure productionrun.

DuckDB2threads/memory2GB/spill2GB, wall deadline1800s с persistent guard, processRSS6GiB ceiling после stages. Engine peak buffer≈0.849GiB, engine peak temp spill0. ProcessRSS иenginebuffer — разные high-water counters, их не складывать. Stage profiler отражает последнийSQLstatement stage; coverage_after_generation содержит несколько statements, поэтому его cumulative_rows_scanned не суммирует всю stage. Walltime/RSS относятся к полнойstage. ProfilingJSON занимаетtempdirectory и не считается engine spill. Scan/state ledger вignoredreport показывает до18 525product keys popularity и11 722recent pairs/day; это не user×catalog.

- Source anchor run:`687afe24b689c0996344892808306685f39afdf56a5dad5aa521c3094ec0305d`.
- Candidate run:`42be82b3e4eda60c3c202e72de381172f1d979efe4c6c5a970d41d1adc5e26f3`.
- Identity fingerprint: actual DB unchanged относительно003; actual Q/Y parquet +anchorrun/report +currentcode/uv.lock SHA. Artifacts ignored, пользовательскиеID не публикуются.

```sh
python -m scripts.candidate_pilot --anchor-run artifacts/anchor-pilot/687afe24b689c0996344892808306685f39afdf56a5dad5aa521c3094ec0305d
```

HYP-004 equal-budget popularity220 vs200+20 здесь **не запускалась**: protocolv1 ограничивает popular_limit≤200. Для неё нужен отдельный явный versioned config change. A7d остаётся отдельным development control, retrieval поA пока не измерен. Следующие005features и007heuristic rankers используют именно этотfixedC, полныйY иaccepted006 evaluator; 004 принят;005/007 production после собственных code/review/resource gates.


[Полный finding/acceptance audit](../backlog-reviews/tlab-004-verification.md) сохраняет независимые проверки и границы результата.
