# Candidate generation — промежуточный исследовательский пакет

15 октября 2026. Сохранены10 из12 независимых исследований и reviews групп01–04/05–08; оставшиеся2 studies и1 review продолжаются. Source proposals не меняют baseline автоматически.

| Тема | Записка |
|---|---|
| Full known-catalog reference | [01 exact reference](01-exact-reference.md) |
| Popularity/trends | [02 popularity](02-popularity.md) |
| Direct recent/repeat | [03 recent/repeat](03-recent-repeat.md) |
| Category/brand/price quotas | [04 metadata sources](04-category-brand-price.md) |
| Item-neighbor retrieval | [05 ItemCF](05-itemcf.md) |
| Similar-user/audience retrieval | [06 UserCF/audience](06-usercf-audience.md) |
| Factor retrieval | [07 ALS/BPR](07-als-bpr.md) |
| Neural retrieval | [08 pooling/sequence](08-two-tower-sequence.md) |
| Exact/ANN serving | [09 vector search](09-vector-search.md) |
| Metadata lexical/dense | [10 text retrieval](10-text-retrieval.md) |

[Review 01–04](review-01-04.md) оставляет P0 принятый004: top200 purchase-distinct-users7d +recent20 distinct all-event items7d, union/dedup без refill. U(t) — prior-observed proxy, не stock; full Y сохраняется. Уже купленное не исключается. Exact dot/ANN audit отделён от full CatBoost catalog scoring. HYP004 pop220 требует новой версии validator, не обхода существующего cap200.

Первая возможная новая source family — category quota053 либо ItemCF061, по одному ограниченному опыту. Category mapping использует последний global timestamp bucket<t без backoff на старое чистое значение; ID не заменяется readable code. Normalization-only constant не меняет source order, а category-median в абсолютном log-gap сокращается. ItemCF graph build может стоить Σm² независимо от малого числа requested pairs; missing top-K edge не measured zero. UserCF capped postings — approximation, не полный exact nearest search. Audience event-time и current-cohort rehash — разные допустимые states.

Fair retrieval comparison фиксирует максимальный и фактический |C|, refill/underfill и source-overlap policy; контроль получает то же число уникальных additions. Предложения220/refill или400+100 не утверждены текущим baseline. Feature ablation использует один fixed C, новые retrieval sources оцениваются отдельно по full-Y Recall и downstream NDCG/cost. Ни один source не получает future-positive insertion. [Backlog](../backlog.md) · [Target research](../target-research/index.md).

ALS поддерживает frozen-V fold-in; BPR default confidence/sampler/fold-in отличаются. Versioned implicit0.7.3 wheels проверены для CPU Mac/Windows; Windows CUDA/MPS не обещаются. HYP073 retrieval отдельно,074 generic fixed-C score duplicate051/056.

[Review05–08](review-05-08.md) уточняет equalactualsize/refill controls, replacementlosthits, conditional cohort denominators, daily ALS grain и neural support/availability. Exactdot прежде ANN при166k — предложение costpilot, не benchmark. ANNRecall against exact reference отличается от purchaseRecall; eligiblefilter не исправляет поздноfittedvectors. Textsource работает на небольшом metadata space, ties/expansionpopularity отделяются от semantics. Only11fusion/12evaluation-budget и finalgroupreview09–12 ещё ожидаются.
