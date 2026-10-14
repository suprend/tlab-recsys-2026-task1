# Текстовые эмбеддинги для T-Lab REES46

Проверено 2026-10-14 по первичным карточкам, конфигурациям и документации. Модели не скачивались и не запускались; рекомендации ниже — план эксперимента, без обещаний качества или измеренной скорости.

## Рекомендация

Для текущих коротких английских названий категорий начать с **`sentence-transformers/all-MiniLM-L6-v2`**; основной более ёмкий comparator — **`intfloat/multilingual-e5-base`**. Если хочется одного современного усиленного эксперимента, выбрать **`Qwen/Qwen3-Embedding-0.6B`**. BGE-M3 оставить альтернативой, EmbeddingGemma — резервом с дополнительными условиями доступа.

126 уникальных строк категорий не оправдывают обучение encoder или выбор модели на миллиарды параметров. Даже большой encoder здесь кодирует всего несколько сотен строк один раз; основной расход — построение признаков по 42 млн событий, а не inference текстов. Наличие 166 тыс. товаров не означает наличие 166 тыс. разных текстов: у товаров одной категории категория-эмбеддинг одинаковый.

## Shortlist

| Точная модель | Размер; выход; контекст | Язык / лицензия | Роль и корректный inference |
|---|---|---|---|
| [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | 22.7M; 384d; стандартный лимит 256 word pieces | English; Apache-2.0 | Самый простой baseline. `SentenceTransformer.encode(..., normalize_embeddings=True)`, без обязательного префикса. При Transformers вручную: masked mean pooling, затем L2 normalization. |
| [`intfloat/multilingual-e5-base`](https://huggingface.co/intfloat/multilingual-e5-base) | около 0.3B; 768d; 512 tokens | 100 языков; MIT | Основной comparator. Для категорий как признаков и симметричного сходства использовать **`query: ` для всех строк**, включая неанглийские. Masked mean pooling + L2. `query:` / `passage:` — для асимметричного retrieval, здесь его автоматически вводить не нужно. |
| [`Qwen/Qwen3-Embedding-0.6B`](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 0.6B; до 1024d, MRL 32–1024d; 32K tokens | 100+ языков; Apache-2.0 | Современный усиленный вариант. Официальный ручной путь: last non-padding token pooling + L2, left padding. `transformers>=4.51.0`. Для retrieval инструкции на query, документы без них; не считать историю покупок обычным поисковым query автоматически. |
| [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3) | около 0.6B; dense 1024d; 8192 tokens | Multilingual; MIT | Альтернатива E5/Qwen, если понадобится богатый текст. Префиксы-инструкции не обязательны. Dense: CLS pooling + L2; sparse и ColBERT для данного опыта не нужны. Не подменять CLS усреднением токенов. |
| [`google/embeddinggemma-300m`](https://huggingface.co/google/embeddinggemma-300m) | 300M; 768d, MRL 512/256/128d; 2048 tokens | 100+ языков; Gemma terms | Компактный современный резерв. HF требует принятия условий. Официальный Sentence Transformers путь сохраняет configured pooling/projection; `encode_query` / `encode_document` используют соответствующие prompts. **Activations float16 не поддерживаются**: FP32 или BF16. |

Дополнительные первичные проверки: [BGE-M3 pooling config](https://huggingface.co/BAAI/bge-m3/blob/main/1_Pooling/config.json), [BGE-M3 architecture config](https://huggingface.co/BAAI/bge-m3/blob/main/config.json), [E5 architecture config](https://huggingface.co/intfloat/multilingual-e5-base/raw/main/config.json), [Google EmbeddingGemma docs](https://ai.google.dev/gemma/docs/embeddinggemma).

Размеры ~0.3B/~0.6B округлены, не являются точным числом параметров. Огромный поддерживаемый контекст не нужен для taxonomy: ограничить фактический `max_seq_length`, например 64–128, после проверки токенизации всех строк.

## Префиксы и pooling: что зафиксировать

Для MiniLM и E5 рекомендации выше следуют их model cards. Для BGE-M3 используется CLS согласно опубликованной конфигурации. Для EmbeddingGemma нужно использовать полный официальный Sentence Transformers pipeline, а не произвольный mean pooling backbone: в этой проверке gated конфигурация pooling напрямую недоступна. Её model card задаёт document prompt `title: none | text: ...`, query prompt `task: search result | query: ...` и отдельные task prompts. Для симметричного сходства категорий заранее выбрать одинаковый подходящий task prompt для всех категорий и записать его, не смешивать query и document spaces без соответствующего эксперимента.

У Qwen можно проверить два заранее заданных режима: одинаковый plain-text document encoding всех категорий и одинаковая инструкция semantic similarity для всех. Это наши варианты протокола, а не гарантия производителя для taxonomy. Не выбирать prompt по финальному test. Официальные обещания MTEB не доказывают прироста в REES46.

## Аппаратные ограничения

Все пять моделей по размеру подходят для **frozen inference коротких строк** на предполагаемой RTX 3070 8 GB с небольшим batch; это оценка, запуск не проверен. Только веса FP32 ориентировочно занимают от 0.09 GB у MiniLM до 2.4 GB у Qwen0.6B; поверх нужны activations/runtime. Большой batch и максимальная длина контекста могут превысить память.

Для нескольких сотен категорий достаточно CPU на Mac, переход на Windows GPU не является предварительным условием. MPS можно проверить позже, не считать поддержку/скорость конкретного pipeline проверенной. Для EmbeddingGemma на RTX3070 безопасный первоначальный путь — FP32; BF16 проверять по фактической поддержке окружения, не предполагать её. Обучение/finetuning этих моделей в эту оценку не входит.

## Действительно полезный опыт для текущих данных

1. Сначала сильный boosting baseline с `category_id`, существующим `category_code`, уровнями taxonomy и причинными user-category affinities. Пример детерминированного представления: `electronics.smartphone` → `electronics / smartphone`. Сохранить исходный code и версию преобразования. Не генерировать описания отсутствующих товаров.
2. Посчитать embedding **каждой уникальной подтверждённой category string**, сохранить нормированные векторы и model revision. В main experiment не включать непроверенные соответствия из других месяцев. Неразрешённым категориям оставить отдельные `text_available`, `mapping_source`, `mapping_confidence`; пустой текст не должен притворяться содержательным названием.
3. Для каждого события-кандидата получить средний вектор категорий из истории пользователя **строго до timestamp кандидата**. Раздельно: views, carts, purchases; заранее выбранные временные окна. В boosting добавить cosine с историей, cosine с последней известной категорией, max/mean similarity с несколькими последними категориями. При пустой доступной истории использовать missing indicator; нулевая норма не должна вести к делению на ноль.
4. Сравнить одинаковые temporal splits: общий baseline из шага 1, уже включающий hierarchy → baseline + lexical similarity → baseline + MiniLM similarity features → baseline + E5. Только если остаётся время — Qwen0.6B. Сначала сравнивать компактные similarity features, а не загружать сотни сырых embedding coordinates в boosting без отдельного основания.
5. Для честной интерпретации сравнить с **same-dimensional random vectors per category string** и с one-hot category-string history cosine. Контроли назначать по тем же 126 подтверждённым текстовым кодам, что и семантические эмбеддинги, а не по 252 именованным category_id: иначе контроль различает ID, которые текстовое представление объединяет. Это проверяет, помогает ли именно семантика, а не ещё один способ кодировать ID/историю. Одинаковая маска наличия текста и один набор event windows во всех ветках. Дополнительно смотреть покрытие истории, редкие категории и холодные товары, но не выбирать победителя по случайному подмножеству.

Главная гипотеза: семантически близкая категория может переносить пользовательский интерес, когда точного совпадения с историей нет. Она может и не подтвердиться: короткая taxonomy часто уже выражается hierarchy/ID features, а близость “smartphone” к “smartphone accessories” не равна одинаковой склонности к покупке.

Названия из будущих месяцев следует хранить с provenance и временем наблюдения. Это отдельный режим внешнего catalog enrichment с явным допущением об исторической доступности; его нельзя незаметно назвать восстановлением из прошлого. Использование современных pretrained encoders на исторических событиях допустимо для ретроспективного исследования при явном описании этого протокола; не утверждать воспроизведение production-системы 2019 года.

## Текст + изображение

Если позже появятся **реальные изображения тех же product IDs с проверенной связью**, можно использовать text tower и image tower **одного checkpoint** CLIP/SigLIP. Например, [`openai/clip-vit-base-patch32`](https://huggingface.co/openai/clip-vit-base-patch32) выдаёт общее projected пространство 512d; text context 77 tokens подтверждён [config](https://huggingface.co/openai/clip-vit-base-patch32/blob/main/config.json), код под [MIT](https://github.com/openai/CLIP). Нормировать projected `encode_text` / `encode_image` outputs перед cosine. Категории в английском; конкретный text template фиксировать.

Нельзя считать cosine между независимыми MiniLM/E5 и DINO image vectors содержательным, даже при одинаковой размерности. Можно отдельно получить similarities внутри каждого пространства и объединить их как признаки. Сейчас изображений и товарных названий в данном CSV нет; найденная в интернете типовая картинка категории не становится картинкой конкретного анонимного товара.

Перекрёстное ревью: факты проверены независимым агентом по изображениям; уточнены общий baseline и одинаковая единица random/one-hot контролей.
