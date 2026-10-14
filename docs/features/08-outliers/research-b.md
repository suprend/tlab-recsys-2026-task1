# Тема 8B. Сохранить хвост для CatBoost, проверить геометрию для кластеров

Дата: 14 октября 2026. Независимый угол: преобразование признака должно соответствовать потребителю. Записка 8A не читалась; данные не пересчитывались, рекомендации ниже — эксперименты, не измеренные улучшения.

## Факты и интерпретация

По предоставленному контексту медиана пользователя — четыре события и один наблюдаемый активный день; нулевых цен 68 673, отрицательных нет. Это не доказывает, что высокая активность — бот, а нулевая цена — бесплатный товар. Без отдельного доказательства пользователей и события из хвоста не удаляем.

CatBoost задаёт числовые разбиения через квантование; доступны разные методы выбора границ и настройка числа границ по признаку. Следовательно, большой масштаб счётчика сам по себе не требует стандартизации. Математически строго монотонный log сохраняет порядок и допустимые пороговые разделения, но полную идентичность конкретного обучения обещать нельзя: способ квантования и численная точность имеют значение. Проверять log следует как вариант, а не обязательную обработку всех столбцов. [CatBoost: quantization settings](https://catboost.ai/docs/en/references/training-parameters/quantization).

K-means использует квадраты евклидовых расстояний: изменение масштаба координаты меняет её вклад в целевую функцию. Поэтому исходные counts могут группировать прежде всего по объёму активности — это вывод из геометрии, а не установленный дефект наших данных. [scikit-learn: clustering](https://scikit-learn.org/stable/modules/clustering.html).

## P0: минимальный baseline

В момент UTC t используем только события [t−7 суток,t); одинаковую секунду прогнозируем до обновления состояния. Grain — пользователь на anchor. `u_view_7d`, `u_cart_7d`, `u_purchase_7d` считаем раздельно; ноль означает отсутствие соответствующих наблюдавшихся событий, не отсутствие истории вообще. Добавляем `u_has_history` и `observed_age_days=t−first_observed_time`; для первого anchor возраст ноль, признак истории ноль. Возраст — наблюдение с начала октября, не lifetime. Эти признаки повторно используем из общего feature store, не строим новые окна ради robustification.

`price_zero` и `price_missing` на grain candidate product×anchor допустимы только для цены, известной к t согласно anchor; неизвестную цену оставляем NaN. Нулевую цену сохраняем отдельно от пропуска. Минимум не содержит fitted outlier cutoff. Все исходные значения сохраняются.

Стоимость: преобразования флагов O(N) поверх N материализованных строк; счётчики требуют существующего strict-past прохода и состояния активных пользователей/окон. Это оценка сложности, не benchmark памяти или скорости.

## P1: три контролируемых варианта

1. **Log:** `log1p_count=ln(1+x)` для трёх P0 счётчиков; ноль остаётся нулём, fit отсутствует. В CatBoost сначала заменяем counts, затем отдельно проверяем добавление к raw. Последнее может лишь дублировать информацию.
2. **Winsorization:** `x_cap=min(x,Q_0.995(s))`, `above_cap=1[x>Q_0.995(s)]`. Порог — предложенный, не оптимальный. Нижний хвост не обрезаем. Флаг различает обычное значение и превышение, но не восстанавливает различия внутри хвоста; raw сохраняем в хранилище и контрольном варианте модели.
3. **Robust scaling для плотного cluster/encoder input:** `z=(ln(1+x)−median_s)/IQR_s`, где статистики относятся к log-count. При IQR=0 используем scale=1 и `constant_scale`; пропуск сначала сопровождаем mask, затем импутируем past-fit медианой для алгоритма без NaN. RobustScaler использует median/IQR, но сами экстремальные наблюдения остаются экстремальными; его нельзя считать заменой clipping. [RobustScaler](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.RobustScaler.html), [официальное сравнение scalers](https://scikit-learn.org/stable/auto_examples/preprocessing/plot_all_scaling.html).

Для разреженного user×category behavioral вектора сравнить TF-IDF с raw TF и `tf=1+ln(count)` при count>0, затем L2-нормирование; это не `log1p`. TF-IDF здесь адаптация к поведению, не текстовые признаки: описаний товаров нет. IDF оценивать по одному документу пользователя на snapshot, не по повторённым candidate-строкам. Центрирование sparse-вектора исключить из-за уплотнения. [TfidfTransformer](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfTransformer.html), [RobustScaler](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.RobustScaler.html).

## Временной контракт и стоимость

Любые внешние quantiles, median/IQR, IDF, priors и encoder weights fit на snapshot s<t, причём s раньше первой downstream training prediction: warmup→freeze либо forward snapshots. Fit на конце train не делает ранние train representations strict-past. Выбор модели на training cutoff — отдельный уровень обучения. Для target-derived priors нужны зрелые outcomes и delay. На validation/test можно обновлять наблюдаемую историю по принятому протоколу, сохраняя fitted transforms. Обычный запрет fit на test необходим, но наша временная политика строже. [scikit-learn: leakage](https://scikit-learn.org/stable/common_pitfalls.html).

Фит статистик выполняем на уникальных user snapshots, иначе пользователи с большим числом anchors/candidates получают лишний вес. Храним version, cutoff, support и fallback. Точные квантили требуют сортировки/агрегации; bounded sample или sketch — отдельный компромисс. Применение P1 — O(Nd), параметры — O(d); sparse TF-IDF — O(nnz). Кластеры требуют отдельного замера.

## P2, ablations и крайние случаи

P2: conditional price median/IQR по category_id, anomaly scores и adaptive clipping — только после выигрыша P1. Не нормировать числовые IDs.

На одинаковых anchors/candidates сравнить raw+flags, log, cap+flag, raw+cap+flag; cluster input — log против log+robust и TF-IDF raw/sublinear. Измерять downstream metric после выбора target, стоимость и результат по past-defined хвосту/короткой истории; для кластеров также размеры и устойчивость между seeds. K-means на sparse-векторах может получать изолированные центроиды; silhouette не заменяет downstream gain. [Официальный пример](https://scikit-learn.org/stable/auto_examples/text/plot_document_clustering.html).

Пять проверок: первый anchor и пустой TF-IDF-вектор; IQR=0 у разреженного purchase-count; легитимный сверхактивный покупатель; новый товар/категория без support; скачок активности после замороженного cutoff. В последнем случае считаем долю clipping и drift, не переобучаем transform задним числом. Полные дубли и повторные покупки различаем отдельной согласованной политикой, а не outlier-фильтром.

## Review appendix — 14 октября 2026

Канонический strict-past first_observed_time определяется только среди s<t; у первого anchor его нет, поэтому observed age — missing и has_history=0. Численный 0 допустим только как явно объявленный sentinel с mask; возраст наблюдаемого текущего anchor — отдельный context feature. Сохранённый численный zero-price сравнивается с derived positive-price/price-state из 8A при неизменном raw. Упоминание feature store означает существующий слой materialization, не предложение внедрить отдельный framework.

Основание: [независимое ревью тем 05-08](../review-05-08.md) и [общий синтез](../index.md). Исходная записка выше сохранена целиком.
