# Цель модели: ранжирование будущих покупок

Дата исследования: 14 октября 2026. Пользователь рассматривает purchase ranking главным кандидатом; точные anchor, горизонт, relevance, candidate universe, метрики и разбиение ещё не утверждены. Восемь независимых записок и два независимых ревью — исследование дизайна, без обучения моделей и без реализации pipeline.

## Независимые углы

1. [Anchors: ситуация выдачи](01-anchors.md).
2. [Target: следующая покупка или набор периода](02-purchase-target.md).
3. [Candidates: universe и потери retrieval](03-candidates.md).
4. [Обучение и negatives](04-training-negatives.md).
5. [Метрики, нулевые queries и uncertainty](05-evaluation.md).
6. [Временная схема и fitted states](06-temporal-protocol.md).
7. [Соответствие T-Lab и проверяемая гипотеза](07-tlab-alignment.md).
8. [Скептическая проверка осуществимости](08-feasibility.md).

## Что именно проверяет опыт

Одна query — пользователь и допустимый момент прогноза `(u,t)`; ranker оценивает известные на этот момент товары-кандидаты. Будущие purchase определяют relevance в заранее заданном окне. В прошлом только `event_time<t`; одинаковые глобальные секунды обрабатываются до обновления любого shared state. Ingestion timestamp отсутствует: replay предполагает доступность события сразу после его секунды, не доказывает реальную задержку сервинга.

Нет impressions, orderID и доступности каталога. Offline predictability зарегистрированных покупок не измеряет причинный uplift рекомендаций. View/cart/purchase — разные наблюдения; отсутствие покупки не является доказанным disliked impression. История одного октября цензурирована слева и справа.

## Матрица решений

| Решение | Предложенный старт для development pilot | Альтернатива / что ещё измерить |
|---|---|---|
| Ситуация выдачи | Fixed clock перед глобальной timestamp-группой, 00:00 UTC, один query `(u,t,protocol_id)` в сутки. | 12:00 UTC и action-triggered queries — другие protocol IDs, не взаимозаменяемые строки. |
| Eligibility | Есть любое событие в `[t−7d,t)`, без условия будущего посещения/покупки. | 48h из feasibility меняет population; сравнить число queries, positive prevalence и coverage на development. |
| Target | Distinct `product_id` с purchase в `[t,t+24h)`, бинарная relevance; ранее купленные товары разрешены. | `(t,t+H]` исключает anchor-секунду, но включает правую. Next-purchase target — все distinct товары первой purchase-секунды, не произвольная строка. |
| Зрелость | При доступных событиях `<S` полуоткрытый target зрел при `t+H≤S`; конец файла также исключительный. | Для закрытого правого конца требуется `t+H<S`. Включение текущего view-context не разрешает считать same-second purchase последующей реакцией. |
| Universe | `U(t)={i: есть event_time<t}` — proxy известного ассортимента, не stock. | Action-context впервые наблюдаемого item требует отдельного `U_action=U(t)∪current_view_items` либо явного ограничения baseline прежним C. |
| Candidates | Для первого bounded pilot — past popularity + recent distinct history, один manifest C для всех feature branches. | M200/M1000 и ItemCF/ANN quotas пока предложены авторами, не выбраны. Сначала coverage/cost; ItemCF требует законченной формулы, cutoff и fusion policy. |
| Обучение | После feasibility/feature checks сравнить query-normalized PairLogit и weighted BCE на одинаковых C/features. | PairLogit не получает сигнал без covered positives или negatives; BCE сохраняет нулевые matured anchors. QuerySoftMax требует явной нормировки. |
| Основная оценка | Conditional macro-query NDCG@20 и Recall@20 по полному Y; дополнительно K=10. | Все mature queries сохраняются: p покупки, пустые/непокрытые/empty-C состояния, all-query zero-конвенция и user-macro явно отдельно. |
| Временная схема | Консервативный календарь A из записки 06, warmup/freeze 8 октября, одинаковые cutoff/refresh у branches. | H72h и forward-refit C — иные процедуры; refit должен быть одинаков у всех сравниваемых моделей. |
| Исследовательская гипотеза | Strong manual CatBoost → +совместимые user×item scalar scores при фиксированных candidates и равном бюджете. | Автоматический конструктор агрегатов и улучшение retrieval — отдельные исследования, с собственными контролями. |

## Предлагаемый первый протокол и ограничения

Это согласующее предложение для пилота, а не окончательное решение пользователя. Первые исследования и ревью не измеряли пригодность labels, покрытие кандидатов, runtime или качество моделей. Новая авторизация ночного backlog позволяет проверять конфигурационные варианты; не делает один из них автоматически утверждённой постановкой.

Первый bounded pilot: development-дни 8–10 октября, до 2 000 past-eligible пользователей на день по заранее фиксированному hash; shortlist до 200 past-popular + 20 recent distinct. Максимум `3×2000×220=1,32 млн` candidate rows до дедупликации — арифметическая граница, не benchmark. Сначала сравнить popularity/recent rules и посчитать positive-query support, target sizes, repeat/explore, cold targets, universe/candidate coverage, feature materialization cost. Другие eligibility/window варианты получают отдельные manifests и отчёты. Final test не участвует в выборе этого пилота.

Для proposed calendar A: warmup `[10-01,10-08)`, boosting anchors `[10-08,10-21)`, fit 10-22; validation `[10-22,10-25)`, выбор 10-26; test `[10-26,10-31)`. Все даты UTC 2019 года. Это консервативная схема; изменение endpoints не требует молча сдвигать исходные календари. Source data cutoff, model availability, label cutoff, refresh policy и protocol version записываются раздельно. Encoder/IDF/clusters/scalers заморожены до downstream периода; observed histories/counters/metadata обновляются строго прошлым. ItemCF/retrieval refresh следует выбрать явно (freeze на warmup либо past-only snapshots), одинаково для branches.

Основные метрики используют полный ground truth независимо от universe и shortlist. Для `|Y|=3`, одного релевантного результата первым и K≥3: Recall=1/3, NDCG≈0,469; candidate-only IDCG ошибочно даст 1. Missing targets не добавляются в возвращённый список с `−∞`: если shortlist короче K, отсутствующие позиции дают ноль, а не реальные ранги. Tie-break один и тот же у всех моделей.

Для conditional query-macro метрики парный bootstrap выбирает пользователей с multiplicity k_u и пересчитывает `Σ_u k_u Σ_q m_q / Σ_u k_u n_u` по непустым mature queries. Среднее user means — другой estimand. `all-query=p×conditional` верно только при том же query-усреднении; ноль пустым queries не проверяет вероятность покупки или отказ от выдачи. Показывать дневные срезы отдельно; один октябрь не подтверждает устойчивость к будущим сезонам.


## Ревью и следующие решения

[Независимое ревью 1–4](review-01-04.md) и [ревью 5–8](review-05-08.md) сохранены целиком. Исходные записки сохраняют собственные окна, часы и бюджеты; согласующие review appendix помечены отдельно.

Следующие решения: clock/action; eligibility7d/48h; H и endpoints; candidate manifest/budget/refresh; query/user weighting и objective; refit и validation budget. Недостаточный support или coverage — основание пересмотреть конкретный протокол, а не бесконечно наращивать модель. View-conversion — явно другая fallback-задача, с собственными anchors, labels и метриками.

[Единый исполняемый backlog](../backlog.md) ведёт реализации, проверки и бюджеты отдельно от исследовательских рекомендаций. Ночные задачи разрешены последующей явной просьбой пользователя; сами независимые research notes остаются отчётами без запуска моделей.

Результаты первоначальных исследований признаков сохранены отдельно: [16 записок и два ревью](../features/index.md). Совместимость user×item и аудитория товара рассматриваются в отдельной очереди; ссылка на неё появится в индексе признаков после публикации.
