# TLAB-007: независимая проверка frozen synthetic implementation

15 октября 2026. **Verdict: accept для code/synthetic scope TLAB-007. Материальных findings не найдено.** Это не утверждение production metrics или resource benchmark. Реальный pilot не запускался reviewer; ему по-прежнему нужны coordinator acceptance artifact с фактическими pins и явный production go.

Полностью прочитаны [heuristic_baselines.py](../../scripts/heuristic_baselines.py), [test_heuristic_baselines.py](../../tests/test_heuristic_baselines.py), конкретная implementation specification и handoff. Проверены интерфейсы используемых accepted 003/004/006 helpers. Оба owned файла были untracked, поэтому проверено полное содержимое; пустой обычный diff не использован как доказательство. Actual SHA-256 совпали с handoff: code `db00b2375fed1083d4bf9b45ef4535793d36ffeaa537050a07e99c61dad13ee4`, tests `b68d294482765a9f04dc6a408a9bc52b4bf1a0d7697f50caf50c6a0f9b2837cf`.

Reviewer не менял repo/Git/code/deps/data, не устанавливал пакеты и не обучал модели. Root005 не затронут. Исполнялись только synthetic fixtures с temporary files, а не реальные Q/Y/C, source DuckDB или production acceptance artifact.

## Фактическое исполнение

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_heuristic_baselines.py -v
```

**Exit 0; Ran 17 tests in 0.457s; OK.** Общий suite и другие WIP tests не запускались. TemporaryDirectory end-to-end test действительно проходит tiny DuckDB → Parquet → pinned upstream manifests → accepted scorer runner → полный ranking export; это больше, чем проверка чистых comparator functions.

## Ranking и временная семантика

[Три comparator](../../scripts/heuristic_baselines.py#L49) соответствуют заданию: popularity по distinct purchase users descending; recent-source-first по существующему recent rank ascending NULLS LAST; last-view7d по последнему view timestamp descending NULLS LAST. Общий fallback — popularity descending/product ID ascending. Последний comparator сохраняет микросекунды integer arithmetic; tie-break детерминирован. Recent-source-first не выдаётся за полноценную view-recency.

[View materialization](../../scripts/heuristic_baselines.py#L110) перебирает отдельные anchors, join только selected fixed `(user,product)` pairs, окно `[t−7d,t)`, type=view. Оно охватывает **все C pairs**, включая товар вне recent20, отличает cart/purchase от view, исключает всю секунду anchor и старые просмотры до левой границы. User×catalog не строится. Raw duplicates не меняют max timestamp.

[make_rankings](../../scripts/heuristic_baselines.py#L132) сохраняет каждый Q и выдаёт ordered **all-C**, проверяя exact membership и cardinality. Нельзя вставить cold positive, убрать ранее купленный товар или обрезать output до K. Пустые C и зрелые пустые Y сохраняются. Censored seam передаёт `targets=None`, а не частичные positives. Production v1 protocol допускает только полностью зрелый pilot; это явно отделено от общего censor-safe ranking/evaluation seam.

Meaningful доказательства: hand golden для трёх разных порядков; отдельный literal row-iteration oracle на случайных events; exact lower/upper boundaries; разные anchors; перестановки/дубли peers и future suffix; 23-item shortlist, positive за позицией20 и positive вне C. Последний даёт full-Y Recall=1/3 и NDCG≈0.469278726, сохраняя все23 C в output. Oracle не вызывает production sort/window helpers.

## Evaluation, slices и bootstrap

[report_rankings](../../scripts/heuristic_baselines.py#L156) передаёт accepted evaluator006 полный независимый Y, включая targets вне C. Получаются все четыре **estimands**: conditional macro-query, all-query zero, conditional user-macro и all-user zero; внутри них evaluator считает NDCG/Recall/AP/RR. Это разные axes, не четыре взаимозаменяемых ranking metrics. p(nonempty) и mature/positive/censored counts сохраняются.

Query slices пересчитывают evaluator на подмножестве Q с прежним полным Y. Label slices явно названы target-pair micro Recall@20 и считают попадания на исходных позициях; repeat-only target set не подставляется в основной NDCG denominator. `any_C_pair_view7d` означает поддержку просмотром пары среди кандидатов, а не вычисленную полную user history. Cold/repeat/catalog slices и retrieval ceiling имеют объявленный grain.

Bootstrap использует accepted006 на тех же Q/users/full targets у обоих rankers; все зрелые пользователи, включая empty-only, остаются cluster population. На каждую пару rankers и NDCG/Recall выдаются все четыре estimands, user_count, defined/undefined draws; нулевой positive-support draw не превращается в нулевой score. Tests проверяют24 summaries, пустую population и undefined conditional intervals. User/time uncertainty и tiny positive support не выданы за promotion evidence. Математика bootstrap006 не дублируется отдельной самодельной реализацией в007.

## Provenance и ресурсы

[verify_accepted_inputs](../../scripts/heuristic_baselines.py#L206) требует explicit version1/approved acceptance, complete reports, matching run IDs/lineage/protocols и actual fingerprints каждого требуемого upstream code/lock/input/artifact. Важно:004 должен потреблять точные original003 Q/Y, а не производную копию или похожий filename. Runtime сверяет эти paths/hashes с anchor artifact refs; labels не берутся из пересобранной retrieval выборки. Canonical protocol входит в validated upstream identity; run-directory имя не является доказательством принятия.

Scorer identity дополнительно включает собственный SPEC, actual scorer/evaluator/dependency code hashes, consumed pins, protocol, bootstrap settings и acceptance-file SHA. Tests действительно изменяют content Q/Y/C/code/source/report, убирают pins, меняют статус/lineage и создают same-byte alternate Q artifact — всё это отклоняется соответствующими gates.

[Runner](../../scripts/heuristic_baselines.py#L273) использует persistent RunDeadline/StageLedger; общий срок включает provenance/fingerprinting. Checks до/после expensive stages и перед complete, SQL interrupt и cooperative RSS ceiling6GiB закрывают прежнюю проблему one-shot interrupt. Limits:≤6000Q,≤1.32m C rows,≤1800s,≤1000 bootstrap draws, threads2/DuckDB2GB/spill2GB. Длинная Python операция останавливается на следующем cooperative gate; OS-level preemption не заявляется.

Failure tests проверяют early invalid acceptance, RSS failure и поздний TimeoutError: сохраняются failed report, elapsed cost/stages/достигнутые counts и identity, а complete metrics не публикуются. Successful synthetic runner сохраняет measured engine peak/RSS, scan bounds, row counts, ordered all-C output и artifact SHA. Peak engine memory не складывается с process RSS; это отдельные counters. Полный real-data runtime/RSS пока **не измерен**.

**Условия следующего шага:** coordinator pins accepted004/003 contents и выдаёт go; production runner проходит resource gates и сохраняет actual aggregate report. Этот code accept не заменяет проверку реальных consumed fingerprints, результата/row counts и measured limits после запуска. Необходимых code fixes до такого ограниченного запуска не найдено.


## Coordinator execution acceptance — 15 октября 2026

После code acceptance выполнен bounded real pilot на exact accepted004/003 inputs с version1 fingerprint JSON. Run12e8f035f62ffb3fe01dcb3b8fe633c56837d866562182b70f43acbb491b97a8 complete:29.551s/RSS921387008bytes, engine spill0. Actual canonical identity/input/code/uv hashes, ranking output SHA и complete stages проверены; limits соблюдены.

Независимый read-only source oracle заново вычислил35143 last-view pairs; Python comparators проверили все18000 exported all-C списков/3 678804 позиций. Независимые literal formulas Recall/NDCG/AP/RR по полномуY и четыре query/user estimands совпали. Recent/last-view aggregate equality не объявляется идентичностью rankings: один positive query имеет другой top20 без metric change. [Aggregate report](../experiments/heuristic-baselines.md) сохраняет counts, CI direction, target slices и стоимость.

**TLAB007 accepted**, включая measured execution evidence. Model training/quality generalization не заявлены; report exploratory,104positivequeries и три development дня не являются lockedconfirmation. Root005 code review/resource gate остаётся отдельным prerequisite сильного boosting.
