# Round051 — численная ошибка scores и точность ranking replay

**Primary-source research и собственный аналитический вывод; не изменение frozen tolerances.** Никакие real data/models, holdout или live019/016 outputs не открывались. Рассмотрены deterministic binary full-Y метрики принятого006 и опубликованный009 replay. Главный вывод: bounded raw-score error, одинаковый ranking и одинаковые aggregates — три разные гарантии. Одно нельзя автоматически объявлять другим.

## Источники и область их утверждений

McSherry–Najork показывают, что tied scores задают лишь частичный порядок: разные допустимые перестановки могут менять IR measures и сравнение scoring functions. Их алгоритм вычисляет среднее по всем согласованным перестановкам, первоначально мотивированное оценкой дискретных отдельных features. Это другой estimand, а не рекомендация незаметно заменить наш product-ID tie-break. [Авторская работа ECIR2008, §1–2](https://marc.najork.org/papers/ecir2008.pdf). Официальный [sklearn.ndcg_score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html) также явно показывает усреднение ties по умолчанию; это подтверждает необходимость указывать convention.

Goldberg объясняет ограниченную точность представления и накопление rounding errors при floating-point arithmetic. Это основание различать точное равенство целочисленных ключей и численное сравнение scores, но не готовая гарантия стабильности NDCG или bitwise equality на другом hardware. [Goldberg1991, авторская статья в официальном переиздании Oracle](https://docs.oracle.com/cd/E19957-01/806-3568/ncg_goldberg.html). Документация [CatBoost predict](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_predict) отдельно требует согласовать feature names/order и prediction type; scalar tolerance не компенсирует применение другой схемы или scoring prefix.

## Аналитическая граница: где epsilon действительно помогает

Пусть на exact C одной query имеются finite scores s и повторные s′, причём для каждого item `|s′ᵢ−sᵢ|≤ε`. Тогда:

`(s′ᵢ−s′ⱼ) ≥ (sᵢ−sⱼ)−2ε`.

Следовательно, строгий порядок пары гарантирован, если исходный gap больше2ε. При gap=2ε возможен tie, и ID-policy уже влияет на порядок. Это собственный элементарный вывод, не эмпирический результат статьи. Для относительной/смешанной tolerance вместо общего ε нужны соответствующие per-item bounds, а для пары — их сумма.

Если `s(K)−s(K+1)>2ε`, top-K membership сохраняется. Но внутренние перестановки top-K всё ещё возможны: Recall останется прежним, NDCG/AP/MRR могут измениться. Для гарантии exact ordered top-K достаточно сохранить каждую соседнюю границу внутри prefix и границу с хвостом; при ties нужно отдельно доказать неизменность соответствующего score equality/ID ordering. Просто большой cutoff margin не решает внутренние ties. При |C|≤K границы с хвостом нет.

Без margin нет универсальной оценки metric error, стремящейся к нулю вместе с ε. Контрпример K=1: Y={a}, C={a,b}, исходные scores отличаются на δ>0, a выше; противоположные ошибки величины меньше ε меняют порядок, когда δ<2ε. Recall и NDCG меняются с1 на0 при сколь угодно малом положительном ε. Поэтому «scores совпали до1e−12» само по себе не означает «ranking совпал».

Для нашего K=20 рассмотрим единственную покупку, переместившуюся с позиции20 на21. Изменения individual Recall, NDCG, AP, RR равны соответственно `1`, `1/log₂(21)`, `1/20`, `1/20`. Это literal construction, не наблюдение REES46. При73positive queries contribution одного такого изменения в conditional query-macro Recall равен1/73; в NDCG —`1/(73·log₂(21))`. Малый score delta поэтому не обязательно мал относительно обсуждаемого quality effect.

## Полный Y и достаточное доказательство replay

Границы выше предполагают неизменные exact Q/C/Y. Удаление target вне C изменит Recall/AP denominator и IDCG, даже если каждый score и весь ranking совпали точно. [006](../../scripts/ranking_metrics.py) использует полный Y, distinct binary targets, удерживает zero-Y/empty-C queries и отдельно определяет conditional/all-query estimands. Numeric replay обязан сохранять эти отношения; candidate-intersected labels не заменяют full Y.

| Предъявленное доказательство | Что оно подтверждает | Чего не подтверждает |
|---|---|---|
| Bitwise-identical keyed scores, IDs и inputs | При одинаковом deterministic sorter — одинаковый ranking | Source/formula correctness или качество на новых днях |
| Score delta в пределах tolerance | Численное согласие native inference | Ranking identity без margin либо прямой проверки |
| Exact ordered top-K и exact full Y/Q | Те же математические значения текущих @K metrics | Равенство tail ranking или корректность происхождения scores |
| Только совпавшие aggregates | Совпадение конкретных summaries | Совпадение queries, рангов или per-query errors: возможна компенсация |

В [опубликованном009 audit](../backlog-reviews/tlab009-model-output-verification.md) raw scores проверялись с rtol0/atol1e−12, затем независимо вычислялись full-Y metrics, bootstrap и decision. [Архив source](../backlog-reviews/tlab009-model-oracle-accepted-source.md) не заявляет отдельную exact equality всего ranked C. Это достаточная причина не переименовывать исторический scope в доказанную bitwise/ranking identity; actual discrepancy здесь не установлен.

## Предложение для будущего executable replay

Рекомендуемый контракт различает две проверки: model-to-score numerical replay с уже объявленной tolerance и evaluation replay с exact ordered top-K IDs, полными targets и independently recomputed estimands. Exact full-C permutation нужна лишь если deliverable утверждает именно её; для текущих @20 estimands mathematically достаточно exact ordered prefix, при separately verified complete C/score keyset. Сравнение агрегатных floating values сохраняет объявленную tolerance и фиксированный порядок вычисления; integer IDs, counts, membership и ranks approximate не становятся.

Отдельно проверяется frozen selection decision. Если каждый candidate metric известен только с ошибкой η, разность двух metrics может отклониться на2η; аналогично Recall(candidate)−Recall(B). Значит, scalar comparison tolerance не является новым tie band и не разрешает расширить Recall guard. При неоднозначности около границы нужно честно указать предел доказательства и выполнить существующий independent policy check, без нового arm, look или подбора epsilon после результата.

Минимальный будущий literal test набор: stable margin>2ε; crossing при margin<2ε; exact score tie с большими integer IDs; неизменный ranking при добавлении Y вне C, меняющем denominators. Это prospective test specification, без выполнения/нового allowance. Наконец, deterministic replay уменьшает computational uncertainty, но не sampling uncertainty73positive queries, date shocks или development selection bias. Точное воспроизведение слабого/отрицательного результата остаётся точным воспроизведением, а не подтверждением generalization или causal recommendation gain.
