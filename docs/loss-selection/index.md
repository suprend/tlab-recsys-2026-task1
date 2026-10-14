# Loss selection — согласованный исследовательский пакет

15 октября 2026. Завершены6 независимых studies и2 grouped cross-reviews. Исходные notes сохранены, необходимые поправки явно отмечены; trained winner и final target этим не выбраны.

| Семейство | Записка | Минимальное решение |
|---|---|---|
| Pointwise | [01 BCE](01-pointwise.md) | Query-weighted all-mature C-groups |
| Pairwise | [02 BPR/PairLogit](02-pairwise.md) | Explicit informative pairs, mass1/query |
| Metric/listwise | [03 Lambda/Yeti/XE](03-listwise.md) | P1 одна замена после tuned control |
| Contrastive | [04 full/sampled softmax](04-softmax-contrastive.md) | Support и actual sampling law до logQ |
| Multitask | [05 auxiliary/pretrain](05-multitask-pretrain.md) | P1 purchase+any только против matched controls |
| Integrated validation | [06 model×loss decision](06-decision-validation.md) | Shared budget/chronology/full-Y checkpoint criterion |

[Review 01–03](review-01-03.md) фиксирует общий clock [t,t+H) и right-open maturity. Исходные right-closed recommendations сохранены, но не используются скрыто в008. BCE all-mature C versus PairLogit informative-only меняет population; same-informative BCE — отдельная абляция. Для полного p×n набора weight1/(pn); sampled pairs требуют actual probabilities/counts. Censored не negative; full Y вне C остаётся miss; zero-purchase query сохраняется в evaluation.

Early stopping реально использует full-Y criterion006, не native candidate-only metric с внешним отчётом после выбора. Full CE, sampled contrastive и InfoNCE не взаимозаменяемы; uniform law, in-batch law и mixture probabilities проверяются отдельно. Unbiased denominator не делает finite-sample log/gradient unbiased. Multiple positives исключаются из negatives; unobserved не dislike. Auxiliary view/cart/purchase labels могут перекрываться, не softmax-классы. Encoder freeze — protocol, не новая hypothesis; HYP066 rejected duplicate.

Initial008 BCE/PairLogit — smoke, не strong tuned B; авторские GPU/trial budgets не приняты. После collection017 и tuning выбрать максимум один новый loss mechanism с неизменными Q/C/features и общим ledger. [Backlog](../backlog.md) · [Target research](../target-research/index.md).

[Review04–06](review-04-06.md) завершает серию: all-positive CE может выравнивать logits без relevance contrast; with/without-replacement/dedup estimators различаются, conditional mixed sampling law обязателен. Head-frequency correction требует согласованного conditional mean. Endpoints/maturity и positive decision-compute gap фиксируются prospectively: selection labels24Oct00 не оставляют времени до confirmation24Oct00. Confirmation пока закрыта; кандидат переноса25Oct либо shortenedselection не принят автоматически. Компактный MVP: BCE/Pair smoke→bounded tuned B→один выбранный loss/representation contrast, без декартова model×loss search. HYP075/076 не сформулированы, validation не выдаётся за новизну.
