# Research round 010: первый bounded tuning сильного manual control

Статус: prospective design для review, без fits/scans/code/acceptance writes. Прочитаны исходное strong-control proposal, round007, metadata009design и появившийся [independent008aggregate evidence](../backlog-reviews/tlab008-smoke-aggregate.json). HYP105/106 остаются зарезервированными: это уточнение существующего tuning, не новая гипотеза качества. Root009-owned code и frozen008 не изменены.

## От чего начинается новый шаг

Evidence008 сообщает independently accepted smoke outputs:6000train queries/1227213candidate rows,92informative groups,5908all-negative,101retrieved-positive rows,114positive-fullY queries; explicit pairs20741. Selection4000Q имеет73positive queries. Эти counts подтверждают support и исполнение, но6000запросов BCE и92группы PairLogit не являются одинаковыми статистическими задачами; пары внутри query не создают20741независимое наблюдение. Smoke metrics уже раскрыты на selection, поэтому новый план может быть prospective **только относительно новых fits**, а не слепым относительно прежних результатов.

Исходная сетка objective×depth4/6 при одинаковом L2=3 — четыре полезные конфигурации, но не доказательство сопоставимой регуляризации. Название после нового этапа: «manual control, выбранный bounded tuning на четырёх configurations». «Хорошо настроенный» в task1 требует опубликованных границ поиска и оставшихся ограничений, а не объявления глобального optimum. Benchmark Grinsztajn et al. учитывает стоимость hyperparameter search при сравнении tree baselines; он изучает преимущественно IID tabular tasks, поэтому не задаёт нашу temporal-ranking сетку. [Первичная работа, §§3–4](https://proceedings.neurips.cc/paper_files/paper/2022/file/0378c7692da36807bdec87ab043cdadc-Paper-Datasets_and_Benchmarks.pdf).

## L2: фиксировать единицы, не обещать эквивалентность

В CPU v1.2.10 Newton leaf denominator содержит `H+λ·Wobj/Nobj`. Для BCE с rowweight1/C сумма object weights равна6000; здесь средний вес≈0,004889. Для ordinary PairLogit с единичными object weights `Wobj/Nobj=1`, хотя explicit pair mass равна92. Именно object weights определяют L2 scale, а pair weights отдельно входят в производные. Это проверенный source mechanism, не вывод из smoke quality: [ScaleL2Reg](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/algo_helpers/online_predictor.h#L112-L166), [fold weights](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/algo/fold.cpp#L197-L261), [leaf calculation](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/algo/approx_calcer.cpp#L903-L947).

Даже перевод номинального penalty coefficient в нормированный risk не уравнивает curvature, support и objective. Поэтому не предлагается «исправить fairness» одним multiplier92/6000, домножать pair weights после просмотра результата или считать одинаковое λ одинаковой силой shrinkage. Веса остаются1/C и1/(p·n); их формулы, суммы, N объектов/пар и число informative groups входят в manifest.

## Три допустимых распределения четырёх fits

Общие prospective параметры: LR=.05, максимум300trees, checkpoints50/150/300, seed2026, CPU2, без native OD/use_best_model. Effective bootstrap/random strength/leaf method/iterations/backtracking/bias фиксируются явно. Рекомендуется сохранить существующие reviewed smoke значения этих параметров; смена должна стать частью review до fits, не новой осью. CatBoost автоматически выбирает некоторые defaults по objective/параметрам; явный learning rate устраняет эту скрытую зависимость. [Официальные параметры](https://catboost.ai/docs/en/references/training-parameters/common).

| Вариант | Четыре configurations | Предел вывода |
|---|---|---|
| **A, предварительная рекомендация** | depth4: BCE λ∈{3,30}; PairLogit λ∈{0.03,3} | По две попытки objective, отдельный широкий bracket L2; глубина не настроена |
| B | BCE depth4/6 при λ3; PairLogit depth4/6 при λ0.03 | Проверяется глубина; чувствительность L2 остаётся неизвестной |
| C | Только BCE: depth4/6×λ3/30 | Больше внимания одному control; нельзя заявлять настроенное сравнение objectives |

Числа A — предлагаемый инженерный bracket, не теоретически выведенная calibration или обещание охватить optimum. Он оставляет defaultλ3 у обоих objectives и одну дополнительную шкалу в каждой ветви; PairLogit проверяет более слабую регуляризацию, поскольку pair-weight scaling не сокращается как BCE object-weight scaling. Depth4 предварительно ограничивает сложность при малом support. Рекомендация основана на реализации/бюджете, не на том, какой objective выиграл smoke. Вариант выбирается один; проигравшие варианты не становятся последующими бесплатными runs.

## Один критерий и честный ledger

Предложение: сначала feasibility по resource/semantic gates и Recall@20≥R0−0.002, где R0 — **до запуска названный и pinned** popularity007 reference на тех же selectionQ/C/fullY. Среди feasible checkpoints максимум external full-Y conditional macro-query NDCG@20. Exact ties в пределах1e−12: меньше деревьев, затем меньше depth, затем фиксированный objective order/config ID. Threshold и tie tolerance — предложения, не принятые параметры. Если feasible checkpoint отсутствует, результат inconclusive/rejected по причине; нельзя задним числом ослабить guard и назвать победителя strong.

Native NDCG по retrieved labels не заменяет006: полный Y задаёт IDCG, misses вне C сохраняются, zero-purchase Q остаются в предусмотренных estimands. Recall/all-query/user-macro/day/repeat/missing slices — diagnostics; они не выбирают нового победителя. Bootstrap после выбора не делает selection claim confirmatory и не гарантирует precision при73positive queries.

Один300-tree fit даёт три заранее названных selection looks; четыре fits дают максимум12. Уже просмотренные два smoke результата,009ablation и другие прежние решения регистрируются отдельно: «12» не означает всю историю поиска. Failed/partial fit расходует попытку; namespace смена или retry не обнуляет ledger. Частичный checkpoint при crash не eligible, если такая политика не была заранее принята. Никакого refill до четырёх успешных fits.

## Что замораживать до009 и после него

До metadata009: support/population policy, smoke-loss screening decision, fixed50-tree ablation settings, цель whole-block comparison и ≤1fit внутри009; также настоящую заметку о prospective tuning/grid/criterion/budget. Нельзя смотреть009, затем изобретать удобную сетку, сохраняя видимость preregistration. После009решения фиксируется окончательный feature/input manifest и затем исполняется один выбранный tuning plan. Hyperparameters feature automation016 получают уже frozenB; каждая новая ветвь не перенастраивает B бесплатно.

Train cap остаётся6000 и immutable sampling policy; full26000 требует отдельного cost/support решения, не автоматически новых fits. Confirmation25-only/positive compute gap остаётся отдельным неподтверждённым calendar proposal: new decision/model должны реально существовать до первого anchor. Final26+ не используется для сетки.

## Измерение CPU и остановка

Сохранить предложенный общий tuning ceiling≤60CPUминут/RSS8GiB, не расширяя четыре fits. CPU измеряется как actual user+system, wall отдельно: snapshots `getrusage(RUSAGE_SELF)` и `RUSAGE_CHILDREN` в одном coordinator учитывают завершённых/reaped детей; per-worker breakdown не суммируется второй раз поверх этого total. Незавершённый worker требует отдельного текущего счётчика/лимита, не нулевой оценки. [Python resource API](https://docs.python.org/3/library/resource.html).

Preparation, Pool building, checkpoints/scoring, oracle, serialization, failure/repair входят в ledger. Предлагается последовательный запуск workers с остаточным CPU allowance, cooperative wall/RSS checks и сохранением partial costs при kill/error; measurement failure запрещает claim соблюдения CPUcap. Engine memory setting не hard RSS limit. Точный остаток общего6CPUh без измерений прежних producer invocations не выдумывается. Достигнутый итог — ограниченный проверяемый tuning шаг; no-gain/inconclusive результат остаётся содержательным результатом, без power guarantee.
