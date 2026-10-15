# Round042 — что именно доказывает автоматизация016

**Source-only consolidation, без исполнения или новых разрешений.** Прочитаны опубликованные [feature-programs design](../experiments/feature-programs.md), принятый [symbolic generator](../../scripts/feature_programs.py) и prior rounds027/029/034. Runtime collection019/016 в разработке не читалась и не запускалась. HYP137/138 остаются refinements существующего механизма; новые IDs и novelty quota не нужны. Основное уточнение: generation, selection, correct calculation, quality и скорость требуют разных evidence и не заменяют друг друга.

## Первичные работы помогают разделить стадии

[DFS2015](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) строит признаки по связям relational entities и последовательному применению функций; Data Science Machine отдельно включает обучающий pipeline и autotuning. Отсюда заимствуется исполнимая программа расчёта, но нынешний016 не реализует рекурсивный DFS и весь DSM.

[ExploreKit2016](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf) генерирует кандидаты, ранжирует их meta-classifier, обученным на ранее разобранных datasets, затем делает wrapper evaluation через обучение и cross-validation. Static I1/I2 не являются таким learned proposer; его офлайн подготовка тоже не бесплатна.

[OpenFE2023](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) использует FeatureBoost с incremental training поверх base predictions и двухэтапное pruning. Заявление «без полного retraining для каждого кандидата» не означает отсутствие обучения, labels или стоимости. Здесь FeatureBoost/pruning не реализованы. Benchmark numbers этих работ не являются evidence качества, скорости либо экономии человеческого труда на нашем fixed Q/C/fullY.

## Проверяемая граница текущего генератора

`generate_pool` принимает вручную аннотированные типы/роли, actions, temporal context, окна24/168h и конкретные bindings трёх template families. Он порождает actual005 definitions, nominal projection, имена, semantic signatures и full registries. Это реальная, но узкая rule-based генерация: восемь списков definitions не хранятся готовыми. Human prior остаётся в выборе schemas/templates/windows/bindings и I1=L02/I2=L06; generator не выводит смысл неизвестных полей и не учится выбирать признаки.

`allocate_slots` фиксирует два static и два uniform seeded draws с возвращением; collisions расходуют возможность без redraw. Definition-only draw уже опубликован: R1=L01/R2=L05, поэтому выбраны четыре разных bundles. Это воспроизводимый выбор программ до новых016 scores, а не автоматический quality optimizer. Actual execution identity дополнительно требует source/protocol/Q/C/Y/F pins, final019 settings/population/trained iterations/scoring prefix и decision locks.

| Утверждение | Уже имеющееся evidence | Что добавит разрешённое будущее исполнение | Что остаётся недоказанным |
|---|---|---|---|
| Генерация definitions | Код, typed rejection, canonical signatures, independent tiny review | Связь exact programs с exported collection identity | Универсальная генерация по любой новой schema |
| Legal/schema closure | Все8 bundles символически дают3 новых physical columns; aliases B/retrieval отклоняются | Actual schema/types/order и every-row сохранение B | Полезность каждого из8 bundles |
| Selection | Fixed static IDs, PRNG law/state/draw, no-refill | Ledger actual attempted/completed/colliding slots | Learned intelligence или superiority стратегии по двумR |
| Calculation | Independent literals/list oracle выбранных additions на tiny fixtures | Exhaustive source oracle выбранных12 и exact keyed export | Новый exhaustive source proof всех старых B18/B41 |
| Quality | Пока отсутствует real016 contrast | До4 legal pipelines против общего frozen tunedB по fullY | Другие дни/datasets/seeds, причинный online lift |
| Runtime/labour | Symbolic invocation cost и code structure | Actual cumulative costs export/oracle/fit/eval/failures | Speedup или сэкономленные human-hours без отдельного сравнения |

Published independent tiny acceptance содержит21cases/180scalar comparisons, из них60hardcoded literal; author8tests воспроизведены. Это проверка выбранных additions, boundaries и transport. Остальные четыре bundles проверены символически. Она не является real-data throughput, exhaustive numerical acceptance всего pool или разрешением исполнения.

## Что означает «24→12»

Восемь closures по3 дают24 потенциальных физических добавления по сумме bundle widths. Выбранные L02/L06/L01/L05 дают11newcores+1automatic mask=12 actual new physical columns в выбранном union, если downstream export сохранит заявленную схему. Эти24 не были материализованы или отранжированы по labels. Корректная формулировка: «из восьми legal programs allocated четыре bundles с суммарной выбранной шириной12». Формулировка «автоматически отобрали лучшие12 из24 признаков» неверна: выбираются whole bundles по fixed policy, не отдельные columns по measured usefulness.

Equal3-column slots ограничивают physical input width, но count/distinct/recency несут разную информацию и требуют разных aggregate states. Shared preparation оплачивается один раз с видимой attribution; per-arm reads/validation/fits остаются actual costs. Номинальные4slots нельзя подменять четырьмя independent strategy repetitions или считать отсутствие collision доказательством лучшего sampling law.

## Механизмы и честный отрицательный итог

| Механизм | Контргипотеза | Достаточный тип evidence в текущем scope |
|---|---|---|
| Typed templates дают законные новые programs | Результат — aliases или незаконные predicates | Structural closure плюс независимые source/formula gates |
| Short-window/pair/cart additions помогают B | Информация уже выражена B/retrieval либо noise | Frozen fullY contrast с общим B и объявленными guards |
| Static semantic choice полезнее случайных bundles | Наблюдаемый winner случаен/зависит от cohort | Только descriptive best-I/best-R; двух draws недостаточно для strategy claim |
| Общий compiler уменьшает повтор ручного SQL | Ручная работа переместилась в schema/templates/review | Inspectable generated artifacts; human-hours сегодня не измерены |

Если все четыре корректных complete arms не проходят принятый quality gate, valid result — реализованная bounded генерация, подтверждённый расчёт и отсутствие установленного улучшения над frozenB в данном эксперименте. Это содержательный отрицательный результат проверки предложения; превосходство сильного контроля заявлять нельзя. CI через0 означает неопределённость знака, не доказательство эквивалентности. Failed resource attempts дают budget-limited evidence; semantic/lineage fault означает invalid/STOP и не является отрицательной оценкой feature quality.

Итоговый artifact checklist: schema/templates/base aliases; eight-pool signatures/closure; immutable allocation; selected export+independent evidence; exact commonB/settings/population; complete attempts/cost/history; fullY comparison и limitation statement. Он уточняет027/029/034, не требует дополнительных fits/looks, human study, runtime benchmark или нового бюджета. Отчёт должен показать, где человеческий prior остался, и назвать каждое измеренное свойство своим именем.
