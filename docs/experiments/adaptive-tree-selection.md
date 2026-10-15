# Per-model выбор числа деревьев

Новая команда выбирает число деревьев отдельно для B и W.1200 — compute ceiling: обе модели сначала полностью обучаются, затем каждая выбирает лучший prefix1…1200 по conditional query-macro fullY NDCG@20. При равенстве в глобальной полосе1e-12 выбирается самое раннее дерево. Это best observed validation prefix, не доказанный оптимум на новой популяции и не native early stopping.

Общий selector API принимает уже обученную модель и `train_baselines.Prepared` с полным validation Q/Y, включая positive queries с off-C target или пустым C:

```python
from scripts.adaptive_tree_selection import select_best_tree

best, curve, support = select_best_tree(model, validation)
selected = model.copy()
selected.shrink(ntree_end=best)
```

Selector покрывает весь trained tree_count; не сокращает стоимость завершённого fit. Stage scoring явно использует RawFormulaVal, eval_period1 и2threads. Учёт CPU/wall/RSS и внешнего lifetime остаётся у вызывающего процесса. Study CLI также сохраняет/reloads выбранную модель и проверяет exact scores/ranks.

Одноразовый study CLI привязан к принятому018 export snapshot и точному report SHAe62b1f…; это не универсальный raw-to-adaptive-training CLI для произвольного свежего каталога. Перед вызовом требуются ровно аутентифицированные train8–20/selection22–23 exports по пути artifacts/reproduction/public-frozen-bw-once. Config сохраняет original proposal flags и provenance без их переписывания; текущая runtime authority описана отдельно.

```bash
.venv/bin/python -B -m scripts.adaptive_tree_selection \
  --request configs/studies/adaptive-tree-selection-oct2019-once.json \
  --expected-request-sha 6ffe3c7a82854fca25446faf8a580dce83c03584c7f37a81d63d1684b76049a7 \
  --output artifacts/reproduction/adaptive-tree-selection-1200-once
```

Этот пример описывает интерфейс; agent не запускает его без отдельного Root-issued finite operation. Existing once namespace не сбрасывается и не переиспользуется. Root producer73792 завершён exit0; первая независимая проверка69903 завершенаexit1 до curves из-за обратного порядка аргументов directionalnative_equal. [Actualfailure/currentrepair](../backlog-reviews/adaptive-tree-producer-terminal-verifier-failure.md); selectedtrees/curves/metrics не приняты, новый verifier не выдан. Producer ceiling3500CPU/2700wall/12GiB; весь study4200CPU/3600wall от originalSTART включает reservedverifier600/800 иsharedtail100/100, без reset или refill.

Новая ветвь — post-final exploratory development: максимум2новых fits и2400зависимых validation checks, train8–20/selection22–23 only. Original015final26–31 и25reporting-only не переоткрываются;11scientificfits/19looks, отдельно2engineeringfixed300fits018 и принятый исторический publicfixed300 contract неизменны. Новый selected-recipe B/W контраст не равен same-k feature-only эффекту и не является независимым quality confirmation.

[Root adoption/alias regression и точные originals](../backlog-reviews/evidence/adaptive-tree-v2-install-and-issued/publication.json), [canonical install receipt](../backlog-reviews/evidence/adaptive-tree-v2-install-and-issued/canonical-install.json). Independent API tests/oracles/adaptive_tree_selection_audit.py остаётся inert: требует exact helper/accepted-matrix/observedrun bytes и внешний guard, не имеет standalone CLI и не превращает producer flags в acceptance. Первая actual-output проверка FAILED; narrow sourceV3repair/recovery ещё не приняты.
