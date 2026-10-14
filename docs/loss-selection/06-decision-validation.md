# L06. Совместный выбор модели, loss и правила валидации

15 октября 2026. Независимая записка; новые записки коллег не читались. Исследование, без обучения, установки пакетов или чтения confirmation. Рабочий development-протокол отличается от окончательного утверждения цели.

## Что уже действительно доступно

Приняты manual18, fixed C: до200 past-popular+20 recent-distinct, эвристики и evaluator006 с полным Y. CatBoost1.2.10 CPU установлен и прошёл synthetic API-check; реальных fits нет. Runtime017 train/selection ещё проходит review, новой принятой обучающей коллекции нет. Эти факты следуют из [CPU environment](../experiments/cpu-environment.md), [development collection](../experiments/development-collection.md) и [backlog](../backlog.md), а не из предположения о готовности модели.

Единица: q=(user,t), товары C(q), бинарный y=1[i∈Y(q)], где Y — distinct purchases в [t,t+24h). История строго<t; label в секунду t допустим после прогноза. Рабочий вариант использует daily00UTC и past-eligibility48h. C не дополняется будущими positives. Отдельно сохраняются p=|Y∩C|, n=|C|−p и targets вне C. Query с непустым Y может иметь p=0.

## Матрица решений

| Приоритет и модель | Loss и вход | Что сравнение выясняет |
|---|---|---|
| P0 CatBoostClassifier | BCE; строки(q,i), все зрелые queries с непустым C | Ранжирование, обученное также на queries без candidate-positive |
| P0 CatBoostRanker | PairLogit; явные пары positive–negative внутри q | Пользу относительных предпочтений на informative groups |
| P1 тот же CatBoost | YetiRank mode=NDCG, top20; группы C | Отдельную проверку согласования surrogate с cutoff после P0 |
| P1 один альтернативный booster | LightGBM lambdarank **либо** XGBoost rank:ndcg | Смену реализации/семейства, без полного декартова поиска |
| P2 одна компактная neural-ветвь | MLP+BCE либо two-tower/small sequence+sampled softmax | Пользу представления; затем frozen scalar features→выбранный CatBoost |

Матрица — очередь, не разрешение запускать все клетки. Официальные реализации различаются: [CatBoost](https://catboost.ai/docs/en/concepts/loss-functions-ranking), [LightGBM](https://lightgbm.readthedocs.io/en/stable/Parameters.html), [XGBoost](https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html). YetiRank non-Classic поддержан на CPU; его auto-pairs/weights нельзя объявлять идентичными explicit PairLogit. Для neural softmax заранее определить target-set, negative proposal и коррекцию sampling; название loss не делает перенос на purchase ranking доказанным.

Для BCE вес каждой строки1/|C|: масса query=1. C=∅ не создаёт обучающих строк, но остаётся evaluation miss; такие queries считать отдельно. Для PairLogit брать все p×n пары с весом1/(pn), только при p>0,n>0; group weight=1. Получается масса1 на informative group. CatBoost игнорирует object weights для PairLogit и использует pair weights — это требует отдельной проверки API, а не переноса BCE-весов ([документация](https://catboost.ai/docs/en/concepts/loss-functions-ranking)).

Следовательно, P0 сравнивает **loss вместе с population policy**. Нельзя приписать разность одной математической форме. BCE на тех же informative groups — полезный support-control, но отдельный третий fit; он требует пересмотра бюджета или замены одной запланированной конфигурации, а не молчаливого добавления.

## Выбор checkpoint должен использовать полный Y

Основной selection-критерий предлагаю conditional macro-query NDCG@20 внешнего006; дополнительно Recall@20, all-query zero-convention, user-macro, p(nonempty), repeat/new и day slices. Native NDCG по labels только внутри C имеет иной IDCG при пропущенных targets. Поэтому native best_model/early stopping не должен окончательно выбирать checkpoint. До fit фиксируются редкие контрольные iterations; реальные predictions каждого checkpoint проходят006 по одинаковым Q/C/fullY и caller tie-break. Сохраняются hashes выбранных деревьев и evaluator inputs. Это часть selection search и стоимости, а не бесплатная проверка после выбора.

Падение training BCE/PairLogit не заменяет рост NDCG. Метрики на randomly sampled negatives также не заменяют принятую candidate-policy: [Krichene–Rendle](https://research.google/pubs/on-sampled-metrics-for-item-recommendation/) показывают возможность изменения сравнительного порядка методов при sampled evaluation. Наш fixed shortlist — явно оцениваемый pipeline с full-Y misses, без обещания exact full-catalog ranking.

## Время, калибровка и остановка

Текущие configs: selection22–23октября, labels доступны24октября00:00; первый confirmation-query тоже24октября00:00. **Положительного времени на scoring, выбор и lock нет.** Prospective исправление: confirmation только25октября, labels зрелы26октября; либо selection только22октября, labels доступны23октября, confirmation24–25. Выбор меняет support и precision, требует новой версии плана. Проверять selection_labels_available≤decision_started<decision_completed≤frozen_before≤first_confirmation и фактические artifacts. Confirmation до исправления остаётся закрыта; равенство timestamp не доказывает выполнимость решения.

Frozen модели обучаются до downstream anchors; обновляемые histories отделены от параметров. Learned priors/encoders требуют warmup-fit или forward snapshots. Crossfit только вперёд по времени; shuffled folds не исправляют temporal leakage. Несогласованные embedding coordinates разных checkpoints нельзя склеивать как одни признаки.

BCE score не объявляется вероятностью реакции на рекомендацию: impressions отсутствуют. Калибровка имеет смысл лишь для наблюдаемой покупки в данном горизонте, population и candidate-policy; class weighting/negative sampling меняют её интерпретацию. Если понадобятся probability thresholds, нужен отдельный временной calibration segment, не confirmation. [Guo et al.](https://proceedings.mlr.press/v70/guo17a.html) обосновывают калибровку отдельно от discrimination, но не гарантируют переносимость между нашими периодами.

Общий действующий потолок —6CPU-часов на pilots/fits, не6часов на каждое исследование. TLAB008: ≤2fit-конфигурации, CPU2threads, smoke/первыйfit≤60минут; предлагаю такой же верхний wall-cap второму, только внутри фактического остатка ledger. Подготовка, predictions, checkpoint-selection, bootstrap и failures оплачиваются; CPU/wall учитывать раздельно. Нельзя обещать остаток до cost reconciliation017. Верхняя арифметика train:5,72млн строк;18float32≈412MB только values, без Pool/state. All-pairs может достигнуть314,6млн пар: превышение ресурса означает остановку и новый заранее описанный sampling-plan.

До запуска фиксировать recall-guard−0,002 и proposed paired95%CI(ΔNDCG)>0; uncertain interval означает inconclusive. Такой CI на selection не устраняет [selection bias](https://jmlr.org/papers/v11/cawley10a.html), поэтому promotion требует один frozen confirmation. Неинформативные группы, budget exhaustion, lineage mismatch или незрелые labels останавливают соответствующий run. Два smoke-fits ещё не доказывают strong baseline; дальнейший tuning требует измеренного расширения. До окончательного target/horizon/estimand нельзя утверждать победивший loss. Новых HYP не требуется: это контроль валидности, а не самостоятельная исследовательская новизна.
