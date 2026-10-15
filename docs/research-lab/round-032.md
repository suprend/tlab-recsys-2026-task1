# Research lab, round032: что означает отрицательный whole-metadata результат009

15 октября2026. Интерпретация опирается **только на опубликованные** [independent audit009](../backlog-reviews/tlab009-model-output-verification.md) и [aggregate evidence](../backlog-reviews/tlab009-model-output-aggregate.json), плюс первичные методические источники. Запрошенное имя `tlab009-model-output-verification.aggregate.json` отсутствует; использован aggregate, явно связанный из audit. Ignored data/models, scores и source не читались, вычисления метрик/replicates/fits не повторялись. Новые budget, looks, slices, refits или rescue experiments не предлагаются.

## Измеренный результат и точное решение

Одно разрешённое009 обучение CPU Logloss50 добавило18 входов к base41: итог56numeric+3nominal, то есть15numeric и3categorical additions. Training population:6000Q,1227213candidate rows,114fullY-positiveQ,92informative C-groups,101retrieved-positive rows; ожидаемая query-normalized rowmass6000. Это не1.2m независимых положительных наблюдений и не114positive candidate groups. Selection:4000Q,817149pairs,96fullYtargets в73positiveQ.

| Fixed development comparison | Conditional full-Y NDCG@20 | Recall@20 |
|---|---:|---:|
| Existing008/base41 |.41444755081727774|.5812133072407045|
| ONE009/base41+metadata18 |.40041404048762785|.5450097847358121|

По опубликованной проверке population/settings/control сохранены, old008scores воспроизведены независимо,009saved model воспроизводит все selection raw scores. Whole-block ΔNDCG=−.01403351032964989. Заранее закреплённая retention policy требовала **одновременно** NDCG>base+1e−12 и Recall≥.5792133072407045 после source/resource/model gates. Оба quality условия не выполнены: корректное решение — REJECT блока и base41 дальше. Для такого screening rejection не требовалось доказать статистически значимый отрицательный эффект.

Это положительный результат аудита исполнения и отрицательный результат одной ограниченной гипотезы. Неизменённые настройки обеспечивают сравнение при фиксированном learner, но не доказывают, что расширенному представлению предоставлены оптимальные hyperparameters. Аналогично этот Logloss50 smoke не становится strong tuned B только благодаря приёмке artifacts.

## Что one-hot/model evidence действительно говорит

При protocol `one_hot_max_size=4096` TRAINencoded cardinalities501/categoryID,120/code,1265/brand проходят cap. [CatBoost common parameters](https://catboost.ai/docs/en/references/training-parameters/common) определяют one-hot для cardinality≤threshold и отсутствие CTR для таких признаков. SavedJSON содержит45`OneHotFeature` и255`FloatFeature` split occurrences,0CTR. Это подтверждает использование categorical equality tests в конкретной модели;45 — не число nominal inputs,255 — не `border_count` и не255 уникальных numeric features. Repeated splits не измеряют независимую информацию или вклад в Δranking.

[Quantization documentation](https://catboost.ai/docs/en/concepts/quantization) описывает разбиение numeric values на buckets с thresholds. Следовательно15новыхnumeric входов дают дополнительные split candidates после quantization; missing/support flags тоже могут участвовать как numeric. Из двух опубликованных файлов нельзя установить, какие именно price/context/missingness признаки получили255float splits, распределение поддержки каждого border или их отдельную полезность. Не следует подменять эту неизвестность рассказом «price доминировал».

[CatBoost paper2018](https://proceedings.neurips.cc/paper/2018/file/14491b756b3a51daac41c24863285549-Paper.pdf) объясняет ordered boosting и target-statistic leakage, но0090CTR не тестирует преимущества target encoding. CatBoost library name не означает, что именно ordered categorical statistics использованы здесь. Paper не обещает, что добавление корректных categorical features монотонно улучшает held-out ranking, и не заменяет наш temporal source contract.

## Механизмы как гипотезы, с конкурирующими объяснениями

| Возможное объяснение, не установленная причина | Counterhypothesis и отсутствующее различающее evidence |
|---|---|
| Новые category/brand equality tests разделяют слабо поддержанные positive patterns и хуже переносятся между датами | Они могут быть полезны; observed drop может происходить из numeric additions или ограниченной реализации взаимодействий. Нет family-specific controlled evidence/support attribution |
| Новые numeric thresholds изменили greedy allocation ограниченных50trees, вытеснив полезные B splits | Metadata может давать хорошую информацию, а конкретная optimization path — неудачную. Нет paired path/capacity attribution;45/255 counts этого не решают |
| Фиксированная regularization недостаточна для расширенного representation при sparse labels | Regularization могла быть достаточной; drop возможен от ограниченного support/date realization. Нет разрешённого tuning comparison для этого блока |
| Новый сигнал слаб или redundant с B на данном Q/C/fullY | Полезные и вредные additions могли компенсироваться; wholeblock не отделяет отсутствие signal от отрицательных interactions |

Эти механизмы согласуются с устройством learner, а не выведены из результата. [Greedy tree construction](https://catboost.ai/docs/en/concepts/algorithm-main-stages_choose-tree-structure) выбирает feature/split pairs из общего набора candidates. Поэтому даже одна добавленная колонка может изменить дальнейший ensemble; фиксированный seed не гарантирует прежнюю последовательность splits после изменения inputs. В официальных [training parameters](https://catboost.ai/docs/en/references/training-parameters/common) L2 задаёт regularization term, random_strength — randomness split scoring. Их наличие не доказывает достаточную защиту от переобучения, а неизменность не доказывает причинный механизм ухудшения. Названное отсутствующее evidence — граница знания, **не запрос сейчас его измерять**.

## Неопределённость и границы source proof

Опубликованный paired-user bootstrap:3995mature users,200shared-multiplicity draws, undefined0;95%percentile interval ΔNDCG=[−.06338086509402815,.04292473944032154]. Он пересекает0: это не equivalence и не non-inferiority proof. Для equivalence нужен заранее определённый допустимый интервал и соответствующее доказательство внутри него; для данного rejection использовалось другое, point-metric правило. Интервал условен на observed dates/fittedmodels/cohort и development history, не описывает новые дни, retraining seeds или confirmatory effect. Малое число positiveQ не исправляется количеством candidate rows.

Три уровня доказательств нельзя смешивать.018 обеспечивает exhaustive Q/Y/C и F-rowset, но original manual18 **numeric source formulas sampled**, не exhaustive allB proof.009accepted addon source отдельно проверил все110mдобавочных значений; опубликованный model oracle затем независимо собрал56float32+3UTF8 arrays из принятых Parquet и replayed raw scores. Он не повторяет все source formulas. Фактически переданные training weights не восстанавливаются из CBM: audit связывает expected population/mass с reviewed fit code/report. Resource receipt producer101.181955CPU seconds плюс оба observer attempts7.921392; initial failed observer сохранён, бесплатного refit нет.

## Следствие для016 и корректная формулировка отчёта

019/016 наследуют base41 по установленной policy. Общий016 B должен быть один и тот же выбранный eligible incumbent/settings/population для всех frozen arms; metadata не возвращается posthoc как скрытый альтернативный контроль. Нельзя после неудачи удалить «плохую» subfamily, поменять cap/encoding, заменить random arm или потребовать новый seed. Bounded typedAST pool может дать полезный либо отрицательный результат:009 не доказывает превосходство counts над metadata и не оправдывает механизм заранее.

Допустимый claim: «На фиксированном development Q/C/fullY и unchanged Logloss50 learner whole metadata18 block не прошёл prospective retention rule; execution/source/model evidence принято, блок отклонён». Недопустимы «price/category универсально вредны», causal recommendation lift, online conversion effect или подтверждённая generalization. Correct calculation и принятие model artifacts делают отрицательное свидетельство воспроизводимым; они не превращают его в установленную причину или разрешение дальнейшего поиска.
