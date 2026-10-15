# Round065 — CatBoost Plain/Logloss: importance не равна ranking gain

**Primary-source report refinement, 15 октября2026.** Сначала проверены M01 и rounds016/032/059/060: Ordered-versus-temporal и fixed-learner boundaries уже разобраны. Новое узкое уточнение — **какую importance фактически означает default API у Logloss модели, используемой для ranking**. Читались paper2018, текущие official docs и tagged v1.2.10 source; API, модели, метрики, actual016 outputs/WIP и heldout не запускались/не открывались. Это не новая HYP, задача или разрешение observer recovery/regeneration.

## Что paper действительно обещает

[Prokhorenkova et al., NeurIPS2018, §§2–4](https://proceedings.neurips.cc/paper_files/paper/2018/file/14491b756b3a51daac41c24863285549-Paper.pdf) разделяют categorical target statistics и ordered boosting. Первый механизм преобразует категорию с помощью labels предшествующих примеров в permutation; второй борется с prediction shift от использования training targets в последовательном boosting. Формальная постановка начинается с i.i.d. examples и независимого test example. Это не theorem о задержке появления событий, зрелости24h targets или глобальном исключении timestamp peers.

Текущие [common parameters](https://catboost.ai/docs/en/references/training-parameters/common) называют Plain классическим boosting, Ordered — альтернативой; `has_time` сохраняет input object order на названных стадиях вместо permutations. Отсюда не следует, что timestamps всех candidate rows одного query атомарны, labels учитывают availability_delay или `<t` применён ко всем source joins. Plain с заранее корректными historical features не нарушает protocol лишь из-за своего имени; Ordered с future-filled count тоже не делает строку корректной.

У нашего принятого numeric/bool B41 нет native categorical input, поэтому categorical ordered TS/CTR нельзя перечислять как использованный механизм контроля. Numeric category-derived share остаётся numeric aggregate, а nominal IDs в key columns — не categorical model inputs. Наличие CatBoost в dependency list не доказывает использование всех его paper advances.

Также ordinary supervised fit использует зрелые targets training queries, находящиеся после собственных anchors; это не противоречит `<anchor` для **исходных numeric features**. Модель применяется после её simulated availability. AST/model learning и strict-past row calculation — разные clocks/contracts; физический audit2026 не backdate модель в2019. Эти положения — дедуп уже принятых lifecycle notes, не новый chronology gate.

## Конкретное новое source distinction

[Official get_feature_importance docs](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_get_feature_importance) описывают automatic FeatureImportance как PredictionValuesChange для non-ranking и LossFunctionChange для ranking. Важно уточнить, что именно библиотека считает ranking в этом dispatch.

В [tagged v1.2.10 core.py](https://github.com/catboost/catboost/blob/v1.2.10/catboost/python-package/catboost/core.py), `get_feature_importance`, строки3215–3220 raw source, читается **stored loss function name**, затем вызывается `is_groupwise_metric(loss)`. При true выбирается LossFunctionChange, иначе PredictionValuesChange. `feature_importances_` аналогично смотрит stored loss. Внешний006 evaluator и человеческое описание «recommendation ranking» в этот выбор не входят. Это статически прочитанный dispatch, не вызов API на нашем CBM.

Следовательно, для объявленного Plain/Logloss B default type — **PredictionValuesChange**, даже если лучшая модель выбрана по fullY conditional NDCG. Нельзя подписать такую таблицу «вклад каждого признака в NDCG» или считать её fullY feature ablation. Native `eval_metric` тоже не заменяет этот конкретный stored-loss dispatch.

Первоначальные direct docs URLs местами вернули Internal Error. Определения ниже проверены по [official tagged docs/fstr.md v1.2.10](https://github.com/catboost/catboost/blob/v1.2.10/catboost/docs/en/concepts/fstr.md); текущий indexed official API text использован отдельно. Tagged implementation, paper2018 и mutable current documentation не выдаются за один неизменный historical эксперимент.

## Importance types отвечают на другие вопросы

PredictionValuesChange описывает изменение prediction values через leaf comparisons/weights, имеет неотрицательные normalized values, суммирующиеся до100. Это не знак внешнего metric effect и не вероятность causal relevance. Leaf weights не восстанавливают полный train population/индивидуальные training weights из CBM; прежний019 proof limit остаётся.

LossFunctionChange требует dataset, dataset-dependent и приблизительно удаляет feature из существующих деревьев вместо настоящего refit. Значение может быть отрицательным; tagged docs определяют используемый metric через training loss. Поэтому даже явный вызов этого type на Logloss-модели не становится paired fullY NDCG абляцией. Для больших datasets документация API допускает subsample. Нельзя превратить название «loss change» в exhaustive source/quality proof.

SHAP values, согласно API, разлагают конкретный prediction относительно expected value. Объяснение RawFormulaVal отдельной scored row не доказывает recall targets внеC, стабильность выбора W или эффект полного нового learning recipe. Данное чтение не предлагает рассчитывать SHAP/importance: это новые cost/data-access операции, даже без fit.

## Литеральный ranking counterexample

Пусть scorer имеет вид `s(q,i)=h(i)+g(q)`. Для двух items значения h равны0 и1; у queryA g=0, у queryB g=100. Scores соответственно(0,1) и(100,101). Query-level ranking одинаков при удалении g, следовательно, при тех же fullY все четыре accepted ranking metrics остаются теми же. Однако модельный компонент g меняет prediction values, может иметь значительную PredictionValuesChange и менять Logloss/calibration. Это аналитический counterexample, не измеренная importance нашего B.

Обратное упрощение тоже неверно: query-constant input способен взаимодействовать с item features в деревьях и менять внутриquery order. Поэтому пример запрещает inference «высокая importance ⇒ ranking gain», но **не** разрешает prune все user-only features как бесполезные. Correlated aliases могут перераспределить importance между columns без эквивалентного перераспределения информации. Semantic dedup005/016 имеет собственное точное основание; metric/importance clustering не подменяет его.

## Минимальная поправка к report

Допустимо: «Использован CatBoost с numeric/bool historical features, Plain и Logloss; temporal correctness обеспечивается source/feature/availability contract. Качество добавлений оценено отдельным matched fullY ranking protocol при frozen learner settings» — последнее предложение только после actual acceptance соответствующего сравнения.

Если когда-либо публикуется importance, нужны model/prefix, exact type/version, dataset/reference/subsample/weights context и единица объяснения. Подпись должна говорить о prediction attribution или approximate native-loss change, а не о causal recommendation benefit. Для текущего report importance необязательна: accepted predictions/metrics/source proof достаточно релевантнее task1 claim. **No new HYP/task/experiment:** сохранить один source-backed wording distinction; не расширять бюджет и не задерживать существующие proof/reproduction работы.
