#016 fixed-procedure draft — independent source/API critique

**READ-ONLY DRAFT CRITIQUE; не code acceptance и не fit permission.** 15Oct2026. Просмотрены requested `tlab-feature-program-experiment.py` и неизменные public helper interfaces005/008/program loader. Никакие модули не импортировались, модели/данные/approvals не открывались, tests/fits не запускались. Draft менялся автором: initial c2d4194005a9acc1364b725b4b365d3a8cd8e49ac9804114f0144de72a58541c; typed-delta revision74aa93c2bda15c4c232ba55bfdb03a96ab8a52551ac904a711a1d9cd23c8fa7a; последний narrowly inspected22ae8426c06470229a347f8749a01f68ddcd41ab1eb803b68ff9ba10b2ec2d17. Ни одна версия не названа frozen. Сохранены original findings и статически видимые fixes; parent orchestration строится отдельно.

## Concrete blocker1 — typed loader boundary; исправлен в draft

Accepted [selected_union](../../scripts/feature_program_collection.py) выдаёт `arms[slot].columns` как list[str]. Accepted [append_program_features](../../scripts/program_model_data.py) требует `extra_columns` как list[{name,dtype}], каждый element с exact двумя keys. Initial draft сохранял names и передавал их обоим train/selection loader calls.

Static exact repro: `extra_columns=['auto_…','auto_…','auto_…']` до source connection попадает в `type(field) is not dict` и вызывает `ValueError('Invalid declared physical delta')`. Healthy actual arm не мог дойти до fit; это конкретное противоречие interfaces, не omission будущего parent. Minimal fix — derive ordered typed fields из independently accepted physical_delta, names оставить отдельно для ordered model schema.

Root исправил: slots хранят names и typed physical_delta, оба loader calls получают второй объект. Narrow reread74aa… и22ae… подтверждает это. Dynamic/native tiny seam test ещё не выполнялся этим reviewer; root обещал включить его до freeze. Полного verdict из чтения исправления не следует.

## Concrete risk2 — allclose не доказывает ranking fidelity; guard усилен

Initial worker проверял loaded prefix через `np.allclose(scores,replay,rtol=0,atol=1e−12)`, затем ranking/metrics строил только из original scores. [NumPy allclose](https://numpy.org/doc/stable/reference/generated/numpy.allclose.html) задаёт числовую tolerance, а не order equivalence.

Literal analytic witness,0execution: IDs[1,2], original[0,0], replay[−5e−13,0]. Allclose проходит; deterministic ID tie даёт original first item1, replay first item2. При fullY={1} top1 quality меняется. Это не обнаруженное расхождение CBM и не утверждение, что CatBoost обычно так сохраняет scores; это недоказанная граница существующего guard.

В22ae… Root добавил equality всех `base.rankings(selection,scores)` и `base.rankings(selection,replay)` перед единственным metric evaluation. Поэтому заявленная ranking fidelity теперь имеет отдельный guard; rawscore tolerance не менялась, новых fits/prefixes/search looks нет. Требуется tiny near-tie regression и обычный output observer, не дополнительный quality experiment.

## Remaining concrete risk3 — hash-then-parse разных snapshots

В22ae… `verify_worker_context` отдельно вызывает `_sha/_pins`, потом `_read` того же context/parent/slot/approval/claim и игнорирует SHA, который `_read` возвращает вместе с parsed body. Это не гарантирует, что использован именно checked snapshot.

Статический сценарий: issuer slot содержит CPU allowance100 и его digest в неизменном context. `_pins` читает correct slot bytes; перед `_read` slot меняется на cpu_seconds6540 при тех же candidate/token/output. Bound1…6540 пропускает новый allowance, а worker identity продолжает ссылаться на исходный digest. Final guard перепроверяет context/input pins, но не связывает **parsed slot snapshot** с issuer SHA. Parent supervision может предотвратить расход сверх исходного allocation, однако это не исправляет ложную provenance использованного body.

Minimal necessary correction: compare `_read`-returned raw-byte SHA с exact issuer reference для каждого указанного receipt и использовать только parsed body этих bytes. End repins сохраняются отдельно; «проверили раньше и ещё раз позже» не заменяет binding в точке чтения. Proposed regression — mocked swap между initial hash и read, без данных/Pool/fit. Это remaining draft finding; implementation Root не изменялась reviewer.

## CatBoost semantics: конкретных противоречий здесь не найдено

[Official fit](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_fit) использует eval_set для native overfitting/best-iteration selection; use_best_model требует validation. Draft fit получает только training Pool и resource callback, explicit use_best_model=False, без eval_set/early_stopping/init_model. Сверка `tree_count_==trained_iterations` отвергает partial model. Поэтому корректная формулировка — fixed-procedure Logloss, не native early stopping по fullY.

[Pool weight](https://catboost.ai/docs/en/concepts/python-reference_pool) — object weight. Reused `group_accounting` вычисляет1/|Cq| на каждом existing row; сумма по nonempty query равна1. All-negative/all-positive mature groups остаются в BCE; emptyC query не получает fabricated training row, но сохраняется в evaluation. Не требуется group_id, чтобы pointwise classifier учитывал эти weights. Это не pairwise objective и не user-macro training mass.

[Predict](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_predict) применяет trees `[0,ntree_end)`. Draft отдельно сохраняет full trained model и shrunk prefix, проверяет оба counts/schema и предсказывает RawFormulaVal с inherited prefix. Не называть prefix «обучено меньше деревьев»: trained и scoring counts различны. Pool/fit/predict явно2threads; name/order проверяются loader/schema, ndarray автоматически не выравнивается по names.

`frozen_model_parameters` закрепляет Plain/Logloss/No bootstrap/Newton/backtracking/iterations/depth/L2/seed/representation; effective float32 LR сверяется отдельно. Actual defaults допроверяются после fit. Это inherited **procedure**, не гарантия same learned splits или одинаковой information capacity B+3. Matched population/source/weights и native effective parameters остаются обязанностью независимого observer.

[NumPy lexsort](https://numpy.org/doc/stable/reference/generated/numpy.lexsort.html) использует последний key главным: helper `(itemID,−score,group)` действительно сортирует group→scoreDESC→IDASC. Raw exact integer keys сохраняются, epsilon selector band не используется как score tie bucket. FullY evaluation идёт через006, не native candidate-only NDCG.

## Parent/resource omissions — pending gates, не найденные completed-run bugs

CatBoost callback вызывается после iteration; returnFalse прекращает обучение. Он не прерывает Pool construction, один долгий iteration, save/load или predict. Draft stage guards до/после и callback.failure check полезны, но не OS hard cap. [Python3.12 resource](https://docs.python.org/3.12/library/resource.html) определяет CHILDREN только для terminated/waited-for процессов; `_children_cpu()==0` не доказывает отсутствия live descendants.

Поэтому building parent обязан independently supervise live worker CPU/RSS/wall, TERM/grace/KILL/reap, charge tail/persistence/imports и не double-count worker self-report плюс reaped usage. Worker status `complete_produced_unreviewed` и receipt boundary явно оставляют terminal tail parent; это честный промежуточный статус. Нельзя выбрать W или seal success по нему без terminal parent+output proof.

Initial context/guard/claim/directory failures до worker try также требуют parent early-failure evidence. Global four-slot claim, exact approval, failure classification, unused reserves, full candidate cover, no-refill и final source/input pins должны быть проверены на frozen parent/observer. Их отсутствие в текущем worker excerpt — объявленная draft незавершённость. **Итог:** один interface blocker статически исправлен, ranking-claim gap усилен отдельным guard; snapshot-read binding остаётся конкретным замечанием. Full execution approval по этой research note не выдаётся.

## Audit amendment — snapshot binding исправлен автором, narrow reread

Observed revision84d10f3d9e66bcd68371060f4ffd283f8f57efa7c0a054193348ff0c15969ace. Original risk3 выше сохранён как finding на22ae…, **не текущий unresolved verdict**. `_read_ref` теперь сравнивает возвращённый `_read` digest с issuer SHA того же parsed byte snapshot; parent/slot/approval/global claim читаются этим способом. Context напрямую проверяет SHA своего parsed snapshot. Worker final pins включают original dynamic refs, context и consumed receipt. Parent launch связывает actual parsed context SHA с issued digest. Typed delta и exact ranking guard остаются. Это статическое закрытие конкретного замечания; snapshot-swap fault tests и full frozen parent/observer review ещё не выполнялись этим reviewer. Global acceptance не выдаётся.

Дополнительная primary-source граница без новых замечаний к draft: отсутствие eval_set оставляет callback `info.metrics` с training `learn`, согласно official fit docs. Эти training-iteration loss values не становятся четырьмя extra selection looks, пока не используются для нового selection/early stopping. Обратно, `weight=1/|Cq|` гарантирует сумму **коэффициентов loss**1 на nonempty query, а не равенство градиентов, positive-query mass или прямую оптимизацию conditional fullY NDCG. Бинарные y и веса остаются inputs supervised fit; внешний ranking criterion — отдельный estimator. Рекомендуемая report подпись: «query-normalized pointwise Logloss при fixed procedure», без обещания calibration, causal purchase probability или одинаковой effective capacity B+3. Новых параметров, fits, metric looks и source jobs это уточнение не требует.
