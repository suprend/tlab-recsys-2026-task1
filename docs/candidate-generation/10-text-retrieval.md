# 10. Текстовая кандидатогенерация на category/brand

Дата: 15 октября 2026. Независимое исследование; без обучения, установки, изменения данных или текущего candidate run. Первичные источники проверены браузером. Локальные `docs/nlp-bm25.md`, `docs/text-embeddings.md` и `docs/experiments/candidate-pilot.md` использованы как контекст. Все параметры ниже — предложения отдельного эксперимента, не принятый протокол.

## Факты и граница задачи

По предоставленной October-диагностике имеются 126 уникальных `category_code`, 3445 брендов и 5987 пар `(category_code, brand)`, включая пропуски, при 166794 товарах. Это размеры полного месяца, не раннего доступного корпуса. Названий, описаний, изображений и поисковых запросов нет. Текстовый retrieval здесь означает поиск метаданных по прошлому профилю интереса, а не восстановление пользовательского запроса.

624 `category_id` не равны 126 кодам: несколько IDs имеют одинаковый текст, 372 IDs не имеют имени. Их нельзя семантически объединять токеном `unknown`. Числовой ID остаётся независимым категориальным каналом. Поздние предположительные названия и pretrained ARGUS не считаются доступными источниками. Поведенчески наблюдавшийся товар входит в proxy known catalog, но это не доказательство наличия на складе.

## P0: контроль прежде нового источника

Сохранить принятый TLAB-004: popularity200 + recent20, dedup без refill, C≤220. Новый retrieval запускается отдельной версией; текущий C для feature experiments не меняется. Минимальные контроли нового источника — популярность внутри персональных `category_id`, затем exact code/brand identity и category-prefix overlap с одинаковой историей, квотами и правилом раскрытия групп. Без них «NLP gain» может оказаться обычной персонализацией категории.

Для query в UTC-момент t берём только историю `[t−7d,t)`. Пример профиля: только view, один вклад каждого distinct product за окно, временем вклада служит последний view; вес `w_i=exp(−ln(2)*(t−last_view_i)/3d)`. Cart/purchase — отдельная последующая абляция, не автоматически усиленные веса. Метаданные исторического товара берём из последнего доступного view этого товара; метаданные кандидата — последнюю запись `<t`. Все peers на t исключены. Цена не текстовый токен; будущая price-aware сортировка потребует последней доступной цены, без full-month median.

## P1: конкретный lexical retrieval

Документ — доступные метаданные одного product_id. Category-поле содержит атомарные префиксы `cat:electronics`, `cat:electronics.smartphone`; brand-поле — атомарный `brand:samsung`. Пользовательский профиль каждого поля `q_f=L2(Σ_i w_i d_if)`, где `d_if` — L2-нормированный TF–IDF документа поля. Score группы `s=.5*q_cat·d_cat+.5*q_brand·d_brand`; отсутствующее поле даёт ноль, пустой общий профиль не выдаёт текстовых кандидатов. Если у пользователя имеется только один канал, его коэффициент равен 1. Это явное правило fusion; отсутствующее поле кандидата не компенсируем перенормировкой.

TF бинарный, `idf_f(z)=1+log((1+N_f)/(1+df_f(z)))`; `N_f` считает товары с непустым полем. Формула smoothing и L2-normalization документирована [scikit-learn](https://scikit-learn.org/stable/modules/feature_extraction.html#tfidf-term-weighting). Готовые namespace-токены передаются собственным analyzer; стандартный tokenizer не сохраняет нужные пути. OOV игнорируется с отдельной диагностикой, что соответствует [официальному API](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html).

IDF/vocabulary fit только на warmup `<t0`, где t0 — первый downstream prediction, затем freeze; новые известные товары добавляются с этим словарём. Альтернатива — опубликованные до query snapshots. Один product = один document, события не размножают DF. Можно сжать одинаковые документы вычислительно, сохраняя product-weighted DF. Fit по уникальным парам меняет статистический смысл редкости и требует отдельной абляции, а не скрытой оптимизации.

Пример бюджета: top20 непустых metadata-групп с положительным score, до10 товаров каждой, максимум200. Группа — пара code/brand, независимо от category_id. Сначала score DESC, затем стабильный канонический group key; внутри — distinct purchase-users в `[t−7d,t)` DESC, затем product_id ASC. Дедуп без добора. Нет оценок — пустой источник, fallback отдельно помечен как popular. Квоты и tie-break обязательны: тысячи товаров одной пары имеют идентичный lexical/dense score. Этот генератор измеряет совместный механизм «текстовая группа + популярность внутри», не чистое качество текстового encoder.

BM25 — дешёвый comparator тех же групп. Weighted score поля: `Σ_z a_z*log(1+(N−df_z+.5)/(df_z+.5))*tf_z*(k1+1)/(tf_z+k1*(1−b+b*L/avgL))`, где `a_z=Σ_i w_i*1[z∈doc_i]`, нормированное суммой весов. Это наша адаптация query weights; первичная теория — [Robertson–Zaragoza](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf), положительный IDF — [Lucene](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/BM25Similarity.html). При `tf=1,b=0` множитель равен1: остаётся weighted overlap; преимущество saturation здесь не обещаем. Сравнить только `b=0/.75,k1=1.2`.

## P2: dense и стоимость

Dense оправдан лишь проверкой переноса между разными именованными категориями. Отдельно encode читаемые category labels, brand сохранить identity-каналом. Профиль — нормированная сумма category vectors с теми же весами; cosine задаёт score групп, expansion неизменен. [SBERT](https://arxiv.org/abs/1908.10084) обосновывает sentence vectors с cosine; документация [Sentence Transformers](https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html) показывает прямой поиск. Это не доказательство purchase relevance коротких labels или корректного понимания брендов.

Материализовать as-of metadata→product postings, sparse vectors, IDF version, window counts и source ranks. При 384 float32 измерениях 5987 vectors занимают около9.2MB, а126 category vectors —0.19MB; копии на166794 товара —256MB. Это арифметика без encoder/index/служебной памяти, не benchmark. Exact group scoring достаточно исследовать первым; ANN и матрица всех пользователей×товаров не нужны.

## Проверка и решение

Одинаковые anchors, полный Y и universe обязательны. Измерить source Recall@200, дополнительное покрытие `|Y∩(C_text\C_base)|/|Y|`, overlap, фактический размер union, latency/memory и downstream topK. Отдельно сравнить равный общий бюджет с заменой существующей квоты, а не объявлять увеличенный union победой. Для ranker-feature абляции зафиксировать один C и менять только scores. Нулевые покупки сохранять по общей метрической политике, cold targets вне universe считать miss.

Пять обязательных случаев: пустая история; полностью missing/OOV текст; несколько IDs с одинаковым code; огромная группа с равными scores; смена brand и событие ровно t. Анализировать named/missing и новые user–item пары раздельно. HYP-085 можно зарезервировать для marginal lexical retrieval; HYP-086 — для dense transfer против identity/prefix контролей. Включать источник лишь при подтверждённом дополнительном покрытии за выбранный бюджет; иначе оставить текстовые scores как необязательные fixed-C признаки.


## Coordinator integration appendix — 15 октября 2026

Metadata latest global bucket<t включает все строки: known+NULL/conflicting ambiguous, all-NULL missing, без older-clean backoff. Historical distinct-product channel разрешает latest user-view bucket по той же ambiguity policy, не произвольную строку. Group lex score не различает items внутри одной code/brand пары; expansion purchase-popularity contribution нужно изолировать matched identity/prefix controls. HYP085 lexical retrieval needs-pilot отдельногоsourceprotocol,086 dense retrieval deferred до lexical residual/support/cost. Они не автоматически расширяют fixed-C textfeature003 budget. Totalcandidate quotas/refill/actualsize заранее versioned.


[Finalreview09–12](review-09-12.md): один brandtoken после L2TFIDF становитсяbrandonehot — IDFсокращается. Brandchannel — identityaffinity; lexicaltransfer085 должендаватьостаточныйcategoryprefixsignal сверхexactcode/brand с темижеhistory/decay/group-expansion/quotas. Сжатиеgroups сохраняетproductmultiplicities вDF/N. Dense086deferred, noNLPqualityclaimизmassiveties.
