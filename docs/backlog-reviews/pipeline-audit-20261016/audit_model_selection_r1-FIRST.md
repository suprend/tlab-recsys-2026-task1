# FIRST — audit_model_selection_r1

Режим: независимый read-only file audit frozen HEAD `c538de4097322715fccac494e2b2becc3279e8e1`, manifest SHA256 `7e2e871f148beac5b9fce3aa23970b370db0c8fdc9eac89958fb6342a4d2a41a`. Original root: `/Users/mdpospelov/tlab-recsys-2026`. Ниже existing defects, не утверждение о регрессии. Точный состав и ограничения чтения — в собственном pins JSON; остальные FIRST не читались.

## 1. Область и фактические цепочки

Полностью прочитаны `train_development.py`, `development_training.py`, `adaptive_tree_selection.py`, `heldout_contract.py`, `ranking_metrics.py`, три development tests, heldout-contract test и adaptive oracle. Релевантные тела/строки прочитаны в `train_baselines.py`, frozen reproduction, heldout prediction metadata validator, historical strong worker и обоих strong oracles. Settings: smoke/grid, frozen constructor/effective parameters, adaptive request. Прочитаны experiment guides, adaptive/native-helper historical reports, Task1 requirements; backlog/model-selection/research index использованы для дедупликации. Это не чтение всех 632 файлов.

Обычный вход: `train_development.main→run→load_runtime→verify_collection→validate_training_phases→input_pins→prepare_dataset→group_accounting→fit_development→Pool/_BudgetCallback→fit→select_best_tree→positive_layout→_choose_curve→rankings→evaluate→copy/shrink→save→score_parity→artifact hashes/recheck_pins→report`. Dataset/producer lineage подчиняется внешним accepted collections; helper прямо доверяет caller для Prepared provenance.

Study-вход: request/public-loader SHA → verified source snapshots → accepted train/selection exports → два полных 1200-tree fits → staged prefixes каждого arm → copy/shrink → save/reload → full-cohort scores/ranks и comparison с curve. Historical frozen reproduction обучает ровно 300; heldout contract требует trained/scoring300. Эти отдельные процедуры не являются fallback development-helper.

## 2. Подтверждённый дефект проверки артефактов

**P2 — проверять равенство ranking при допуске score parity в historical strong-control.** `scripts/strong_baseline.py:389` принимает reload, если tree count совпал и `allclose(scores,replay,atol=1e-12,rtol=0)`, затем `:390–396` оценивает и сохраняет исходные scores. Порядок replay не сравнивается. Независимые `tests/oracles/strong_output_audit.py:315–316` и `tests/oracles/strong_recovery_audit.py:397–398` повторяют тот же пробел: сравнивают full/prefix численно, метрики считают только из full. Их NPZ-проверки (`:238` / `:317`) также не сравнивают ranking сохранённых scores.

Минимальный свидетель: одна Q, group `[0,0]`, items `[1,2]`, fullY `{1}`, full scores `[0,0]`; serialized-prefix replay `[-5e-13,+5e-13]`, остальная metadata идентична. Все указанные числовые проверки принимают отклонение 5e-13. Full ranking `(1,2)` даёт NDCG@20=1; replay ranking `(2,1)` даёт `1/log2(3)≈0.630929754`. Поэтому producer и оба oracle способны принять опубликованную метрику, не соответствующую выбранному serialized model. Аналогичная замена только NPZ scores также проходит проверку. Ожидается отклонение при любом изменении объявленного deterministic ranking, включая близкие scores; современный development CLI это уже делает в `train_development.py:138`, regression — `tests/test_train_development.py:308`.

Это подтверждённая логическая недостаточность acceptance predicate по статическому контрпримеру. Реальное возникновение такого CBM roundtrip здесь не наблюдалось; дефект не доказывает неверность прежних принятых моделей/результатов.

## 3. Границы, сохранённые контракты и gaps

- Development/helper требуют fresh exact numeric CPU classifier, два threads, no eval_set/native OD/init_model, один fit и полное достижение потолка. Ошибка callback, короткий fit, неполная/неfinite curve вызывают отказ; refit/fallback300 нет. Полный model не усекается; отдельная копия проверяется.
- Selector действительно покрывает prefixes1…ceiling и выбирает первый score ≥globalmax−1e-12. Это best observed in range, не early stopping/global optimum. FullY определяет IDCG; off-C и empty-C positive Q остаются с нулевым вкладом. Нет positive fullY — отказ до fit; все positive C пусты — literal zero curve без native empty prediction.
- CLI сохраняет constructor/full/selected effective params, но не сравнивает reload `get_all_params()` с ними. Score/rank parity проверяется для всех validation C; полная general serialization fidelity или native metadata parity этим не доказана. Это boundary текущего unreviewed producer, не самостоятельный confirmed defect.
- Cooperative SELF CPU/RSS/run-entry wall и callback могут overshoot blocking calls; startup/cleanup/whole-tree не ограничены. Это явно документированный предел. Нового native callback-abort/CLI E2E здесь нет; принятый исторический helper toy проверял только flat8→1 normal path. Предыдущий native CLI attempt failed pre-fit; исправленный CLI E2E остаётся UNRUN.
- Исторические B1189/W403 выбраны после обоих 1200 fits на reused73positiveQ после final. 2400 checkpoints зависимы. Это не CV/новое independent confirmation/доказанный gain/экономия обучения. Frozen300 final CI crossing0 и уже открытый25–31 не меняются.

## 4. Одна quality hypothesis, без нового ID

**Refine existing TLAB-019 / optional TLAB-013 sensitivity; не NEW.** Механизм: максимум длинной dependent curve на 73 positive Q может зависеть от нескольких influential queries, хотя множество соседних k имеет почти одинаковое качество. Counterhypothesis: optimum достаточно устойчив, небольшая перемена k отражает безвредное plateau. Prediction: deletion/resampling users меняет selected k существенно чаще, чем меняет regret относительно исходного максимума. Ближайший будущий опыт: заранее заморозить процедуру и получить per-user/per-prefix contributions, затем отдельно анализировать k distribution и regret; это diagnostic reused-dev анализ, не quality confirmation. Для Task1 помогает честно оценить силу tuned manual control. Cost UNKNOWN; fits/native/data сейчас не разрешены. Дедуп: backlog `:212`, `:468–506`, index references round005/019/069 и wave077 уже содержат tuning/sparse-support/bootstrap/adaptive themes; linked round documents отсутствуют в frozen tracked scope, полного semantic dedup по ним нет.

## 5. Различающая независимая проверка

Root может отдельно назначить native-free bounded regression для producer/oracle acceptance: supplied full/replay/NPZ vectors из свидетеля при одинаковых keys/metadata. Приёмка исправления: identical case принимается, обе near-tie ranking mutations отклоняются, исходный full сохраняется, дополнительного fit нет. Это проверит дефект без CatBoost/SQL/реальных данных; native roundtrip E2E — другая проверка и иной grant.

В этом FIRST не запускались tests, project imports/functions, SQL, ML/native fits, model loads/getters или анализ реальных данных. Выполнялись только чтение/поиск текста, stdlib hashing/JSON для упаковки и readback. Нативная работоспособность и отсутствие всех утечек не установлены.
