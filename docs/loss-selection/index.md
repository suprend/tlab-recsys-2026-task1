# Loss selection — промежуточный исследовательский пакет

15 октября 2026. Готовы2 из6 независимых исследований; два cross-review и integrated decision matrix ожидаются. [01 Pointwise BCE](01-pointwise.md) и [02 Pairwise](02-pairwise.md) различают conversion-after-view и purchase ranking, query-weighted full-C objective и negative sampling.

P0 остаётся existing008 BCE versus PairLogit на одинаковых Q/Y/C/features. Mature all-zero query сохраняет BCE gradient; censored не negative; C empty остаётся evaluation miss. Ни BCE score после sampling/class weights, ни соседский score не объявляется автоматически calibrated purchase probability. HYP027 inverse-inclusion weights — отдельный P1 после008, не обязательное расширение initial budget; focal пока deferred. HYP035 дублирует008, HYP036 mixed negatives — отдельный P1. Исходный L02 предлагает `(t,t+H]`; coordinator appendix фиксирует отличие accepted clock `[t,t+H)` без скрытой замены протокола.

[Backlog](../backlog.md) · [Target research](../target-research/index.md). Остальные4 loss темы,2 reviews и окончательный выбор не завершены.
