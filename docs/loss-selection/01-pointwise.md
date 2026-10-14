# L01 — Pointwise BCE: что именно означает отрицательная строка

Дата: 15 октября 2026. Независимое исследование; новые записки о моделях, loss, candidates и user–item не читались. Контекст: [исходный план](../experiment-plan.md), [данные](../data.md), [канонический backlog](../backlog.md). Никакие модели не обучались. Предпочтительный кандидат — purchase ranking; окончательные anchor, H и split ещё требуют решения.

## Две разные задачи

**Conversion после просмотра:** единица — определённый заранее наблюдаемый просмотр `(u,i,t)`, либо дедуплицированный episode с явным правилом начала. Метка `y=1`, если этот пользователь купил этот товар в выбранном будущем окне; иначе `0` только после созревания окна. При repeated views одна покупка может пометить несколько просмотров: это вероятность покупки после выбранной единицы наблюдения, а не независимые сделки. Если прогноз делается после наблюдения view, его товар/атрибуты доступны; остальные history events строго `<t`. При секундной точности нельзя утверждать, что purchase с тем же timestamp произошёл после view: для conversion предлагаю `(t,t+H]`, same-second случаи отдельно. Это отличается от уже обсуждаемого pre-update ranking `[t,t+H)`.

**Purchase ranking:** единица — `(q,i)`, где `q=(u,t)` выбран по past eligibility, `C_q` построен без будущего, а `Y_q` — distinct purchase-set в зафиксированном окне. `y_qi=1[i∈Y_q]`, `i∈C_q`. Ноль означает отсутствие зарегистрированной покупки в этом окне; без impressions он не означает dislike, отсутствие интереса или отказ после показа. Модель на выбранных строках не оценивает причинный эффект рекомендации. Purchased item вне `C_q` остаётся retrieval miss; вставлять его в обучение или evaluation oracle-способом нельзя.

## Точный loss и поддержка

Пусть `z_qi=fθ(x_qi)` — вещественный logit, `p=σ(z)`, `ℓ=−y ln p−(1−y)ln(1−p)`. Для зрелых непустых candidate groups предлагаю

`L = (1/|Q+|) Σ_q (1/|C_q|) Σ_i∈C_q ℓ(z_qi,y_qi)`.

`Q+` здесь означает **непустой C**, а не наличие покупки. Вклад каждого query равен одному; единица loss — nats на query при равномерном выборе его кандидата. Признаки — общий manual baseline, strict-past counters/recencies/category affinity и availability flags; одинаковый input поддерживает классификатор и ранжирующую модель. Никакого user×catalog tensor.

P0: CatBoostClassifier с `Logloss`, object weights `1/|C_q|`, без class balancing; сортировать raw score внутри query. Документация подтверждает оптимизацию Logloss на CPU/GPU; это не подтверждает доступность GPU на наших машинах. Нативные class weights умножают object weights и несовместимы с одновременными `auto_class_weights`/`scale_pos_weight`. [CatBoost objectives](https://catboost.ai/docs/en/concepts/loss-functions-classification), [параметры весов](https://catboost.ai/docs/en/references/training-parameters/common#class_weights).

Для нейросетевого кандидата тот же loss реализуется через `BCEWithLogitsLoss(reduction='none')` и явное суммирование с весами. Его `mean` делит по элементам, поэтому после masking нельзя оставлять padding в знаменателе. `pos_weight=β` умножает только положительный член; это не query normalization. Вычисление из logits устойчивее отдельного sigmoid→BCE. [PyTorch 2.14, проверено на дату исследования](https://docs.pytorch.org/docs/2.14/generated/torch.nn.BCEWithLogitsLoss.html).

## Sampling, вероятности и focal

Если внутри фиксированного `C_q` сохраняются все positives, а negative имеет известную вероятность включения `π_qi>0`, оценка исходной суммы использует `ℓ/π_qi`, сохраняя знаменатель `|C_q|`; для positives `π=1`. Это собственный вывод по линейности ожидания, без требования независимости включений. Деление на случайную сумму inverse weights даёт иной, self-normalized estimator. Для выборки с возвращением нужны веса по draw distribution и учёт multiplicity. Deterministic hard-only sampling с нулевым support невозможно исправить таким взвешиванием; корректировка внутри C не восстанавливает весь каталог.

Алгебраический минимум условного weighted BCE: `p*=βη/(βη+1−η)`, где `η=P(y=1|x)` до class weighting. При class-dependent selection rates `s1,s0` вместо β возникает `βs1/s0`. Постоянный множитель теоретически сохраняет порядок, но меняет вероятность; item-dependent sampling меняет и порядок. В конечной модели это не гарантия ни calibration, ни NDCG. BCE не учитывает top-K discount; улучшение logloss может происходить на лёгких negatives вне верхушки. Вероятности проверять только на зрелой несэмплированной целевой популяции C; перенос на другой retrieval или горизонт отдельно валидировать.

P2: focal `−α_y(1−p_y)^γ ln p_y`, `p_y=yp+(1−y)(1−p)`. Он подавляет easy examples, но может усилить noisy/hard unobserved labels. Исходная работа исследовала dense detection, не REES46. Теория показывает classification calibration, однако отсутствие strict properness при γ>0: score не обязан совпадать с posterior. Следовательно, imbalance сам по себе не основание включать focal в первый цикл. [Lin et al.](https://arxiv.org/html/1708.02002), [Charoenphakdee et al.](https://arxiv.org/abs/2011.09172).

## Контроль, бюджет и крайние случаи

P0 уже покрыт TLAB-008: один query-weighted BCE против PairLogit, одинаковые C/features/split и ограничение двух конфигураций. Сравнивать conditional macro-query NDCG@20, all-target Recall@20, user-macro и стоимость; logloss/Brier — диагностика вероятностей, не замена ranking metric. Proposed gate из backlog: 95% user-cluster interval ΔNDCG выше нуля, ΔRecall≥−0,002; неопределённость означает needs-pilot.

P1 **HYP-027, needs-pilot:** sampling с inverse-inclusion weights сохраняет full-C BCE лучше невзвешенного sampling при меньшем числе строк. Counter: дисперсия больших весов уничтожит экономию. Контроль — full-C BCE; сохранять positives и равномерно выбирать без возвращения фиксированные `m=max(1,floor(Nneg/4))` negatives при `Nneg>0`, `π=m/Nneg`. Тогда сумма весов каждого query детерминирована; нормировка CatBoost не добавляет случайный знаменатель. Два варианта на одном sample, максимум два дополнительных fit/60 CPU-минут, 2 threads, RSS≤8 GB, после008. Предложенный отдельный gate экономии: нижние границы парных 95% интервалов ΔNDCG/ΔRecall против full-C≥−0,002, число строк≤½ и wall time ниже; несэмплированный logloss не хуже невзвешенного sampling. Иначе deferred/rejected с cost ledger. HYP-028 не предлагается: focal пока не оправдан, отдельный PairLogit/BCE experiment дублировал бы008.

Оценка, не benchmark: 6 000×220=1,32 млн строк; 18 float32 features занимают около95 MB без IDs, quantization и training buffers. Полный user×166 794 каталог исключён. Реальную память/время измерять до расширения.

Проверки: зрелое `Y=∅` сохраняется и даёт BCE-gradient; `C=∅` маскируется без деления на ноль, остаётся в evaluation; незрелое окно исключается, не превращается в negatives; all-positive группа допустима BCE, но не даёт negative contrast; точные дубли не равны repeated purchases. Fit priors/encoders и calibration cutoff должны предшествовать своим predictions; same-second peers не упорядочиваются по ID. Главная развилка — условная conversion после view или покупка среди past-generated кандидатов: один sigmoid не делает эти estimands одинаковыми.
