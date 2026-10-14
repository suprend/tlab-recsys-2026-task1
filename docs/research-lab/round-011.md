# Round011: граница переносимой typed feature automation

15 октября 2026. **Статус: primary-source synthesis и предложение, без реализации, сканов, скачивания datasets или fits.** Прочитаны [004](round-004.md), [008](round-008.md), [009](round-009.md) и [backlog](../backlog.md). Здесь уточняется calculation seam HYP002/046: какие программы разрешает схема и какие семантические обязательства должен утвердить человек. HYP107/108 остаются reserved: нового механизма улучшения качества не сформулировано. Frozen005/008/009/017/018 не изменяются.

## Что действительно выводится из схемы

**Факт.** Woodwork различает physical type, logical type и semantic tags; автоматическое определение logical type допускает ручное исправление. Integer получает `numeric`, однако объявленный primary index теряет стандартные теги своего типа. Поэтому утверждение «любой числовой ID автоматически усредняется» неверно. Имя столбца или Integer без объявления роли ещё не доказывает, что перед нами измеряемая величина. [Woodwork: types/tags](https://woodwork.alteryx.com/en/stable/guides/logical_types_and_semantic_tags.html).

**Факт.** В Featuretools числовой foreign key может сохранять `numeric`, но DFS отдельно исключает комбинацию `foreign_key`+`numeric` из подбора операндов. При этом ключи используются для группировки. Защита относится к корректно объявленным отношениям; нераспознанный integer ID остаётся риском. Сам Mean требует numeric, не проверяет валюту, физическую единицу или экономический смысл. Это видно в [DFS v1.31.0](https://github.com/alteryx/featuretools/blob/v1.31.0/featuretools/synthesis/deep_feature_synthesis.py#L959-L971) и [Mean](https://github.com/alteryx/featuretools/blob/v1.31.0/featuretools/primitives/standard/aggregation/mean.py#L24-L26).

**Факт.** OneBM классифицирует результат joining path как scalar, multiset, sequence или time series; cutoff-колонку необходимо указать явно. Авторы также описывают ручное исправление `ad_id`: parser первоначально считал его numerical, затем categorical. Это конкретное свидетельство полезности аннотации, а не доказательство семантической автономности. Label-distribution преобразования из той статьи не получают автоматически разрешение в нашем strict-past протоколе. [OneBM, III-A и V-D](https://arxiv.org/html/1706.00327v1).

**Факт.** RelBench задаёт PK/FK, timestamps и task-table с entity, seed time, label; проектировщик задачи отвечает за предотвращение time leakage. OpenFE обучаемо оценивает кандидатов через FeatureBoost и pruning: наличие numerical/categorical полей не делает отбор label-free. Его grouped transformations требуют отдельного temporal применения в нашем протоколе. [RelBench, §2](https://cs.stanford.edu/people/jure/pubs/relbench-neurips24.pdf), [OpenFE](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf).

## Минимальный adapter contract — предложение

Механически проверенная связь даёт допустимый путь вычисления; бизнес-контракт определяет смысл результата. Не нужен новый универсальный framework: достаточно versioned manifest и capability gate перед существующим AST.

| Из схемы можно проверить | Человек утверждает | Разрешение calculation seam |
|---|---|---|
| Уникальность PK, FK membership, cardinality | Entity scope, стабильность ID, допустимые orphan/null | Join/groupby; арифметика ID запрещена |
| Integer/decimal/category и nullability | Measure/unit: event, invoice, quantity, currency; multiplicity | Count/distinct/sum/mean только по разрешённому grain |
| Timestamp format/resolution | Event, available, valid-from/to; clock и endpoints | Явный as-of predicate, никаких угаданных ролей |
| Наличие action/category полей | Vocabulary, label role, историческая metadata policy | Whitelist событий и conditional operators |
| Заявленный source interval | Что наблюдается, пропуски, downtime/exposure | Coverage отдельно от age и missing |

FK cardinality проверяется на входе, а не считается истинной по одному названию. Invoice-line count, distinct invoice и sum quantity — различные результаты. One-to-many join не должен размножать сумму исходных строк; adapter либо агрегирует на утверждённом grain, либо отклоняет программу. `count_distinct(group_key)` может быть допустимым индикатором, хотя часто дублирует support; это не тот же дефект, что `mean(product_id)`.

Контракт дополнительно фиксирует row- и field-level availability, null/unknown policy, source/version provenance и утверждённую интерпретацию отсутствующих capabilities. `unsupported view` нельзя превращать в zero views; unknown action требует QA-политики. Поле label запрещено как обычный predictor; использование прошлых labels требует отдельной декларации зрелости, availability и fit cutoff. Semantic tag служит входом валидатора, но не удостоверяет правдивость самой аннотации.

## Время и наблюдаемость нельзя угадывать

**Факт.** Featuretools secondary time index маскирует перечисленные поля, пока дополнительное время не наступило. В проверенном коде primary cutoff зависит от `include_cutoff_time`, а secondary mask использует `>= cutoff`. Следовательно, одинаковый endpoint нельзя предполагать для обоих путей: boundary нужен в тесте. Маскирование значений само по себе не восстанавливает старые версии исправленного поля. [Time handling](https://docs.featuretools.com/en/stable/getting_started/handling_time.html), [EntitySet v1.31.0](https://github.com/alteryx/featuretools/blob/v1.31.0/featuretools/entityset/entityset.py#L1277-L1325).

**Предложение.** Для event history сохранить `[t−W,t)` и отдельно утвердить доступность строки/поля; для synthetic проверки ниже выбрать строго `available_at<t`. Неизвестная availability отклоняется либо даёт explicitly unknown, без подстановки event time. Для metadata нужны одновременно validity и knowledge: `valid_from≤t<valid_to` и известность до query. Fitted components сохраняют принятый собственный контракт `fit_cutoff≤available_at≤first_query`; это другой endpoint, его не менять ради единообразия.

При наблюдаемом интервале `[s,e)` source coverage равен `length([t−W,t)∩[s,e))/W`, если объявлена непрерывность наблюдения. First observed user event определяет observed age, а не registration или exposure. Пользователь, впервые замеченный час назад в полностью наблюдаемом месяце, имеет месячный coverage=1 и age=1h; возраст не обнуляет coverage. Downtime требует множества наблюдаемых интервалов, а не заполнения промежутков.

RetailRocket publisher описывает weekly property snapshots, сжатые в changelog. Это отличается от принятой REES46 event-embedded metadata policy: latest global past bucket, mixed NULL ambiguity, без older backoff. Перенос carry-forward между этими схемами меняет смысл состояния. Snapshot timestamp не доказывает ingestion time, а `available` не означает наблюдавшийся показ товара. [RetailRocket publisher](https://www.kaggle.com/retailrocket/ecommerce-dataset/home), [текущий manual contract](../experiments/manual-features.md). Отсутствующие времена знания остаются явным offline assumption, не online replay guarantee.

## Один prospective zero-fit эксперимент

**Не выполнен и не разрешён автоматически.** Два synthetic adapter manifests: A — event-embedded schema с numeric IDs; B — переименованные строковые IDs и отдельные versioned metadata. Максимум24 events,8 metadata versions,6 queries,12 candidate pairs. Общие заранее заданные программы: count views24h, distinct viewed items24h, pair observed recency. Metadata category с missing flag проверяется как отдельная adapter capability; это не заявление о расширении grammar005/009 или verifier018. Совпадение значений требуется у общих event-программ после bijective rename; metadata имеет отдельные ожидаемые ответы по своему контракту.

Обязательные hand-computed случаи: field valid с часа6, available с9 — в8 unknown, в9 всё ещё unknown при strict knowledge endpoint, в10 known. Другая версия available9, valid12 не применяется в10. Поздняя correction не переписывает query8. Future suffix и перестановка peers сохраняют past features. Повтор event увеличивает count, но не distinct; join fanout, среднее ID, неопределённая availability и unsupported action/program отклоняются. Отдельно проверяются monthly coverage против new-user age и отсутствующая metadata в последнем bucket без старого backoff.

Приёмка correctness: точные keys/types/counts/null/flags и ноль расхождений с независимыми ожидаемыми таблицами; никаких label-driven фильтров или quality claims. Предлагаемый общий cap — wall≤5минут, CPU≤5минут,2threads,RSS≤512MiB,0fits, с cleanup/resource failure→failed evidence. Он входит в будущий согласованный ledger, не прибавляется к действующим бюджетам. Capability failure сохраняет причину и не запускает fallback автоматически.

Результат может подтвердить переносимость ограниченных вычислений, но не полноту логирования, полезность новых features или ускорение. Для Task1 остаётся последовательность: approved contract→capability whitelist→typed AST→closure→keyed calculation→independent oracle. Quality всё ещё требует сильного tuned B, frozen chronology и общего бюджета. Semantic-free automation, averages of IDs и подмена event time временем доступности отвергаются; новые HYP107/108 пока не нужны.
