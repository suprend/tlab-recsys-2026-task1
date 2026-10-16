# График выбора числа деревьев

Рецепт читает только принятые агрегированные JSON с фиксированными SHA, не модели или event data. Повторно используется прежнее независимое свидетельство сравнения curves; нового model evaluation нет.

Из корня репозитория, в активированном проектном окружении по lock:

```bash
python scripts/plot_adaptive_tree_selection.py --summary docs/backlog-reviews/adaptive-tree-results.json --source docs/backlog-reviews/evidence/adaptive-tree-results/originals/result.json --output-dir artifacts/figures/adaptive-validation
```

Output directory должен быть новым. Создаются PNG/PDF и `validation-checks.json`; outputs остаются производными artifacts вне Git. При проблеме font scanner опциональный `--font-cache` принимает локальный `fontlist-v*.json`, соответствующий установленной версии Matplotlib/font-manager. Кэш приватный и не публикуется.

Слева — все 1–1200 checkpoints, справа — увеличение 250–1200 с **отдельной шкалой Y**, без сглаживания. Выбраны B1189/W403; обе модели полностью обучены до 1200. Validation 22–23 октября повторно использует 73 positive-fullY запроса: 2400 зависимых checks, post-final exploratory. Независимый выигрыш качества, оптимум за потолком и экономия обучения не доказаны.

[QA](../backlog-reviews/adaptive-tree-figure-review.md) принят; PDF отдельно визуально не рендерился. Все попытки закрыты/reaped:

| Receipt | Exit | Wall, с | Child RUSAGE CPU, с |
|---|---:|---:|---:|
| [V1](../backlog-reviews/evidence/adaptive-tree-figure/render-v1.json): нет Matplotlib | 1 | 0.103303792 | 0.041913 |
| [V2](../backlog-reviews/evidence/adaptive-tree-figure/render-v2.json): font scanner | 1 | 11.811216625 | 9.633245 |
| [V3](../backlog-reviews/evidence/adaptive-tree-figure/render-v3.json) | 0 | 2.814880084 | 1.260575 |

Это отдельные reported scopes; RSS наблюдаемый, не hard/full-tree bound. Failures/costs сохранены, ML budget не сбрасывался; новых fits/source-data/targets reads нет.
