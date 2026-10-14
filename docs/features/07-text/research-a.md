# 7A. Лексические metadata-признаки: сначала измерить идентичность

Дата: 14 октября 2026. Независимое исследование; реализация и обучение не выполнялись. Записка 7B не читалась. Локальный контекст: `docs/nlp-tokenization.md`, `docs/nlp-bm25.md`, `docs/nlp-experiments.md`, `docs/text-embeddings.md` проекта tlab-recsys-2026.

## Факты и граница гипотезы

По предоставленному October-аудиту: 126 заполненных category_code на 252 category_id, 372 ID без имени; 3445 брендов. Нет titles, descriptions, search queries. Категория отсутствует в 31,84% событий, бренд — в 14,40%; brand менялся у 137 товаров. Эти числа описывают полный месяц, не доступный раннему прогнозу каталог. Документы проекта отмечают 22 кода с underscore и реальные бренды `p.i.t.`, `tp-link`, `am.pm`.

**Вывод:** одинаковые category+brand делают текстовые представления товаров одинаковыми. Лексический score здесь сжимает историю metadata, а не восстанавливает индивидуальное содержание товара. Перенос через общее слово — проверяемая гипотеза; точное совпадение пути или бренда — идентичность. Прирост иерархических токенов нельзя автоматически приписать NLP.

## P0: полезный минимум

Сильный общий baseline уже содержит category_id, brand, hierarchy и причинные affinity/count/recency. Дополнение — **один category TF–IDF cosine** на grain `(user, candidate, t)`, сначала views в rolling `[t−7 суток,t)` UTC. Семь суток — предложенный старт, не утверждённый оптимум. Cart/purchase и дополнительные окна в MVP не размножать; выбор target/horizon/split остаётся открытым.

Токенизация H: `furniture.living_room.cabinet` → `cat_path:furniture`, `cat_path:furniture.living_room`, полный `cat_path:furniture.living_room.cabinet`. Каждый токен один раз; numeric category_id остаётся categorical. Бренд хранить отдельно атомарным `brand:tp-link`, с сохранением пунктуации; отсутствующее значение не создавать как общий текст `unknown`. Сырой текст сохраняется, нормализация копии — NFC/trim/casefold. Готовые списки передавать callable analyzer: стандартный sklearn tokenizer разделяет пунктуацию, отбрасывает односимвольные слова, сохраняет underscore. Это может стереть `p.i.t.` или смешать разные бренды. [Официальный API](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html).

Корпус P0 — **уникальные непустые строки категорий**, наблюдённые до warmup-cutoff `t₀`, без брендов. `N` — число таких документов; `df(z)` — число содержащих токен документов. Определить `idf(z)=1+ln((1+N)/(1+df(z)))`; `x(c)=L2norm(binary_tokens(c)·idf)`. Профиль `q(u,t)=Σ x(c_j)` по уникальным product_id, просмотренным в окне, с категорией последнего допустимого просмотра каждого товара; это наша защита от доминирования refresh, а не удаление событий. `lex_cat_cos=cos(x(candidate),q)`; L2-нормировка соответствует cosine через dot product. [TF–IDF: формула и нормировка](https://scikit-learn.org/stable/modules/feature_extraction.html#tfidf-term-weighting).

Сохранять support: число уникальных просмотренных товаров, число с текстом, число с ненулевым in-vocabulary вектором, `history_observed_seconds`. Пустой вектор → score=0 плюс отдельные `candidate_text_missing`, `profile_empty`, `candidate_oov_fraction`. Ноль при известных непересекающихся токенах отличается от отсутствия текста. Порог support не выдумывать: сначала явные support-поля, затем проверка качества по диапазонам. Brand-share, если его нет в baseline: доля уникальных просмотренных товаров с точным брендом кандидата среди товаров с известным брендом; denominator=0 → missing и support=0. Это категориальный контроль, не дополнительная семантика.

## P1/P2: что проверять дальше

**P1:** H+W, где W — отдельные `cat_word:` после разделения по точке и underscore. `coffee_machine` и `coffee_grinder` разделяют `coffee`; одноимённые листья разных веток сохраняют различия в H. Без stemming, автоперевода и сгенерированных описаний. Бренды не разбивать на слова.

**P1:** определённый weighted BM25, документ — категория кандидата, query-вес `a_z` — доля уникальных прошлых товаров, содержащих z:

`Σ_z a_z·I_z·f_z(k₁+1)/(f_z+k₁(1−b+b·L/avgL))`,

где `I_z=ln(1+(N−df_z+0.5)/(df_z+0.5))`, `k₁=1.2`, `b∈{0,0.75}`. Корпус и история те же. Положительный IDF и смысл параметров подтверждены [Lucene](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/BM25Similarity.html); общая форма — [Stanford IR book](https://nlp.stanford.edu/IR-book/html/htmledition/okapi-bm25-a-non-binary-model-1.html). Это явно заданная адаптация, не реальный search query. При binary `f=1,b=0` дробь равна 1: остаётся IDF-overlap; большой поиск k₁ не обоснован. Обратное направление с user-history документом меняет TF, DF и length normalization — отдельная гипотеза.

**P2:** character n-grams, brand morphology, per-product corpus и dense semantic comparator. Per-product DF отражает ассортимент, per-category DF — taxonomy; события как документы смешают редкость с популярностью.

## Время, стоимость, проверки

Vocabulary/IDF/avgL fit до первого training prediction и freeze; пользовательская история обновляется вперёд. Fit до конца train тоже заглядывает в будущее ранних train-строк. Новые слова — OOV, без будущего словаря. Candidate metadata берётся из прошлого as-of либо текущего наблюдаемого контекста только при разрешающем anchor; история использует metadata соответствующих прошлых событий, без позднего backfill. Все same-second predictions выполняются до обновления состояния группой. Поздние восстановленные category names исключить.

Материализовать sparse-векторы уникальных категорий и пользовательские счётчики с expiry; при повторном товаре поддерживать замену последнего просмотра. Считать только evaluation/training пары, без user×catalog матрицы. Стоимость зависит главным образом от обработки событий и состояния уникальных user–product, не от 126 строк; RAM/скорость не измерены.

Абляции: baseline → H-cosine → H+W-cosine; IDF против единичных весов; BM25 против того же overlap; distinct-product против event-weighted профиля. Сохранять anchors/candidates, окна и доступность текста; показывать общий результат и slices без точного category match, с пропущенным текстом, короткой историей. P0 может оказаться избыточным над сильным hierarchy baseline — это полезный отрицательный результат.

Edge cases: (1) null/null не создаёт общего сходства; (2) `am.pm`≠`am-pm`, `p.i.t.` непуст; (3) одинаковый leaf в разных ветках сохраняет namespace; (4) новый код имеет OOV-флаг; (5) добавление future/same-second события не меняет ранние score, IDF или as-of metadata; конфликт brand в одной секунде отмечается неоднозначным, без случайного порядка.

## Review appendix — 14 октября 2026

Перед сравнением representations фиксировать weighting: unique-product профиль этой записки и event-weighted профиль 7B — разные эксперименты. На одном weighting сравнивать full-category-code one-hot → prefix TF-IDF → dense/random при тех же channels, агрегаторах и missing/OOV masks. Контроль текстовой идентичности строится по category_code, не category_id; exact affinities для unique-product опыта получают тот же denominator. Затем отдельно сравнивать event и unique-product weighting. Слова «причинные affinity» в исходном baseline означают только строго прошлую доступность, не установленный причинный эффект.

Основание: [независимое ревью тем 05-08](../review-05-08.md) и [общий синтез](../index.md). Исходная записка выше сохранена целиком.
