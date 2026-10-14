# 09. Vector search: сначала точный поиск, затем измеренная аппроксимация

15 октября 2026. Независимое исследование; реализация, установка пакетов и обучение не выполнялись. Источники: первичные документы ниже, общий brief, текущие backlog и candidate-pilot. При поиске HYP-004 случайно увидены отдельные строки опубликованных notes 02/03; выводы на них не опираются. Остальные новые исследования не читались.

## Контракт источника

Факт проекта: 166794 — число уникальных товаров **за весь октябрь**, не готовый каталог любого раннего момента. Определим `U(t)={i: first_observed(i)<t}`: proxy наблюдавшегося каталога, без доказательства наличия. `E_s` — товары с корректным вектором из checkpoint/snapshot, действительно доступного до `t`. Искомое множество `V(t)=U(t)∩E_s`. Векторный поиск не создаёт представления: нужны отдельно проверенные ALS/two-tower/behavioral vectors; тексты, изображения и готовый ARGUS не предполагаются.

Предлагаемое правило для query `(u,t)`: `A_L(u,t)=TopL_{i∈V(t)} q(u,t)ᵀx_i`, `L=min(100,|V(t)|)`. Query encoder использует только события пользователя `event_time<t`; для простого профиля — последние 7 суток, event weights объявляются вместе с моделью. Это grain query→product, не поиск по каждой строке события. Купленные ранее товары сохраняются; неизвестное взаимодействие не означает dislike. Пустой профиль/OOV без fold-in/content encoder возвращает пустой vector source и явную причину; fallback обеспечивают существующие recent/popular sources.

## Геометрия и корректность

Dot-trained факторы искать по inner product: нормализация товаров меняет ранжирование и может удалить полезную информацию норм. Cosine — отдельная абляция: нормировать **оба** ненулевых вектора. Тогда `||q−x||²=2−2qᵀx`. Faiss `METRIC_L2` возвращает squared L2; `METRIC_INNER_PRODUCT` максимизируется. Для L2-only индекса MIPS можно перевести в `x′=(x,√(R²−||x||²)), q′=(q,0)`, `R≥max||x||`: distance равна `||q||²+R²−2qᵀx`. Это не повод предпочесть преобразование прямому IP; новый товар с нормой выше R требует обновить преобразование. [Faiss: metrics](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances).

У hnswlib `ip` выдаёт **distance** `1−dot`, cosine — `1−cos`, l2 — квадрат расстояния; направление сортировки и преобразование в общий score обязательны. Zero-norm/NaN/Inf не нормировать и не заменять незаметно валидным нулём: mask и исключение из vector support. [Author README](https://github.com/nmslib/hnswlib).

## P0: exact reference и стоимость

Для 166k начать с блочного `QXᵀ` на существующем численном стеке, без новой зависимости. При необходимости Faiss FlatIP даёт точный reference, не требует обучения; ANN сравнивается с ним на идентичных `q/x/V`. [Official index guidance](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index).

Инженерная оценка, **не benchmark**: float32 item matrix при d=128 занимает `166794×128×4≈81.4 MiB`; d=64/256 — 40.7/162.9 MiB. Batch64 полного scoring требует ещё ≈40.7 MiB scores; item blocks 16384 ограничивают score buffer ≈4 MiB с потоковым merge top-L. Одна query — ≈21.35 млн multiply-accumulate при d=128. Полную матрицу users×items не хранить. Код/BLAS workspace, copies, embeddings model и события добавляют память; RAM 32/36 GB сама по себе не доказывает соблюдение бюджета. Точный dot существенно проще полного CatBoost scoring всех товаров с дорогими pair features.

Предлагаемый первый замер после появления разрешённых векторов: 100 заранее выбранных past-eligible queries, CPU ≤2 threads, ≤30 минут и peak RSS ≤6 GiB; отдельно materialization/build/search/time и output rows. Это остановочный budget, не обещание скорости. Если exact укладывается, ANN пока не нужен.

## P1/P2 и платформы

P1 при измеренном bottleneck: один HNSW index, начальные `M=16, ef_construction=200`; для L=100 сравнить `ef=100/200/400`, больше ef — дороже и обычно точнее. Graph memory hnswlib оценивается ≈M×8–10 bytes/item сверх vectors; при M16 это ≈20–25 MiB, без остальных накладных расходов. [Parameters](https://github.com/nmslib/hnswlib/blob/master/ALGO_PARAMS.md). Возможны incremental add/update, но snapshot остаётся неизменяемым для воспроизведения.

Faiss CPU официально имеет conda packages Windows x86-64 и macOS ARM; GPU packages перечислены для Linux x86-64 CUDA. Поэтому RTX3070 на Windows не означает доступный официальный GPU package; MPS backend в списке нет. Совместимость конкретного Python/ABI и фактическая VRAM не проверены. [INSTALL](https://github.com/facebookresearch/faiss/blob/main/INSTALL.md). hnswlib — лёгкая CPU-альтернатива, wheel/build на обеих машинах не проверен. Лицензии: [Faiss MIT](https://github.com/facebookresearch/faiss/blob/main/LICENSE), [hnswlib Apache-2.0](https://github.com/nmslib/hnswlib/blob/master/LICENSE). P2 ScaNN здесь добавляет платформенный барьер: official wheels Linux; TF bindings optional, поэтому утверждение «обязательно TensorFlow runtime» неверно. [ScaNN README](https://github.com/google-research/google-research/tree/master/scann).

## Временная материализация, проверки и эксперимент

Manifest хранит checkpoint hash/fit cutoff, snapshot/build/available_at, item mapping/vector hashes, dtype/dimension/metric/normalization, U cutoff, index/library version, seed/insertion order/threads и search parameters. Все fitted transforms также past-only; поздний checkpoint нельзя «исправить» фильтром U(t). Новый known ID без вектора остаётся OOV; frozen ID-only model его не обслуживает. Новый вычислимый вектор включается только после фактической доступности; stale index support показывается отдельно. Кеш query включает t/history version, checkpoint/index/filter hash/L; cache только по user_id неверен.

Пять edge cases: same-second peers исключены; `|V|<L` уменьшает k; zero vectors маскируются; новые IDs дают support miss; ties разрешаются score DESC/product_id ASC, включая всю пограничную группу до усечения exact top-L. ANN rerank упорядочит найденные кандидаты, но не восстановит пропущенных tied items. Seed не гарантирует межплатформенный bit-exact результат; сохранить index artifact и измерить вариативность. [Faiss reproducibility](https://github.com/facebookresearch/faiss/wiki/FAQ#reproducibility).

Фильтр применяется **до выбора** top-L: exact mask либо snapshot только V. ANN oversampling→filter может недобрать; нужен явный cap/shortfall, а не скрытый refill. hnswlib имеет label filter, но Python multithread filter документирован как медленный. [API](https://github.com/nmslib/hnswlib).

Отдельно измерять `ANNRecall@L=|A_ANN∩A_exact|/L` и purchase candidate Recall по полному Y, включая cold/out-of-support misses. Предлагаемая retrieval-абляция: `popular100+vector100+recent20` против текущего `popular200+recent20`, одинаковые Q/U/Y, no-refill и дополнительное size-matched сравнение; fixed-C embedding-feature опыт идёт отдельно. Текущий TLAB-004 не меняется. HYP-081/082 остаются не сформулированными: exact→ANN проверяет вычислительный компромисс, а новая самостоятельная purchase-механика пока не обоснована.


## Coordinator final-review appendix — 15 октября 2026

[Review09–12](review-09-12.md): zero norm invalidates cosine, но finite zero vector математически допустим для raw IP. Исключение zero vectors — declaredmodel-supportpolicy для exact/ANN, не свойствоIP. ANNRecall denominator |A_exact|=min(L,|V|), empty support undefined. Boundary ties acrossblocks разрешаются scoreDESC/IDASC; argpartition толькопоscore можетпотерятьнужныеtiedIDs. Eligibilityfilter не устраняет поздноfittedweights. ANNservingпока deferred до measuredexactbottleneck.
