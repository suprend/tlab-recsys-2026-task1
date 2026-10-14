# Model selection — промежуточный исследовательский пакет

15 октября 2026. Готовы2 из8 независимых model studies; два cross-review и окончательная decision matrix ожидаются. Ни installs, ни fits эти notes не выполняли.

- [01 CatBoost](01-catboost.md): PairLogit с explicit query-normalized pairs против query-weighted BCE; raw IDs исключены из initial P0, categorical handling и native CTR требуют явной политики.
- [02 LightGBM](02-lightgbm.md): CPU LambdaRank как потенциальный второй tuned control; rank_xendcg — отдельный loss, all-zero training semantics различаются.

Встроенная metric видит только переданные candidate labels; LightGBM native NDCG присваивает all-zero query1. Выбор/early stopping должны использовать объявленный full-Y evaluator006, сохраняя estimand. Initial008≤2 fits — smoke, не доказательство well-tuned control. Большой tuning budget M02 не принят автоматически: общий budget и selection reservation фиксируются заранее. Для task1 центральны automation features либо method, обгоняющий tuned boosting с experimental evidence. Максимальное число boosters само по себе задачу не закрывает. Hardware/GPU и package availability проверяются отдельно.

[Backlog](../backlog.md) · [Target research](../target-research/index.md). Шесть других model тем и2 reviews остаются в очереди.
