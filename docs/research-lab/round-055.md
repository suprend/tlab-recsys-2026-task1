# Round055 — purchase event не равен независимому завершённому заказу

**Primary-source semantics audit; no execution.** Проверены авторская REES46 dataset card и современная официальная integration documentation; локально прочитаны только published schema/target records. Никаких archives, data, query targets, metrics/models или jobs не открывалось. Конкретное unresolved assumption: можно ли трактовать registered purchase после anchor как новое независимое покупательское решение и завершённую коммерческую транзакцию? Для нашего logged-item target это не обязательное предположение, но оно ограничивает внешний смысл repeat/purchase predictability.

## Что говорит именно источник

[Каталог REES46](https://rees46.com/en/datasets) отделяет multi-category behavior events Oct2019–Apr2020 от отдельных transaction datasets. Поэтому нельзя переносить order semantics другого transaction export на выбранный marketplace event file. [Published data record](../data.md) фиксирует октябрьский источник и девять колонок, без order_id, quantity, order status или ingestion timestamp.

Индексированный текст [авторской Kaggle card](https://www.kaggle.com/mkechinov/ecommerce-behavior-data-from-multi-category-store/tasks) определяет row как product-user event, event_time какUTC, product_id как product identifier, user_id как permanent identifier, session как временный ID после длительной паузы. В разделе multiple purchases card буквально поясняет: “A session can have multiple purchase events. It's ok, because it's a single order.” Это авторское объяснение, но не проверенный functional dependency по actual file. Direct card response сейчас пустой; использован доступный индексированный текст primary page, не архивные строки.

В карточке есть редакционная несогласованность: одна schema строка говорит only purchase, тогда как Event types перечисляет view/cart/remove_from_cart/purchase. Это основание сверять конкретный downloaded version с собственным schema/action audit, не придумывать новые actions или автоматически включать remove_from_cart в frozen005. Размеры/частоты карточки не являются нашими измерениями.

[Текущая официальная purchase API](https://rees46.ru/help/integration/cdp/standard-events/purchase.html) принимает items с product ID, quantity, unit price, отдельно sid и уникальный order_id. Цена покупки может отличаться от feed price. [Текущая страница статусов](https://rees46.ru/help/integration/cdp/orders/statuses.html) различает оформленный, исполненный и отменённый заказ; исполненный означает оплаченный, доставленный, не возвращённый. Это первичные сведения о **нынешнем** product interface. Они не доказывают, что именно такая integration/schema/status synchronization действовала у анонимного магазина2019года или какие поля exporter отбросил.

## Неопределённость, специфичная для нашего target

Принятый `Y(u,t)` — distinct product IDs с зарегистрированным purchase в `[t,t+24h)`. По этому определению evaluator корректно считает hits и misses. Отсюда не следует, что каждый элементY — новый order, одна физическая единица товара или полученная выручка. Multiple-item order способен дать несколько positives, а повторные events одного product схлопываются только внутри target set. Raw historical counts сохраняют multiplicity по объявленному bag contract.

Предположим, уU purchaseI за секунду доT и ещё purchaseI через секунду послеT с тем же session. История содержитI, target содержитI, repeat prediction может быть верным. Но CSV без order/ingestion fields не показывает, был ли это новый checkout, повторная отправка tracking или часть прежнего процесса. Авторское объяснение multiple purchases дополнительно делает one-row-one-order interpretation необоснованным. Нет основания удалять такие rows как технические дубли: их происхождение тоже неизвестно.

Даже если принять session→single-order explanation целиком, успешно оплаченный/доставленный и позднее отменённый order могут оставлять одинаковые девять видимых event columns. Таким образом, terminal-success target не идентифицируется из этого projection. Это conceptual indistinguishability, не утверждение о доле отмен или дефекте REES46.

Аналогично product_id задаёт nominal key экспорта, но card не устанавливает глобальную SKU namespace между магазинами, variants либо отсутствие reuse IDs. Permanent user_id не удостоверяет одного физического человека и cross-device continuity. Эти границы важны при переносе repeat механизмов; они не мешают воспроизводимому join по принятым exact IDs внутри данного source version.

## Что законно проверить позднее

Из legal train/development event rows можно измерить **наблюдаемые burst/session patterns**, не настоящие orders: сколько session имеют несколько purchase timestamps/products, одинаковый product в близких timestamps, purchase rows по обе стороны заранее заданного daily anchor. Короткий lag между двумя event_time — inter-event lag; без recorded received_at он не оценивает ingestion delay. Длинная session не доказывает несколько orders, поскольку threshold sessionization и tracking semantics не установлены.

Такой будущий aggregate audit способен опровергнуть узкую рабочую эвристику «все purchase rows session лежат в одной секунде» или показать, что cross-anchor continuation заслуживает явно ограниченной интерпретации. Он не докажет независимость намерений, retry rate, paid-order rate или lifecycle статусы. Для этих вопросов требуются отсутствующие order/status/received-time provenance либо отдельная авторская export specification; добывать её или запрашивать данные здесь не предлагается.

Замена labels на reconstructed sessions, новая dedup policy, time-gap basket или revenue weights поменяли бы experiment. Поэтому future diagnostic не меняет current H/Q/C/fullY/duplicates/selector и не добавляет outcome slices к текущему model comparison. Никаких post-hoc исключений «неудобных» repeats или нового fit. Bounded train-only aggregate proposal конкретизируется в056 и требует отдельного source/resource разрешения.

## Формулировка final report и backlog

«Предсказываются distinct product IDs зарегистрированных purchase events следующего24h. Несколько events могут относиться к одному order/session; repeat hits отражают предсказуемость этого журнала и не интерпретируются как доказательство нового заказа, replenishment intent, оплаты или доставки. UTC event_time используется в declared offline availability simulation, фактическая delivery latency не измерена».

Это уточнение существующих target/provenance limitations, не новый quality mechanism или HYP. Единственное возможное backlog addition — deferred aggregate session/burst audit с preregistered interpretation limits. Он ниже приоритета accepted019/016 verification, воспроизводимого deliverable и readable report; полученный diagnostic не обещает quality improvement и не делает неизвестный бизнес-процесс известным.


## Dedup amendment после source-only056

Existing `scripts/eda.py` уже содержит general session span/cross-day/identity, purchase-without-view/cart и timestamp-bucket diagnostics; их actual outputs не читались. Поэтому первоначальный possible backlog addition следует сузить до deferred train-only purchase-specific fixed-anchor cross-boundary check056. Второй общий sessionEDA task не предлагается. Исходный055 finding и historical/current limits сохраняются.
