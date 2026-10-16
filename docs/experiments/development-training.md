# Обучение новых development-моделей

`fit_development(model, train, validation, *, max_iterations, check)` из `scripts/development_training.py` обучает модель один раз и выбирает число деревьев по отдельной validation-выборке. `max_iterations` — положительный потолок, а не заранее выбранный размер модели. Validation обязательна; отсутствие положительных полных targets обнаруживается до fit.

Поддержан свежий точный `CatBoostClassifier`: числовой `train_baselines.Prepared`, CPU, Logloss, две нити, явные `iterations`, `use_best_model=False`, `allow_writing_files=False`. Допустимы 18 перечисленных в исходнике constructor options. Ranker, GPU, подклассы, уже обученные модели, native early stopping/OD, aliases и дополнительные fit kwargs не поддержаны. Расширять область поддержки нужно явно.

После полного fit helper вызывает существующий [`select_best_tree`](adaptive-tree-selection.md): все prefixes от 1 до потолка, full-Y conditional macro-query NDCG@20, глобальная полоса 1e-12 и меньше деревьев при равенстве. Положительные validation-запросы с пустыми кандидатами и покупками вне кандидатов сохраняются. Не используется native Logloss для выбора checkpoint. Ошибка callback, короткий fit или неполная кривая приводят к исключению; повторного fit и fallback к потолку нет.

Возвращается `DevelopmentFit`: `full_model`, отдельная `selected_model`, `trained_ceiling`, `selected_trees`, полная `validation_curve`, `validation_support`, `training_accounting`. Усечена только копия; исходная обученная модель остаётся полной. Выбранный размер может совпасть с потолком, если это результат complete validation selector.

`validation_support.informative_candidate_groups` возвращает уже вычисленное
`group_accounting(validation)[-1]['informative_groups']`: число групп кандидатов с
положительными и отрицательными labels внутри C. Это диагностическое поле;
исходный словарь support selector не изменяется. При корректных
`y = 1[item ∈ fullY]` и фиксированном C ноль означает, что каждая группа пустая,
полностью отрицательная или полностью положительная, поэтому NDCG не зависит
от перестановки её кандидатов. Scores и rankings при этом могут меняться.
Положительное число не гарантирует неплоскую наблюдаемую кривую или достаточную
статистическую мощность. Поле не включает отказ, resampling, увеличение потолка,
дополнительный fit или изменение выбора prefix.

Caller отвечает за временное разделение train/validation, зрелость и полноту Q/C/Y, происхождение фичей, source pins, сохранение моделей/метаданных, отчёт и общие CPU/RSS/wall ограничения. `check` обязателен и кооперативен; native blocking/startup/cleanup/exit требуют внешнего наблюдения. Helper не выдаёт разрешения на обучение.

## Обычная команда нового development-training

`scripts/train_development.py` вызывает этот helper ровно один раз для одной новой модели. Входы — два отдельных independently accepted [development collections](development-collection.md) с ролями `train` и `selection`; `--validation-acceptance` здесь обозначает selection collection. Проверяются прежние lineage/schema/maturity/chronology правила. Confirmation/final входы не поддержаны. Команда не строит коллекции из raw и не является историческим frozen/smoke runner.

Все параметры ниже обязательны; задайте их явно, включая положительные целые ресурсные пределы. Пути acceptance должны принадлежать этому checkout и соответствовать принятому collection lineage. Output directory должен отсутствовать, его родитель — существовать:

```bash
uv run --locked python -B -m scripts.train_development \
  --train-acceptance "$TRAIN_ACCEPTANCE" --validation-acceptance "$VALIDATION_ACCEPTANCE" \
  --output "$NEW_OUTPUT_DIRECTORY" --max-iterations "$MAX_ITERATIONS" \
  --train-query-cap "$TRAIN_QUERY_CAP" --max-matrix-rows "$MAX_MATRIX_ROWS" \
  --depth "$DEPTH" --learning-rate "$LEARNING_RATE" --l2-leaf-reg "$L2_LEAF_REG" \
  --random-seed "$RANDOM_SEED" --cpu-seconds "$CPU_SECONDS" \
  --wall-seconds "$WALL_SECONDS" --rss-bytes "$RSS_BYTES"
```

Используется свежий numeric CPU Logloss classifier с двумя threads, `Plain`, `bootstrap_type=No`, `use_best_model=False`, `allow_writing_files=False`. Train cap 1–6000 выбирается по SHA256(query_id), затем query_id до чтения labels. Validation не ограничивается числом Q: сохраняются отрицательные Q, positive fullY вне C и пустые C. Matrix row cap 1–1320000 применяется к каждой матрице; превышение вызывает отказ, а не усечение validation. Depth поддержан 1–16, learning rate — (0,1], L2 — конечное неотрицательное число, seed — 0..2³¹−1.

После full fit до явного потолка выбирается лучший **наблюдаемый validation prefix внутри этого потолка**. Команда сохраняет `full.cbm`, `selected.cbm`, `recipe.json`, полный curve/support/chosen k/параметры и data/source identities в `report.json`, а также scores всех validation-кандидатов в `validation-scores.npz`. До статуса `complete_produced_unreviewed` selected snapshot загружается заново; его scores и scores selected-копии сравниваются с full-model prefix при tolerance 1e-12. Source/data pins проверяются перед fit и после persistence. Ошибка не вызывает повторный fit, fallback или успешный результат; partial output остаётся с failed report, когда его запись возможна, и не переиспользуется.

CPU/RSS относятся к текущему процессу, wall — ко входу в `run`; проверки выполняются между операциями и через callback. Это **кооперативные** limits: native fit/SQL/hash/save/load могут блокировать или превысить их до следующей проверки. Поддержаны macOS/Linux с `resource`; старый data loader сохраняет собственные DuckDB 2GB memory/temp settings. Нужен внешний supervisor для полной startup/blocking/cleanup/exit области и всех ресурсов; CLI не даёт hard whole-tree bound или разрешение на ML. Loader dependency/lock witness сохраняется в report. Выбор не доказывает глобальный оптимум, CV, независимое качество или экономию обучения.

Этот source CLI закрывает отсутствие обычного caller на уровне реализации; на TMP-байтах прошли [12 CODE-unit тестов](../backlog-reviews/development-cli-code-acceptance.md) с actual NumPy/orchestration/helper и FakeML/selector/accepted-data I/O. Native helper и end-to-end CLI остаются **UNRUN**; реальных CatBoost/DuckDB/ML/data действий не было. Предложенный отдельно human budget 50CPU/65wall относится только к прежнему helper native test, не к запуску этого CLI. Прочие будущие non-frozen callers должны явно перейти на helper. Исторические smoke/019/016/frozen процедуры и принятый selector сохранены.

На новых байтах helper и `tests/test_development_training.py` 2026-10-16
прошли все 11 CODE-unit тестов: 10 прежних lifecycle-сценариев и один новый
accounting/ranking/selector сценарий. Реальные тела этих функций и маленькие
NumPy-массивы при fake ML проверили validation Q=1, fullY={99}, C={1,2}, три
prefix-перестановки, ноль informative groups, кривую `(0,0,0)`, выбранный prefix 1
и неизменный исходный support. Завершение принято с terminal exit 0 и известным
reap. См. [приёмку кода](../backlog-reviews/development-training-support-code-acceptance.md)
и [точную квитанцию Root](../backlog-reviews/evidence/development-training-support-code-unit-v1/root-code-unit-acceptance.json).

Реальные CatBoost/DuckDB не импортировались; реальных ML fits и чтений датасета
не было. Native CatBoost body helper остаётся **UNRUN**: fake lifecycle не
подтверждает реальный fit/shrink/serialization. Python/NumPy versions в этом unit
не записаны. Child profile сообщил peak RSS 47,923,200 байт, outer observer —
47,972,352 байт; это разные наблюдения, не сумма и не жёсткие RSS limits. Tool wall
0.256018958 с и outer-body wall 0.301967834 с сохранены с разными областями учёта.
Проверка не подтверждает качество модели, CV или работу на полном источнике и
не выдаёт разрешения на реальное обучение.
