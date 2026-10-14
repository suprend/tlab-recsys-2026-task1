# Model selection — промежуточный исследовательский пакет

15 октября 2026. Сохранены7 из8 independent studies и cross-review01–04; hybrid08 и review05–08 ещё в очереди. Эти notes не являются real training results.

| Приоритет | Исследование | Решение |
|---|---|---|
| P0 | [01 CatBoost](01-catboost.md) | Required tuned manual boosting, BCE/PairLogit smoke перед tuning |
| P1 optional | [02 LightGBM](02-lightgbm.md), [03 XGBoost](03-xgboost.md) | Один дополнительный learner только при явном вопросе и budget |
| P0/P1 | [04 cheap behavior](04-cheap-behavior.md) | Accepted heuristics007; bounded ItemKNN/ALS отдельно |
| P1 | [05 candidate-conditioned MLP](05-tabular-neural.md) | Один компактный reranker вместо user-ID table |
| P1 | [06 pooled two-tower](06-two-tower.md) | Frozen shared-space scalars на fixed C; retrieval отдельно |

[Review 01–04](review-01-04.md) требует фактического checkpoint selection по full-Y evaluator006. LightGBM default native metric отключается явно; XGBoost callback фиксирует dataset/metric/direction; CatBoost native overfitting/use_best_model не подменяют full-Y criterion. Native candidate IDCG и all-zero conventions не равны конечной метрике. BCE сохраняет все mature C-groups, PairLogit — informative pairs; это сравнение packages/populations, не чистый loss-only эффект. Pair/query/object weights имеют разные API.

[CPU dependency принята](../experiments/cpu-environment.md), но tiny API fit не real baseline, 2 smoke fits не tuned B. Development collection017 и её semantic/lineage gates предшествуют model experiments. Brand/code metadata extractor не появляется автоматически в numeric manual18; raw IDs не numeric semantics. ALS051/056 — одна family; neural coordinates/checkpoints требуют frozen version/availability. MLP candidate-conditioning исключает single cached user vector; two-tower допускает dot retrieval, но это отдельный C experiment. Авторские model budgets не складываются, Windows/GPU доступность не считается измеренной.

[Backlog](../backlog.md) · [Target research](../target-research/index.md) · [Task1](../task1-requirements.md).

[Integration review M06](integration-review-06.md) закрывает sampled-loss population, actual availability и whole-timestamp-bucket cap ambiguities. Это дополнительная проверка одной note, не недостающий grouped review05–08.

[07 Sequential](07-sequential.md): optional SASRec-small против last-bucket и matched pooling. Permutation-invariant timestamp buckets — явная адаптация; cap50bucket отличается от50events. Sampled loss/support и encoder availability общие, legacy code не готовый purchase-pipeline. Только08 и groupedreview05–08 остаются в этой family.
