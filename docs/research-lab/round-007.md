# Research round 007: масса query, веса CatBoost и единицы регуляризации

Статус: исследование механизма, частично завершённый синтетический API-check; не эксперимент качества и не изменение frozen 008. Проверена установленная версия CatBoost 1.2.10, Python 3.12.14, CPU. Исходный код проверялся по авторскому тегу `v1.2.10`; совпадение номера версии не является проверкой побитового соответствия установленного бинарника исходникам. REES46, реальные модели и репозиторий не изменялись.

Практический вывод: одинаковая масса каждого query задаёт понятный статистический риск, но не делает одинаковый `l2_leaf_reg` сопоставимым между BCE и PairLogit. В проверенном CPU-коде L2 зависит от **суммы весов объектов**. Отдельные explicit pair weights не становятся этой суммой. Поэтому правило «умножение всех весов автоматически сокращается» требует указать objective, тип весов и путь вычисления листьев.

## Какой риск задают веса

Пусть `Cq` — непустой фиксированный candidate pool, `mq=|Cq|`, `yqi` — бинарная покупка в принятом будущем окне, `sqi` — score. Для mature queries `QB` query-normalized BCE определим как

`LB = (1/|QB|) Σq∈QB (1/mq) Σi∈Cq [log(1+exp(sqi)) − yqi·sqi]`.

Реализация через object weight `wqi=1/mq` даёт каждому query суммарный вес 1. Запрос без покупок остаётся в BCE; отсутствие кандидатов требует заранее принятой политики, поскольку `1/0` не определено. Это равенство масс query, а не равенство их градиентов, сложности или числа положительных наблюдений. Нормированная формула weighted Logloss приведена в [авторской документации](https://github.com/catboost/catboost/blob/v1.2.10/catboost/docs/en/concepts/loss-functions-classification.md).

Для PairLogit положим `pq=Σi yqi`, `nq=mq−pq`, `I={q:pq>0,nq>0}` и передадим все `pq·nq` пары positive–negative с `ωqab=1/(pq·nq)`. Тогда

`LP = (1/|I|) Σq∈I (1/(pq·nq)) Σa:y=1,b:y=0 log(1+exp(−(sqa−sqb)))`.

Каждый informative query снова имеет массу 1. All-negative и all-positive queries не создают пар; это ограничение обучающего support, не повод исключать их из evaluation. Покупки из полного Y вне C остаются retrieval misses. Oracle insertion на evaluation не допускается. Если применить sampling или `max_pairs`, необходимо заново определить inclusion weights и estimand: формула полного декартова произведения уже не описывает получившуюся выборку. Документация различает pair weights и object weights и допускает explicit pairs внутри одной группы: [PairLogit](https://catboost.ai/docs/en/concepts/loss-functions-ranking).

Умножение всех весов на положительное `k` сокращается в обеих **нормированных нерегуляризованных формулах**. Оно сохраняет их минимум, когда минимум существует; PairLogit также не идентифицирует общий аддитивный сдвиг scores. Из этого не следует равенство конечных деревьев регуляризованного boosting.

## Что действительно делает CPU-код 1.2.10

`ScaleL2Reg(λ,W,N)` возвращает `λ·W/N`; Newton leaf delta вычисляется как `G/(H+λ·W/N)`, где H — положительная величина отрицательной второй производной в принятом кодом соглашении. Следовательно, для фиксированного листа BCE общее масштабирование object weights умножает G, H и регуляризатор на k, и алгебраически сокращается. Это нормализация единиц L2 внутри learner, а не переписывание весов Pool в сумму 1. Источник: [online_predictor.h, ScaleL2Reg/CalcDeltaNewtonBody](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/algo_helpers/online_predictor.h#L112-L166).

Цепочка происхождения W принципиальна. `TFold::SetWeights` сохраняет object weights и их сумму; при отсутствии нетривиальных весов сумма равна числу объектов. `PairwiseWeights` вычисляются отдельно. Вызов расчёта leaf values передаёт `fold.GetSumWeight()` и `fold.GetLearnSampleCount()`, а не сумму explicit pair weights. См. [fold.cpp](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/algo/fold.cpp#L197-L261) и [approx_calcer.cpp](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/algo/approx_calcer.cpp#L903-L947).

Подготовка CPU target сохраняет raw object weights при единичных group weights. Переданные explicit pairs копируются в competitors с исходным `pair.Weight`; нормализация по общей массе пар здесь отсутствует. В `TPairLogitError` каждая пара умножает первую и вторую производные на `competitor.Weight`, без деления на сумму пар. Источники: [data_providers.cpp](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/target/data_providers.cpp#L163-L310), [error_functions.h](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/algo_helpers/error_functions.h#L764-L809).

Отсюда **вывод по исходникам** для обычного PairLogit, CPU Newton и единичных object/group weights: масштабирование только всех pair weights меняет отношение парных производных к L2. `PairLogit` не входит в специальную ветвь `IsPairwiseScoring`, в которую входит `PairLogitPairwise`; переносить вывод на неё нельзя. [enum_helpers.cpp](https://github.com/catboost/catboost/blob/v1.2.10/catboost/private/libs/options/enum_helpers.cpp#L452-L457).

Ручная иллюстрация для заранее фиксированных двух листьев и одной пары при нулевых scores: `G=.5ω`, `H=.25ω`, `λ=3`, `W/N=1`. Newton step равен `.5/(.25+3)=.153846` при ω=1 и `8/(4+3)=1.142857` при ω=16. Это расчёт формулы, не результат обученной PairLogit-модели. Одновременное масштабирование λ и pair weights восстанавливает этот фиксированный шаг; оно не доказывает инвариантность выбора splits и полного обучения.

Learning rate, leaf estimation и инициализацию следует фиксировать явно. Автоматический learning rate зависит от objective и того, заданы ли параметры оценки листьев/L2. `boost_from_average` поддерживает Logloss и ряд других objectives, но PairLogit в списке отсутствует. Для BCE постоянный общий k не меняет weighted prevalence и оптимальный начальный constant logit; toy использовал `False`. Это не разрешает менять уже frozen настройки. [Общие параметры CatBoost](https://catboost.ai/docs/en/references/training-parameters/common).

## Синтетическое свидетельство и сохранённая ошибка

План предусматривал максимум четыре tiny fits, фактически **израсходованы три**: BCE k=1, BCE k=16, затем PairLogit k=1. После третьего fit скрипт завершился `TypeError`: у `CatBoostRanker.predict()` нет аргумента `prediction_type`. PairLogit-модель не была сериализована; четвёртый fit не запускался. Повторного обучения нет. Корректная сигнатура подтверждена [официальным API](https://catboost.ai/docs/en/concepts/python-reference_catboostranker_predict). Нельзя записать «4 passed» или эмпирическое сравнение PairLogit.

BCE toy: 15 искусственных строк, два числовых признака, размеры четырёх query 2/4/6/3; последняя группа полностью отрицательная. Pair toy использовал первые 12 строк, три informative query и 12 explicit pairs, с массами query 1/1/1. Общие настройки: три дерева, depth=2, learning_rate=.1, L2=3, CPU threads=2, seed=2026, Plain, bootstrap=No, random_strength=0, score_function=L2, Newton, одна leaf iteration, backtracking=No, без eval set и best-model selection. Это изоляция механизма, не подобранная конфигурация.

Две сохранённые BCE JSON-модели имеют одинаковые splits, leaf values и scale/bias. Read-only восстановление предсказаний из float-tree JSON дало максимальную абсолютную разницу 0.0. Ручной normalized BCE на фиксированных predictions для k=1/16 одинаков: 0.6561308353962578. Это согласуется с объяснением L2, но не доказывает универсальную инвариантность всех режимов CatBoost.

Audit сохранён в [archived failed-check source](round-007-check-source.md) и [partial result](round-007-partial-result.json); два model JSON остаются временными производными артефактами. После каждого из трёх fits прошли проверки elapsed<60 секунд и peak RSS<300,000,000 байт; установлен CPU hard limit 55 секунд и thread_count=2. Финальные точные RSS/CPU counters при исключении не экспортировались, поэтому точные значения не заявляются. Последующая ошибка read-only JSON-parser исправлена без fits и отражена в audit.

## Следствие для task1

До будущего freeze полезно зафиксировать раздельно: objective, формулу веса, число всех/ informative queries, N объектов/пар, сумму object weights, сумму pair weights, λ, learning rate, bias и effective leaf parameters. В BCE `W/N=|QB|/N`, тогда как для рассматриваемого PairLogit без object weights `W/N=1`; одинаковая цифра λ не означает одинаковой силы регуляризации между objectives.

Предлагается сохранить query-mass policy и учитывать её при заранее объявленной objective-specific сетке L2. Нельзя добавлять global weight scale как бесплатную новую ось поиска: при необходимости соответствующий вариант заменяет точку внутри будущего согласованного бюджета. Prospective strong tuning 4 fits×3 checkpoints остаётся предложением, а frozen 008 не меняется. Нового механизма качества и новых labels здесь нет; это уточнение существующих loss notes. HYP099/100 остаются зарезервированными без выдуманной новизны.


## Coordinator critic amendment — 15 октября 2026

[Independentcritic004–008](round-004-008-review.md) подтвердилsourceL2chain иread-only2BCEmodel equality, ноисправляет API attribution: current [officialpredictpage](https://catboost.ai/docs/en/concepts/python-reference_catboostranker_predict) показывает generic prediction_type и расходится с [taggedv1.2.10Ranker source](https://github.com/catboost/catboost/blob/v1.2.10/catboost/python-package/catboost/core.py#L6038-L6065)/installedsignature. Именноversionedcode+actualTypeError подтверждают отсутствиеэтогоаргументависпользованнойверсии; фраза вышеoprovedofficialAPI считаетсяисправленной.

Toyfitparams threads2неограничивалиPool/predictdefaults−1. All-stage2corecapдляround007недоказан; after-fitelapsed/RSSchecks иCPUhardlimit55остаютсясвоимиеvidence, точныесчётчикиunknown. [Archive](round-007-check-source.md) сохраняетdefect иlimitations, бесплатныхretries нет. Принятый008отдельнопроверилявные2threadsвобоихPool/predict. Этоdocumentamendment, неновыйfit/codechange.


Два savedtoyJSON, originalfailedcheck иpartialresult дополнительноскопированыбезперезапускавignoredprojectartifacts/research-lab/round-007. [Artifactmanifest](round-007-evidence-manifest.json) сохраняетactualSHA/size;derivedmodelsнепубликуютсявGit. Этоpreservationсуществующихтрёхизрасходованныхfits, нетновогоcompute/approval.
