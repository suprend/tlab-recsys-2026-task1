# M06. Две башни: pooled history как замороженный генератор признаков

Дата: 15 октября 2026. Независимое исследование; обучение и изменение репозитория не выполнялись. Контекст: `docs/embedding-experiments.md`, `docs/experiment-plan.md`, общие feature/target briefs. Anchor, H, relevance и split требуют отдельного решения.

## Рекомендация и границы

Первым проверять небольшой совместно обученный user/item space поверх сильного настроенного ручного бустинга B. Самостоятельный dot-ranker — диагностический контроль; добавление ANN-кандидатов — другой эксперимент. Так сохраняется требование Task1: автоматизировать представления либо доказать выигрыш над настроенным контролем при одинаковых данных и бюджете. Обычная двухбашенная архитектура сама по себе не новая исследовательская идея.

Данные позволяют ID/category/brand/price и историю view/cart/purchase. Богатых текстов, изображений, impressions и готового pretrained ARGUS нет. Медиана четыре события означает, что pooling — содержательный дешёвый контроль; усложнение encoder ещё надо заслужить. Первичная работа [Yi et al., RecSys 2019](https://storage.googleapis.com/gweb-research2023-media/pubtools/5716.pdf) описывает совместные башни и inner-product retrieval; её результаты YouTube не являются прогнозом эффекта REES46.

## Точный небольшой кандидат

Единица прогноза q=(user,t), единица downstream-признаков (q,item). Предлагается d=64; это стартовая конфигурация, не установленный optimum. Item tower: e(i,a)=MLP_item([E_ID(i),E_categoryID(a),E_brand(a),missing_flags]), выход 64. Категориальные числа — lookup, не порядковые величины. User tower получает среднее тех же e по последним максимум 50 событиям строго раньше t (границу 50 обрезать целыми timestamp-buckets), log1p счётчики трёх event_type и флаг пустой истории; MLP_user: 128→64. Все веса обучаются совместно. Отдельной таблицы трёх миллионов user ID нет: новый пользователь с историей получает профиль непосредственно из неё.

Для исторического события a — атрибуты, наблюдаемые к его времени; для кандидата — последние известные строго до t. Missing brand/category_code не превращать в вымышленный текст; categoryID остаётся доступен. В P0 цена остаётся отдельным as-of признаком B. В P1 допустимо добавить log1p(price), zero-price и missing-price в item tower, используя historical price для истории и latest-known-before-t для кандидата. Нормализацию fit только в warm-up. Изменение price/brand требует пересчёта item vector и индекса; кэш по одному ID уже недостаточен. Нулевая цена — наблюдаемое значение, отсутствие — отдельный случай.

Основной score s_dot=z_qᵀe_i. Контроль s_cos=z_qᵀe_i/(||z_q||||e_i||), с epsilon и флагом нулевой нормы; training logit=s/τ. Dot сохраняет влияние норм, cosine устраняет его; пользу ни одного заранее не утверждать. Сравнивать отдельно обученные варианты с одинаковым маленьким budget для τ, а не просто заменить score после обучения. Пара MLP([z,e,z⊙e,|z−e|]) — P2-reranker: произвольная такая функция не сводится к одному ANN dot-search. Независимые башни соединяются поздно; кандидат не влияет на pooling. Разделение retrieval/ranking подтверждено [официальным TFRS tutorial](https://www.tensorflow.org/recommenders/examples/basic_retrieval).

## Purchase objective, support и нули

Предлагаемый вариант после утверждения set-target: P_q — distinct purchases в (t,t+H], полностью зрелые к fit cutoff; точные дубли удаляются согласно общей политике, повторы разных покупок остаются в истории. V_t — prior-observed catalog proxy, без утверждения stock availability. Для обучаемой части P′=P∩V_t взять 128 уникальных uniform negatives N⊂V_t\P; если support меньше — все доступные. Потеря на query:

`L_q = − mean_{p∈P′} log[exp(s(q,p)/τ)/(exp(s(q,p)/τ)+Σ_{n∈N}exp(s(q,n)/τ))]`.

Это явно заданная sampled contrastive loss, не точная full-softmax likelihood и не вероятность покупки. Если P′ пуст, retrieval loss пропускается; долю таких queries показывать. Если negatives отсутствуют, query не даёт contrastive signal. Zero-purchase queries сохранять в downstream оценке: отдельно доля нулей, условная buyer-метрика и заранее выбранная конвенция all-query метрики. Такой encoder учит выбор товара при покупке, но не вероятность возникновения покупки.

Другие target-positives не становятся negatives; ранее купленное не исключается автоматически. In-batch sampling — P1 с маской совпадений и всех выбранных target-positives, past-only Q и документированной коррекцией. Uniform-P0 не переносит механически logQ из другой схемы. [TFRS Retrieval API](https://www.tensorflow.org/recommenders/api_docs/python/tfrs/tasks/Retrieval) различает accidental hits, temperature и sampling probabilities. Неизвестное взаимодействие без impressions не является доказанным отказом.

## Доступность и холодный старт

Warm-up W должен закончить все encoder-labels до первого downstream anchor B; vocabulary, scaler, sampler priors и weights затем frozen. History обновляется по фактически прошедшим событиям, параметры — нет. Одна секунда обрабатывается до обновления state, без порядка по ID. Новые после W товары используют UNKNOWN_ID плюс известные as-of metadata; UNKNOWN обучить небольшой ID-dropout только внутри W, иначе это необученный fallback. Новые metadata тоже OOV. Пустая история получает fallback past-popularity; neural similarities — нули с empty-флагом. Target вне V_t считается miss с отдельной coverage; положительный товар нельзя вставить oracle-образом. Forward snapshots — P2: координаты разных пространств несопоставимы, scalar scores тоже дрейфуют.

## Бюджет, сравнение и остановка

Инженерные оценки, не замеры: 166794×64 float32≈40.7 MiB; weights+gradients+два Adam moments≈163 MiB только ID-таблица. Батч 512×50×64≈6.25 MiB history activations до дополнительных слоёв. Все 42 млн event embeddings материализовать не нужно. Mac CPU и Windows CPU/CUDA поддерживаются [PyTorch](https://docs.pytorch.org/get-started/locally/); реальные версии, driver и 8GB VRAM проверить перед запуском. Малый streamed pilot разумен для 32GB RAM/8GB GPU, но throughput не измерен. [EmbeddingBag](https://docs.pytorch.org/docs/2.14/generated/torch.nn.modules.sparse.EmbeddingBag.html) экономит промежуточные lookup tensors; взвешивание поддерживается с sum, не weighted mean напрямую. Фреймворк имеет [BSD-style LICENSE](https://github.com/pytorch/pytorch/blob/main/LICENSE); специальных ANN/legacy зависимостей P0 не требует.

P0: одинаковые anchors/candidates, настроенный B; B+dot/cos/norms/empty-OOV flags; standalone dot; дешёвый pooling/ItemCF контроль. P1: ID-only против ID+metadata; затем price или раздельные event-type pools, по одному изменению. P2: ANN-union с отдельным stage Recall и end-to-end ranking, MLP, forward fitting. HYP071/072 не оформлять как новые без сверки: основная лестница уже предложена embedding-протоколом.

Остановить ветку, если выигрыш B+encoder не воспроизводится на заранее выбранных временных срезах/seed, исчезает против настроенного дешёвого контроля, ограничен скрытым warm-only отбором либо превышает заданный budget. Проверять uncertainty по пользователям, расходы materialization и coverage. Падение train loss, лучший sampled Recall и улучшение retrieval сами по себе не доказывают улучшения финального purchase ranking.


## Coordinator protocol appendix — 15 октября 2026

Исходная note предлагает right-closed target (t,t+H]. Для текущего provisional clock использовать [t,t+H) из protocol manifest; при source availability<c зрелость right-open t+H+delay≤c, right-closed требует строгого <c. Это разные protocol IDs, не косметическая замена. Warm-up weights/vocabulary/scaler/sampler требуют fit_cutoff≤available_at≤first downstream anchor, не просто labels до W. Latest global metadata bucket разрешается с NULL/conflict flags без older-clean backoff. HYP071/072 остаются reserved до integration review; базовая frozen-encoder лестница уже есть в embedding protocol. Source proposals не дают новый fit budget.


[Независимый integration review M06](integration-review-06.md) дополнительно задаёт mean_q по nonempty supported-positive/negative queries, причины skip и uniform-without-replacement sample m=min(128,support). Это sampled per-positive contrast, не full CE/BCE. Matched ALS/pooling controls фиксируют одинаковые history inputs. Whole-bucket cap50 требует overflow policy: например остановиться перед crossing bucket с truncation flags, без ID order. MLP input68→hidden128→64 уточняется до реализации. Zero-norm cosine — masked sentinel. HYP071/072 остаются reserved, не новые сформулированные hypotheses.
