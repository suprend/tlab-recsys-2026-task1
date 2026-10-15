# Round053 — OpenFE: путь labels, бюджет и граница воспроизведения016

**Углублённый source audit одной измеренной AutoFE работы.** Прочитаны ICML2023 paper, официальный package source и отдельно связанный авторами reproduction repository. Ни datasets, ни models, ни executable examples не запускались. Дополняет047 конкретным code trace, а не новой HYP. Наши accepted symbolic interfaces прочитаны отдельно; WIP019/016 execution и outcomes не инспектировались.

## Версия — часть результата

[Официальный OpenFE README](https://github.com/IIIS-Li-Group/OpenFE) явно направляет воспроизводить paper через [OpenFE_reproduce](https://github.com/ZhangTP1996/OpenFE_reproduce), предупреждая, что его код отличается от актуального package. Поэтому `pip install openfe` не является спецификацией опубликованного эксперимента. Здесь наблюдались public `master`15Oct2026; commit API не вернул доступный ответ, immutable SHA не установлен. Ссылки ниже — проверенные места, но не заявление о полном historical checkout.

## Что измерено и как устроен метод

[Paper, §2–3,5,7,AppendixD](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) задаёт expand-and-reduce: enumerate transformations, FeatureBoost, successive pruning, joint feature attribution. FeatureBoost обучает добавочную функцию g поверх base predictions: `Σℓ(yᵢ,ŷᵢ+g(xᵢ))`; значит, это supervised fitting, а не дешёвый label-free score. На десяти tabular benchmarks используется один общий train/validation/test split, LightGBM tuning на base features и10 repetitions; обычно добавляются10features. Например, California RMSE Base.432±.004→OpenFE.421±.002. Это конкретное измерение, не наш ranking contrast. Feature generation использует40-core Xeon/512GB, tuning/training —V100. Работа прямо признаёт отсутствие past-only time-series constraint. AppendixD.3 указывает1000estimators для successive pruning; наблюдённый код ниже содержит100. Это unresolved version/spec difference, не доказательство того, какой snapshot авторы фактически исполняли.

## Code trace reproduction: labels не только в final model

В [runs/FE_first_order.py](https://github.com/ZhangTP1996/OpenFE_reproduce/blob/master/runs/FE_first_order.py) train и validation X объединяются, labels тоже объединяются; исходные train/val indices передаются отдельно. Test X/Y загружаются интерфейсом, но test Y в `ofe.fit` не передаётся. Regression normalization использует train-only mean/std. Это свидетельства конкретного access path, не гарантия строгого temporal применения каждого feature.

[Reproduction OpenFE.py](https://github.com/ZhangTP1996/OpenFE_reproduce/blob/master/OpenFE.py) при `init_scores=None` строит5-fold OOF base predictions посредством LightGBM, maximum10000estimators/early-stop200. Folds идут по переданному data/label, включая его validation portion; это не training-only proposer относительно этого внутреннего split. StageI обучает candidate-specific models:100estimators,16leaves, early-stop3 по validation. Затем StageII обучает совместную модель с maximum1000/early-stop50, ранжируя features по importance. Transform method объединяет train/test **X**, рассчитывает features и разделяет обратно; test labels в этом method не используются.

Следствие для нас: «нет test labels» и «features рассчитаны из данных, известных перед каждым historical query» — разные свойства. OOF prediction исключает собственную label из обучающих folds, но не исключает later-user rows или более поздние labels других queries. Даже правильно переданные chronological train/val indices сами по себе не делают обычные5folds causal. Это сравнение contracts, не обвинение в нарушении tabular задачи статьи.

## Текущий package: ещё один distinct algorithm path

В [openfe/openfe.py](https://github.com/IIIS-Li-Group/OpenFE/blob/master/openfe/openfe.py) `feature_boosting=False` по умолчанию; тогда initial scores строятся из label mean/proportions. При включении появляется5-fold base fitting. Default split — random80/20, если indices не заданы. `_subsample` shuffle/doubling расширяет train/val subsets, StageI рассчитывает features на их объединении и оценивает по val labels. `delete_same` удаляет соседние features с evaluation-score difference<1e−20: это score heuristic, не доказательство равенства AST/values. Когда положительных StageI результатов нет, package оставляет top100 — policy, которую016 не воспроизводит.

В reuse path workers читают union необходимых source columns из Feather, группируют candidate jobs, но вычисляют каждый candidate отдельно и удаляют промежуточные feature data. Это column/I/O sharing, не generic relational aggregate-plan sharing или доказанный DAG reuse. `transform` также документирует совместное преобразование train/test X из-за global operators. Package и paper reproduction поэтому нельзя смешивать в один якобы неизменный execution recipe.

[FeatureGenerator.py](https://github.com/IIIS-Li-Group/OpenFE/blob/master/openfe/FeatureGenerator.py) выполняет `Freq`/GroupBy по переданному dataframe, без per-row cutoff. `Log` реализован как log(abs(x)) с0→NaN, `Round` —floor; названия сами не задают нашу mathematical semantics. Literal пример именно этого snapshot contract: две строки одного entity с величинами10 доT и30 послеT дадут общий mean20; strict-past query перед второй строкой должен видеть только10. Это conceptual counterexample, не выполненный тест и не новый legal005 mean operator.

## Search/training cost и measured comparison

Для одного этапа supervised selection нельзя считать расходы равными одному final fit. Если Nj — число оцениваемых candidates на halving round j, structural count включает base OOF fits при соответствующем режиме, `ΣNj` StageI fits и joint StageII fit; early stopping меняет trees, не отменяет attempts. Repeated feature orders добавляют этапы. Полный source-read/serialization/failed-worker/oracle cost из этих counts не восстанавливается и остаётся unknown без ledger.

[Reproduction eval.py](https://github.com/ZhangTP1996/OpenFE_reproduce/blob/master/runs/eval.py) отдельно проходит seeds0…9, копируя base tuned configuration для расширенного dataset и запуская downstream model executable. Значит,10repetitions — не10разных splits и не весь feature-search budget. [California shell recipe](https://github.com/ZhangTP1996/OpenFE_reproduce/blob/master/runs/shell_inst/california_housing.sh) фиксирует fold1,10saved features и StageII reserve100 перед tuned downstream evaluation. Этот concrete recipe полезнее headline «четыре строки Python» для понимания, что действительно воспроизводится.

## Что наша реализация воспроизводит концептуально

| Шаг | Accepted symbolic016/005 | Чего из OpenFE здесь нет |
|---|---|---|
| Generation | Schema roles + human bounded templates→typed definitions | Автономного смысла полей, широкого arithmetic/global transform catalogue |
| Reduction | Exact semantic alias rejection против B/retrieval, physical closure | Label-score dedup, FeatureBoost, halving/importance fits |
| Allocation | Два фиксированных I и два seeded R draws | Learned feature ranking или adaptive candidate refill |
| Calculation | Existing005 strict-past grains/windows/raw bag | Объединённого snapshot GroupBy как temporal гарантии |
| Quality | Отдельный frozen matched full-Y ranking protocol | Reproduction tabular RMSE/AUC результатов OpenFE |

Основание текущего столбца — [public symbolic module](../../scripts/feature_programs.py) и [accepted design](../experiments/feature-programs.md): три functions создают definitions/allocation/registry, не читают data/labels и не запускают fits. Selected12 source proof и четыре matched arms требуют собственного evidence, не выводимого из чужой статьи; их actual результаты здесь не инспектировались.

Практический вывод для final report: допустимо назвать expand-and-reduce conceptual inspiration и явно перечислить наши ограничения. Нельзя приписывать016 FeatureBoost, cost superiority над OpenFE, expert-level discovery или label-blind human design. Если когда-либо обсуждать OpenFE branch, до его budget решения нужны immutable reproduction revision, точный init-score/OOF/transform population contract и ledger всех selector fits/validation looks. Сейчас такой branch не предлагается к исполнению: нынешние12columns/4fits неизменны; отрицательный016 не опровергнет OpenFE, положительный не воспроизведёт его полный алгоритм.
