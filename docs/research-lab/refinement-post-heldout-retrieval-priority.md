# После015: сначала различить retrieval misses и fixed-C ranking headroom

15 октября2026. **Existing TLAB-012/HYP-001 остаётся более узким первым ItemCF probe, чем построение нового retrieval family061/062. Это порядок будущей проверки механизма/стоимости, не доказательство, что ranking важнее retrieval или ItemCF улучшит качество.** Сдача/воспроизводимость и frozen015 имеют приоритет. Прочитаны только public accepted aggregate reports, определения evaluator/coverage и уже опубликованные studies; actual DB/Y/scores/models/heldout, новые metrics/looks/fits не открывались/не запускались.

## Какие единицы действительно опубликованы

[017collection acceptance](../backlog-reviews/tlab017-collection-verification.md), [007selection aggregate](../backlog-reviews/tlab007-selection-aggregate.json) и [019accepted result](../backlog-reviews/tlab019-strong-output-verification.md) относятся к одной selection population22–23:4000matureQ,73positiveQ,96distinct `(query,item)` fullY pairs,817149candidate pairs. В007 `retrieval_ceiling.unit` прямо равен **full-Y target pair**: C содержит65из96targets; все96принадлежат strict-past observed-catalog proxyU. Это не65positivequeries и не65покупок/order IDs.

| Опубликованная величина | Определение/значение | Чего она не означает |
|---|---|---|
| Micro coverage C | Σ|Y∩C|/Σ|Y|=65/96≈0,677083 | Query hit-rate |
| Positive-query macro C | mean_(Y≠∅)|Y∩C|/|Y|≈0,684932 | Доля queries с хотя бы одним попаданием |
| Query hit-rate | mean_(Y≠∅)1{|Y∩C|>0} | Его exact count в этих summary не опубликован |
|019Recall20 | Conditional query macro0,585127201566 | Micro top20 hits/96 |
|016frozenR2Recall20 | Conditional query macro0,591976516634 | Новый retrieval coverage |

[Coverage SQL](../../scripts/candidate_pilot.py) и [007aggregation](../../scripts/heuristic_baselines.py) подтверждают units: `retrieved_targets` считается по target pairs, macro — среднее per-query fractions. `informative_ranking_queries` дополнительно требует negative candidate и тоже не query hit count. Смешивать эти величины нельзя.

Буквальный source-free пример: два queries, Y={a,b}/{c,d}. C₁ ловит2/0targets, C₂ —1/1. В обоих случаях micro и macro Recall0,5; query hit-rate соответственно0,5и1. Следовательно, даже оба опубликованных Recall не определяют query-hit. Это аналитический counterexample, не новый анализ приватных labels.

Старый accepted004pilot6000Q/121Y/92retrieved и new-pair21/48 относится к другой population. Нельзя складывать его с selection96/65. В selection007 recent top20 попал в3из38new-pair targets против6уpopularity, но это **ranking hits**, не coverage всей C по new-pair. Где именно лежат31targets вне C, эти aggregates не устанавливают.

## Что известно о потолке и запасе

Для любого ranking внутри C, `Recall20_q ≤ min(20,|Y_q∩C_q|)/|Y_q| ≤ |Y_q∩C_q|/|Y_q|`. Поэтому0,684932 — опубликованная верхняя граница macroRecall20. Она не обязательно достижима при20позициях, если у query больше20retrievable positives. Относительно019 остаётся не более≈0,099804 macroRecall; относительноR2≈0,092955. Это аналитические разности опубликованных scalars, **не измеренный выигрыш достижимого scorer**.

NDCG ceiling нельзя получить как65/96 или1−NDCG_B. Для binary relevance oracle bound каждой query равен `DCG(min(20,h_q))/DCG(min(20,m_q))`, где h=|Y∩C|,m=|Y|; нужно распределение этих counts по queries, не totals. Из public summaries оно не восстанавливается. Ни новый NDCG oracle, ни slice сейчас не предлагается вычислять.

Наличие31out-C target pairs показывает реальный ограничитель currentC. Catalog96/96 показывает, что в этом sample misses не вынуждены unknown-to-U товарами; оно не доказывает наличие ItemCF support, stock, других покупателей или доступного нового adjacency. Fixed-C ItemCF никогда не вернёт эти31targets. Retrieval, напротив, может добавить новые hits и одновременно потерять прежние из-за квоты; «нашёл новые» ещё не net gain.

## Почему один механизм требует двух отдельных задач

[Sarwar et al.,2001](https://www.ra.ethz.ch/CDstore/www10/papers/519/node10.html) разделяет item similarity и prediction aggregation; [performance section](https://www.ra.ethz.ch/CDstore/www10/papers/519/node18.html) рассматривает precomputed top-k table и quality/storage trade-off. Их rating/MAE experiment не является доказательством purchase-NDCG gain. [Linden et al.,2003,§How It Works](https://webpages.charlotte.edu/sakella/courses/cloud09/papers/AmazonLindenSmithYork.pdf) отделяет дорогую offline similar-items construction от online aggregation. Быстрый lookup не оплачивает автоматически построение графа.

Existing [TLAB-012/HYP-001](../backlog.md) запрашивает similarities только для fixedC×history≤20. На100queries максимум440000requested pairs до cache; exact intersections популярных postings всё равно дороги. Retrieval061 требует найти neighbors во всём допустимом item domain: top100 output не ограничивает `Σ_v m_v(m_v−1)/2` discovery/build work. Успех fixed-C cost gate поэтому не принимает retrieval feasibility.

## Единственное refinement existing HYP-001

После015 — лишь отдельно разрешаемый **100past-selected-query fixed-C support/cost gate** existingTLAB012: тот же C200+20/no-refill,0candidate replacement, daily available snapshot7d, binary view-user overlap, historycap20, diagonal/self-contribution policy заранее фиксированы. Сначала literal own-only/zero-overlap/topK-missing/cold/boundary tests; затем оплаченные postings construction/intersections/cache/cleanup, unique requested pairs, degree-tail/state size, support и defined-fraction. Existing proposal≤30min/6GB не становится разрешением этим note. No new fits нужны для correctness/cost; later≤2fits возможны только по отдельному frozen budget/label reservation.

Контргипотеза: поддержка отсутствует либо scores лишь повторяют direct history/popularity. Низкая coverage/дорогие exact intersections опровергают практичность этого MVP; хорошая support/cost не доказывает quality. Отсутствующее topK edge нельзя записать как observed zero. Self-subtraction до норм и shortlist нужна именно для claim других пользователей.

Если позднее открывается **отдельный061retrieval protocol**, current no-refill baseline остаётся reference; treatment150popular+20recent+50ItemCF/refill сравнивается с новым matched-refill control, а не незаметно с004. Original200+20 union versus treatment150+20 exclusion, actual uniqueC-size, gained **и lost** fullY pairs, macro/query-hit units фиксируются заранее. Это уже существующий [grouped review](../candidate-generation/review-05-08.md), не дополнительная здесь гипотеза/пилот.

Concrete backlog/report action: сохранить две ветви раздельно и назвать65/96target-pair coverage. Очередь после frozen015: existing012support/cost прежде full061graphbuild; никаких нынешних policy/fit/heldout amendments.

## Publication boundary

Archived15October2026 as a refinement of existing hypotheses, not a new independent idea round or an execution allowance. The original research result is retained; subsequent code/review progress does not retroactively change its historical snapshot. No actual source/model/target/fit job was run for this note.
