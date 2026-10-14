# 06. Обученное user–item пространство как признаки CatBoost

Проверено 15 октября 2026. Независимое исследование; обучение не выполнялось. Контекст: сильный ручной boosting — контроль task1; clock-протокол, fixed C и full Y пока provisional. Источники проекта: `docs/argus.md`, `docs/sequential-embeddings.md`, `docs/embedding-experiments.md`, `docs/backlog.md`. Новые записки коллег не читались.

## Решение и граница применения

Предлагаю один past-fit checkpoint и несколько скаляров совместимости. Обученное пространство должно добавлять информацию сверх прямой истории, популярности и category affinity. Ни большая размерность, ни улучшение encoder-loss этого не доказывают. На REES46 медиана истории — четыре события; 96% событий — просмотры. «Любит» означает наблюдаемую активность при неизвестной экспозиции: view/cart/purchase не ratings, неизвестный товар не доказанный dislike.

Score на существующих кандидатах — **feature experiment**. Поиск максимального dot по каталогу — **retrieval experiment**, меняющий покрытие. Разделение retrieval/ranking подтверждает [официальный TensorFlow tutorial](https://www.tensorflow.org/recommenders/examples/basic_retrieval). Здесь C, Q и full Y сохраняются; пропущенный retrieval target остаётся miss. Полную матрицу 3 млн × 166 тыс. не строить; повторно купленные товары автоматически не исключать.

## P0: один ALS и четыре скаляра

P0 здесь — минимальная ветвь исследования, не обязательное расширение текущего ядра. Fit item factors V размерности d=64 до W. Начальная конфигурация: `r_ui = число view(u,i) до W`, `p_ui=1[r_ui>0]`, `c_ui=1+α log(1+r_ui)`, α и λ фиксируются до финального теста. Только один тип события делает MVP проверяемым; cart/purchase — последующая отдельная абляция. Частоты — confidence, не сила доказанной симпатии. ALS минимизирует `Σ_ui c_ui(p_ui−x_uᵀv_i)²+λ(Σ||x_u||²+Σ||v_i||²)`; [Hu, Koren, Volinsky, 2008](https://yifanhu.net/PUB/cf.pdf).

Для anchor t используем view-историю `[t−7d,t)`, объединяем по distinct item и считаем r_ui(t) по событиям. При замороженном V пересчитываем пользователя:

`x_u(t)=(VᵀC_u(t)V+λI)⁻¹VᵀC_u(t)p_u(t)`.

Это fold-in, включая пользователя, отсутствовавшего при fit. Решение линейной системы предпочтительнее явного обращения матрицы. `implicit` предоставляет [recalculate_user](https://benfred.github.io/implicit/api/models/cpu/als.html), возвращающий factors без изменения объекта. Item factors и глобальные fitted statistics остаются замороженными; fold-in обновляет локальное представление истории.

Для каждой пары `(query,user,item)`:

- `als_dot=xᵀv_i`: основной score, произвольные latent units, отрицательные значения допустимы;
- `als_cos=xᵀv_i/(||x||||v_i||)`: безразмерный угол, диапазон [−1,1];
- `als_user_norm=||x||`, `als_item_norm=||v_i||`: диагностические user-only/item-only controls в latent units, сами по себе не personalized crosses.

Дополнительно нужны `history_known_distinct`, `history_oov_fraction`, `item_fit_distinct_users` и empty/OOV/zero-norm flags. Support измеряется пользователями или товарами согласно имени, не смешивается с event count. При пустой известной view-истории fold-in даёт нулевой vector, но score считаем unavailable: NaN плюс флаг; OOV fraction при отсутствии view-событий — NaN. Неполные 7d отделяем coverage-флагом от полного окна. Истинный нулевой dot между доступными ненулевыми vectors сохраняем как 0. При нулевой норме cosine — NaN. Item, отсутствующий в V, также unavailable; его историю не выдумывать. Нормы/support уже имеющегося baseline не дублировать бесплатно.

## P1/P2: альтернативы, не одновременный ансамбль

**P1 BPR** меняет objective на pairwise `−log σ(s_ui−s_uj)` с regularization; [оригинальная работа](https://proceedings.mlr.press/r7/rendle09a.html). Unobserved j — sampled alternative, не зарегистрированный отказ. Обычный BPR lookup пользователя не обновляется автоматически от новой истории; среднее item factors не является его исходным user factor. Для cold user нужна явно описанная оптимизация x при frozen V либо отдельный history encoder. Не обещать ALS fold-in для BPR.

**P1 two-tower:** `h=f(history<t)`, `v=g(ID,category_id,brand,price_asof)`, общий loss обучает их dot. History pooling обходится без 3-миллионной user-ID таблицы. OOV ID + доступные metadata дают content fallback, но одинаковые metadata не различают товары. Начать с pooling и того же набора скаляров; [официальный пример side features](https://www.tensorflow.org/recommenders/examples/featurization).

**P2 sequence:** один SASRec-small против pooling, d=64/L=50; только если порядок даёт остаточную пользу. Оригинальный [код SASRec](https://github.com/kang205/SASRec/blob/master/model.py) использует causal attention и dot с output item table. Тип события/временные интервалы — наши расширения. Обычная треугольная mask пропускает peers одной секунды; необходима timestamp-aware mask или bucket protocol. Next-event score не становится purchase probability.

## Время, checkpoint и стоимость

Fit data/labels, vocabulary, sampler и normalization доступны до W; фактическое `fit_cutoff≤available_at≤первый downstream anchor`. CatBoost обучается после available_at, encoder frozen; вся группа timestamp предсказывается до обновления истории. Mature labels не дочитывают validation. Глобальную ось времени нельзя заменить leave-last-one-out: [Ji et al.](https://arxiv.org/abs/2010.11060).

Forward checkpoints — P2: сырые координаты между ними несопоставимы. Алгебраически общий ортогональный поворот сохраняет dot/cos/norm, но смена objective, confidence или обучения меняет шкалу. Более общие предсказательно эквивалентные факторизации сохраняют dot без сохранения cosine. Procrustes на общих прошлых items исправляет только часть координатного расхождения; не устраняет semantic/score drift. Проверять score-квантили и OOV по дням; calibration, если нужна, fit только на прошлом, без текущих labels.

Оценка памяти, не benchmark: item table d=64 float32 ≈40,7 MiB; user table ≈738 MiB, дополнительно CSR/solver. Scoring M пар — O(Md); точный fold-in — O(d²n_u+d³), с кешированием один раз на query, не на candidate. Дешевле контроль `mean(v_history)`: O(n_ud), но это другой score. Начальный gate: 100 queries, ≤30 минут/6 GiB; затем отдельная reservation encoder-fit/materialization внутри общего ledger, не поверх ≤4 fits/2 CPUh автоматизации. Превышение — deferred с cost report.

## Проверки и гипотезы

Пять edge cases: пустая история; полностью OOV история/item; same-second target; повторная покупка; checkpoint сменился при неизменной истории. Future-suffix invariance проверяет всю fit-chain, не только aggregation. Абляции: strong manual; +support/norm controls; +pooling dot/cos; +ALS dot/cos; только затем sequence. Одинаковые warm-up rows, C/full Y, бюджет tuning, warm/cold и repeat/new срезы. Предложенный promotion: нижняя граница 95% CI парной ΔNDCG@20>0, ΔRecall@20≥−0,002, preparation≤2×baseline и absolute budget; CI по пользователям. Текущий маленький pilot не даёт уверенного вывода.

**HYP-051 — needs-pilot, refinement:** fold-in ALS даёт пользу сверх pooling на тех же V благодаря confidence и учёту всего пространства. Counter: эффект объясняют популярность/повторы. Принять только по общей метрике и стоимости; отрицательный результат сохранить. **HYP-052 — rejected duplicate:** «добавить SASRec score в CatBoost» уже содержится в embedding-experiments; новый ID не создаёт новизны. Learned features не вытесняют основное сравнение автоматизации с настроенным ручным boosting.
