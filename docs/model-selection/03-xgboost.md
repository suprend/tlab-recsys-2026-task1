# M03 — XGBoost: дополнительный контроль, а не третий обязательный бустинг

Дата: 15 октября 2026. Независимое исследование; обучение, установка пакетов и изменение репозитория не выполнялись. Проверены официальные stable-документы, отображавшиеся как 3.4.2; это не утверждение о версии локального окружения. Новые записки коллег не читались.

## Решение и контекст

**Рекомендация: P1 optional.** Сначала нужен сильный настроенный ручной CatBoost-контроль и проверенный общий evaluator. Добавлять XGBoost стоит при конкретном вопросе: сохраняется ли эффект автоматизированных признаков при другой реализации деревьев либо даёт ли альтернативный ranker лучшее качество за тот же бюджет? Само сравнение трёх библиотек не доказывает пользу автоматизации. Первые ≤2 fits TLAB-008 — smoke, не хорошо настроенный финальный контроль; task1 требует доказательства автоматизации признаков либо превосходства над настроенным boosting по подтверждённой постановке задания. Основание: существующие `docs/experiment-plan.md`, `docs/backlog.md`, раздел Reservation gate.

## Подтверждённые возможности

Единица строки — `(query=(user,t), candidate item)`. Входы: одинаковые ручные strict-past агрегаты пользователя, товара и пары, as-of metadata, источник/ранг кандидата. Score — сумма выходов деревьев `s(q,i)=Σ_m f_m(x_qi)`, используется для сортировки внутри запроса, не объявляется вероятностью покупки. Системная исходная работа описывает регуляризованный tree boosting и инженерные методы масштабирования, а не гарантированное превосходство на REES46. [Chen–Guestrin, 2016](https://arxiv.org/abs/1603.02754).

`XGBRanker` поддерживает `rank:ndcg` — LambdaMART с NDCG-взвешиванием парных градиентов; `rank:map` предназначен для бинарной relevance; `rank:pairwise` использует RankNet logistic loss без metric scaling. Поэтому это разные цели, а не три названия одного loss. Для бинарных покупок предлагается начать с `rank:ndcg`; MAP-ветвь имеет смысл при выбранной AP/MAP-метрике. Исходный RankNet был нейросетевым методом; здесь используется его парная функция потерь в бустинге. [LTR tutorial](https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html), [Burges et al., 2005](https://www.microsoft.com/en-us/research/publication/learning-to-rank-using-gradient-descent/).

`qid` должен задавать отсортированные группы; `group` — их размеры. `sample_weight` и `sample_weight_eval_set` у ranker относятся к запросам, не строкам: ими нельзя напрямую реализовать произвольную индивидуальную importance correction для sampled negatives. При нескольких validation-наборах/метриках стандартная early stopping использует последние; sklearn prediction учитывает `best_iteration`. Callable-метрика по умолчанию минимизируется, поэтому направление оптимизации требуется задать явно. [Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html#xgboost.XGBRanker).

Native categorical splits доступны через `enable_categorical`, dataframe categorical dtype и `hist`/`approx`; есть partition и one-hot стратегии. Это не CatBoost ordered target statistics. Python auto-recoding появился в 3.1, но не решает семантику новых невиданных категорий. Нужны frozen словарь/unknown policy, одинаковая типизация и JSON/UBJSON serialization. Numeric user/item/category ID не становятся порядковой величиной; миллионные user-ID лучше исключить из первого контроля, оценив metadata и поведенческие агрегаты. [Categorical documentation](https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html).

## Обязательные проверки смысла

Зафиксировать общие Q, полный Y, C, горизонт, maturity, temporal split и features. `y_qi=1[i∈Y_q]` предлагается для distinct purchase-set; отсутствие impressions не позволяет назвать остальные товары доказанными неприязнями. Позитивы из будущего не вставляются в C. Targets вне C остаются промахами; Recall/AP/IDCG считаются по полному Y. Freeze обученных priors/encoders должен предшествовать downstream predictions; одного `history<t` недостаточно.

Native `ndcg@K`/`map@K` дают 1 группе без позитивов; суффикс `-` меняет её вклад на 0. Это не выбор общей политики evaluation. Даже `ndcg@K-` считает IDCG по переданным candidate labels и может расходиться с full-Y evaluator при неполном покрытии. `topk` строит приблизительно K×|C| пар, `mean` ограничивает sampling; равные labels пропускаются. [Parameters](https://xgboost.readthedocs.io/en/stable/parameter.html). CPU-код обнуляет градиенты группы и пропускает равные labels: all-zero/all-positive/singleton не дают различающего парного сигнала. [Objective source, master](https://github.com/dmlc/xgboost/blob/master/src/objective/lambdarank_obj.cc).

До fits нужны golden cases: пустой Y; Y непустой, но целиком вне C; частичное покрытие нескольких покупок; singleton/all-positive; равные scores, неравные query weights и OOV. Native-метрика остаётся диагностикой, пока её denominators/ties/weights не сверены. Для выбора checkpoint предлагается callback с общим full-Y evaluator на selection; confirmation/test закрыты. Это предотвращает раннюю остановку по другой целевой величине.

## Ресурсы и ограниченный опыт

Windows x86_64 wheels поддерживают NVIDIA GPU; Apple Silicon wheels — CPU. Windows требует Visual C++ runtime. GPU `hist` включается `device=cuda`; документация сейчас требует CUDA≥12.9. Фактические driver/build/VRAM RTX3070 здесь не проверены. [Installation](https://xgboost.readthedocs.io/en/stable/install.html), [GPU guide](https://xgboost.readthedocs.io/en/stable/gpu/index.html).

External memory через iterator/`ExtMemQuantileDMatrix` существует, однако GPU async-pool путь документирован без Windows support; акцент — NVLink-C2C, а GPU disk-cache может оказаться медленнее CPU. Это не обещание спасения Windows/3070 от OOM. [External memory](https://xgboost.readthedocs.io/en/stable/tutorials/external_memory.html).

**Инженерная оценка, не замер:** 6000 Q×220 C×50 float32 требуют 264 MB только значений матрицы; copies, metadata, gradients, bins и caches добавляются. Предложение: CPU `hist`, 2 threads, один optional fit ≤60 минут; stop при peak RSS>24 GB, ошибке группировки/evaluator или недостаточном positive support. Начальные depth=6/max_bin=128 — предложения, не defaults. Лимит не расширяет общий ledger.

**P0:** protocol/evaluator и tuning plan ручного baseline. **P1:** один ограниченный XGBoost screening после этих gates; продолжение лишь при практически значимом validation gain или выгоде cost. **P2:** MAP/pairwise ablations, GPU/external memory, ensemble. Сравнивать одинаковые данные и общие CPU/временные бюджеты, оплачивая preprocessing и неудачи; одинаковое число деревьев не означает равную стоимость. После tuning единственная выбранная модель проходит закрытый confirmation. Без выигрыша optional-ветвь прекращается. Duplicate scan существующего backlog: отдельная «гипотеза пользы ещё одного бустинга» отклоняется как повтор выбора baseline; HYP-041/042 не занимаются.
