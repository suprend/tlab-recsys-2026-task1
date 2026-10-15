# Round056 — historical provenance gate и train-only burst diagnostic

**Продолжение055, не новая гипотеза.** Здесь конкретизируется только возможная проверка unresolved order/session interpretation. Primary источники: [publisher datasets index](https://rees46.com/en/datasets), [авторская card](https://www.kaggle.com/mkechinov/ecommerce-behavior-data-from-multi-category-store/tasks), [современная purchase API](https://rees46.ru/help/integration/cdp/standard-events/purchase.html), [современные order statuses](https://rees46.ru/help/integration/cdp/orders/statuses.html). No data/targets/models/SQL/tests/fits; источник055 не переписывается.

## Exact historical/current граница

| Evidence | Что разрешено заключить | Что не установлено |
|---|---|---|
| Indexed publisher card2019–2020 source | Product-user events, UTC event_time, временный session, объяснение multiple purchase rows одним order | Гарантия one-session-one-order для каждой строки конкретного файла, paid/fulfilled status |
| Accepted header девятиколоночного октября | В этом export нет order_id/quantity/received_at/status | Что исходная система никогда не собирала эти поля |
| Current REES46 API | Session/order/product quantity — разные нынешние fields | Historical tracking version, exporter projection, timestamp/dedup/status mapping2019 |
| Current status documentation | Заказ может быть оформлен/исполнен/отменён | Какие purchase rows выбранного журнала соответствуют каждому состоянию |
| Сходные события близко по event_time | Наблюдаемая временная co-occurrence | Ingestion latency, один реальный order, retry или независимое намерение |

Current API docs прочитаны как current source, без ретроспективного version claim. Card доступна через индексированный primary text; direct response пустой. Не проводились archive/Wayback поиски и скачивания. Поэтому historical integration неизвестна, а не «совпадает с нынешней». Отсутствие поля в projection не разрешает заполнить его эвристикой и объявить observed fact.

## Что уже покрыто, не добавлять повторно

Read-only просмотр [accepted EDA source](../../scripts/eda.py) показал существующие session span/cross-day, session-to-user identity, purchase-without-cart/view, timestamp ties и timestamp-bucket transitions. Их actual output здесь не читался. Не нужен второй общий session audit или whole-month scan ради research note. Новый узкий вопрос только один: насколько purchase co-occurrence пересекает именно **фиксированный prediction anchor** внутри разрешённого train range? Он помогает описанию logged repeat evidence, но не устанавливает order truth.

## Prospective bounded protocol — только при отдельном разрешении

Вход: existing accepted trainQ, exact pinned source version и train-access cutoff; никаких selection/confirmation/final query-level targets или моделей. Выбрать до100Q на каждом из уже существующих train anchors по заранее объявленному bottom hash, до чтения purchase diagnostics. Это diagnostic sample, не новая train/eval population. Все reads, source hashing, oracle/readback и failures должны входить в отдельно разрешённый resource ledger; здесь allowance отсутствует.

Для каждого q=(u,t) рассмотреть только purchase rows пользователя в `[t−1h,t+1h)`, причём весь диапазон обязан лежать в разрешённом train observation domain. Если range пересекает закрытый cutoff, отказаться от case, а не читать дальше и не выдавать усечённый результат как полный. Timestamp predicates и sampling заранее неизменны; bins не подбираются по увиденным counts.

Для non-null session s определить:

`cross(q,s)=1[∃purchase(u,s,τ), t−1h≤τ<t]·1[∃purchase(u,s,σ), t≤σ<t+1h]`.

Отдельный same-product indicator требует существования **одного**i по обе стороны. Это два объявленных source diagnostics, не две model quality hypotheses. Raw rows сохраняют exact duplicates; distinct products/timestamps считаются отдельно. Нельзя выводить event order внутри одной секунды.

Public aggregate evidence: число sampledQ и covered windows; raw purchase rows, distinct products/timestamps; Q сcross-session иsame-product-cross; purchase rows сNULL session. Denominators — все sampled coveredQ и отдельно cases сполностью известным session scope. ПриNULL session отсутствие найденного cross не доказывает отсутствия continuation. Row/user/session IDs не публикуются. Не считать source coverage равной exposure, а lag — delivery delay.

## Tiny specification перед реальным diagnostic

Literal example без исполнения: `(U,I,s,T−1s)`, `(U,J,s,T+1s)`, две одинаковые `(U,I,s,T+2s)` и `(U,I,NULL,T+3s)`. Expected: cross дляs=true; same-product-cross=true; четыре postanchor raw rows, дваdistinct postanchor products, двеизвестные postanchor секунды плюс однаNULL-session секунды; отсутствующий session отмечается отдельно. Это пять input rows, не оценка REES46. Golden boundaryT−1h включена, T принадлежит postanchor portion, T+1h исключена; добавлениеfuture suffix внеразрешённогоrange ничего не меняет.

Такой test обнаруживает wrong predicates, dedup/rawcount mix иNULL→knownfalse. Он не способен отличить повторную отправку одного checkout от новой покупки. Даже идеальное совпадение expected table не делает session surrogate настоящим order_id.

## Decision record для backlog

Немедленное полезное действие — точная final-report wording055 и historical/current provenance disclosure. Diagnostic — deferred, только если интерпретация repeat mechanism станет существенным отдельным вопросом после текущего task1 deliverable. При нулевых cross counts на bounded sample нельзя заявить глобальное отсутствие burst effects; при ненулевых нельзя переписать targets/dedup/eligibility или исключить rows послеmodelcomparison. Current frozen policy продолжает предсказывать зарегистрированный distinct item set; успех и независимость коммерческих orders остаются unknown. Нового HYP, quality family или execution authorization не требуется.
