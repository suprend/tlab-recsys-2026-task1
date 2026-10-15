# Round074 — версия ID vocabulary: cold item, collision и перенос state

15 октября 2026. **Deferred embedding/user×item refinement**, без datasets, models, native API, SQL, tests, fits или иных jobs. Прочитаны [ARGUS](../argus.md), [sequential shortlist](../sequential-embeddings.md), [embedding protocol](../embedding-experiments.md), [learned-space study](../features/09-user-item/06-learned-space.md), rounds [022](round-022.md)/[057](round-057.md) и существующий backlog. Они уже требуют past-fit vocabulary, OOV/empty flags, согласованное пространство и global read-before-update. Конкретное дополнение: версия **ID→index binding** должна связывать обе башни и cached user state; shared dimensionality и неизменная форма tensor этого не доказывают. Нынешние016 программы/weights/candidates/budget не меняются; новой quality HYP не предложено.

## Что можно знать об ID до обучения

REES46 branch рассматривается как ID-only behavior с доступными event metadata, без придуманных titles/images; наличие category/brand не делает разные товары индивидуально описанными. Различаем четыре договора, не четыре разрешённых сейчас эксперимента:

| Vocabulary policy | Допустимый смысл | Обязательство/ограничение |
|---|---|---|
| Train-only learned vocabulary | ID/support/frequencies из разрешённого fit prefix | Новые позже наблюдаемые товары могут быть вне fit vocabulary; history всё равно может содержать их |
| Catalogue-known mapping | Внешний перечень ID действительно доступен до cutoff | Нужны provenance/availability перечня; наблюдавшийся event catalogue proxy не равен stock catalogue |
| Preallocated full-month vocabulary | Transductive знание будущего ID domain | Раскрыть источник/момент знания, влияние на indexing, negatives, initialization; не выдавать за past-observed vocabulary |
| Fixed feature hashing | Определённая заранее функция над любым допустимым ID | Зафиксировать serialization, namespace, bins/salt/mask; collisions разделяют параметры |

Знание уникального будущего ID **само по себе не доказывает знание предпочтения**: заранее выделенный неиспользованный слот не равен embedding, обученному на будущих покупках. Но extracting vocabulary из всего event файла уже использует информацию будущего domain; frequency-based adaptation дополнительно читает будущие частоты. Такую процедуру нельзя автоматически объявить соответствующей нынешнему strict-past fitted-component contract.

## Primary API findings

Официальный [StringLookup](https://www.tensorflow.org/api_docs/python/tf/keras/layers/StringLookup) описывает vocabulary, обучаемый `adapt()` по частотам; capped vocabulary оставляет наиболее частые tokens, остальные OOV. Порядок зависит от частот и tie ordering. Несколько OOV indices распределяют неизвестные tokens по buckets. Наш вывод: повторный `adapt()` не является обещанием append-only indexing. Даже неизменная cardinality не защищает от перестановки старых ID; отдельная OOV строка и padding/mask имеют разный смысл.

В оригинальном [SASRec util.py](https://raw.githubusercontent.com/kang205/SASRec/master/util.py) `itemnum/usernum` вычисляются по всему предоставленному sequence file до per-user leave-last-two partition. [Sampler](https://raw.githubusercontent.com/kang205/SASRec/master/sampler.py) выбирает negative из `1..itemnum`, исключая train-item set; [model.py](https://raw.githubusercontent.com/kang205/SASRec/master/model.py) использует общую item table для history и scoring,0 — padding. Просмотрен public master, immutable commit не установлен. Это иной benchmark contract, не библиотечная ошибка. При переносе future-only ID способен изменить negative universe, хотя его interaction не вошёл в train positives; causal attention не защищает sampler или vocabulary lifecycle.

[Keras3.3.3 Hashing source](https://raw.githubusercontent.com/keras-team/keras/v3.3.3/keras/src/layers/preprocessing/hashing.py) фиксирует bins, FarmHash64 либо SipHash64 с salt, отдельную mask политику и преобразование числовых входов в строки. Hash lookup не требует learned vocabulary, но embedding bucket обучается по взаимодействиям. Collision с warm item не превращает cold raw ID в fit-supported item. Exact BIGINT serialization необходима до hashing: ранее округлённый float не восстанавливает исходный ID. User/item namespaces должны быть раздельными, если shared bucket semantics не была намеренно утверждена.

[Weinberger et al., Feature Hashing v5, §§2–3](https://arxiv.org/html/0902.2206v5) анализируют signed hashed feature maps и inner-product distortion при своих условиях. Эти bounds нельзя объявлять гарантией качества learned unsigned embedding lookup, отсутствия collisions или purchase-ranking gain. Hashing даёт возможность детерминированной ограниченной адресации, а не доказанную рекомендационную совместимость.

## Буквальный future-only witness: четырнадцать строк

Два source events до fit cutoff F: A/view/20 и B/view/30. Query `(A,T)` при T>available_at≥F, C={20,30}; история A содержит только20. Suffix добавляет C/view/10 в T+1h. Это3 event rows,1Q,2C. Две явно заданные mapping tables: V1={20→1,30→2}, V2={10→1,20→2,30→3}, всего5 binding rows. Ещё3 toy weight rows: e1=(1,0), e2=(0,1), e3=(2,0); суммарно14 literal rows. Векторы заданы вручную, ничего не обучалось.

С V1 cached h_A=e1 даёт dot(20)=1, dot(30)=0. Если candidate tower молча переключить на V2, сохранив старые weights/cache, получим0 и2: ranking переворачивается после добавления future-only ID. Это counterexample несогласованного binding, не утверждение, что Keras автоматически выполняет такое переключение. Один frozen V1/OOV contract сохраняет прежний результат; новый approved V2 требует согласованного переноса weight rows и пересоздания либо доказанно корректной миграции state. При training resume туда же относятся optimizer moments.

## Единственный полезный будущий gate

Уже deferred learned-space/embedding protocol достаточно; новый task не требуется. Source-free0-fit conformance после отдельного разрешения должен отвергать mismatch `(θ, vocabulary/hash config, history-state version, candidate table)`, сохранять frozen past scores при future suffix, отличать padding/empty/OOV/zero-support и не считать bucket support поддержкой raw ID. Negative universe/draw law тоже фиксируются: изменившийся full-file maximum обязан либо не влиять на frozen sampler, либо означать новую identity и иной эксперимент. Global peers прогнозируются до allocation/update по bucket; новый unknown ID не становится событием от самого scoring C.

После F past history может законно расти; suffix invariance относится к прежнему T при неизменных fitted dependencies, не к запрету новым событиям менять более поздние representations. Hash collision допустима только как declared representation, не как повод склеить full-Y item identities или counts. Такой gate докажет lifecycle mechanics; качество, CPU/GPU feasibility и переносимость на новые товары останутся неизвестны. Cache rebuild/migration и failed attempts оплачиваются будущим отдельным протоколом; нынешние016 fits/looks и закрытый heldout для этого не используются.


## Publication scope appendix — 15 October 2026

Original note SHA256 7342fbc1da820c47c3d8adad926ccba146433b174cc69f3a1af5a8d11c995919. This retained research snapshot predates the locally accepted actual016 model evidence in the current [progress report](../progress-report.md). Its future tense is historical scope, not the current canonical execution status. No new hypothesis execution, resource grant, fit, source download or reserved-target access is authorized by publication. Current accepted development winner is R2; this does not establish guided-strategy superiority or heldout improvement.
