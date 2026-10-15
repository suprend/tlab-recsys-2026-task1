# Research lab, round021: schema-only Online Retail adapter drill

15 октября 2026. Это узкое предложение conformance проверки, уточняющее [004](round-004.md), [011](round-011.md), [013](round-013.md), [015](round-015.md) и [016](round-016.md). Прочитаны actual [registry005](../../configs/features/manual-18.json) и [validator/compiler](../../scripts/manual_features.py). Данные не получены и не исследованы; code, Root/C11 artifacts и approvals не менялись. Ошибочно включённый в source lookup ZIP URL инструмент отклонил по размеру; ни файл, ни его data content не получены, повторного запроса не было. Ни dataset schema implementation, ни pilot, fits, downloads на диск или тестовые исполнения не выполнены.

## Первичные сведения и неизвестное

[Официальный UCI record](https://archive.ics.uci.edu/dataset/352/online%2Bretail) описывает transactional dataset: InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country. Invoice prefix `c` обозначает cancellation; Quantity — количество товара в transaction, UnitPrice — sterling за единицу; CustomerID/StockCode/InvoiceNo номинальны. InvoiceDate — время генерации transaction. Карточка утверждает отсутствие missing values; без файла это **не подтверждение полноты**. Точные доли NULL/duplicates/служебных кодов здесь неизвестны. Views/cart/impressions, availability timestamp, timezone и item taxonomy в описании не заданы; их нельзя восстановить из названий колонок.

UCI указывает CC BY4.0; [текст условий CC](https://creativecommons.org/licenses/by/4.0/) требует attribution, ссылку на license и указание изменений. Лицензия не подтверждает temporal observability. [Introductory Chen–Sain–Guo paper, publisher preview](https://link.springer.com/article/10.1057/dbm.2012.17) подтверждает RFM segmentation с clustering/decision trees, но доступный abstract не описывает проверяемое matching returns или online availability. Полный текст здесь недоступен; чужие notebooks не заменяют его и не дают оснований объявить отрицательную Quantity всегда однозначно привязанным возвратом.

## Contract до исполнения

Предлагаемый adapter объявляет grain=`invoice_line_bag`, строковые nominal keys, units и action predicate. InvoiceNo идентифицирует transaction, не отдельную строку; `(InvoiceNo,StockCode)` не доказанный PK. Exact duplicate lines сохраняются до явной dedup policy; synthetic record ordinal годится для provenance, не как invented event ordering. Quantity2 означает одну строку с двумя единицами, не два purchase events. CustomerNULL не объединяется в synthetic user: attributable user/pair queries требуют ключа, item-level line counts могут сохранять такие строки.

Для fixture ниже **предлагается**, а не выводится из UCI: purchase-line = не-cancellation invoice с Quantity>0 и finite positive UnitPrice. Cancellation сохраняется в audit relation, не превращается в purchase и не вычитается задним числом из прошлой продажи. Zero/negative quantity, conflicting prefix/sign, missing keys и invalid prices требуют отдельных policy outcomes; нельзя незаметно отфильтровать всё неудобное как dirty data. Отсутствует надёжная связь original-sale↔return: ни совпадение суммы, ни удаление буквыC её не доказывают. Signed net quantity/revenue — отдельный контракт и новые operators.

Без timezone literal InvoiceDate остаётся source-local clock; actual005 UTC protocol нельзя назвать выполненным. Для synthetic test время явно UTC, для будущего файла timezone/ambiguity policy должна быть отдельно утверждена либо temporal adapter отклонён. Нет available_at: допустима лишь помеченная offline event-time assumption, не доказанный deployment replay. Source start/end — границы наблюдаемого файла, не гарантии uptime/полноты каждого окна; first purchase age не account age, отсутствие покупки не отсутствие exposure. Description/UnitPrice transaction-line observations не доказывают historical catalog, stock или текущую offer price.

## Capability matrix против actual005

| Программа | Статус для invoice schema |
|---|---|
| Frozen `user_purchase_7d`, `pair_purchase_7d`, `pair_purchase_recency_seconds`, `item_purchase_24h` | Механически выразимы после purchase-line/time/key annotations; unit=count lines, не invoices/units |
| Остальные14 manual18, зависящие от view/cart/category | Unsupported; view/cart нельзя подменять observed0, Country/Description не category |
| Purchase distinct products/users | Синтаксис count_distinct005 допускает product/user; это новые registry definitions, вне frozen manual18 и принятого018 scope |
| Distinct InvoiceNo, sum Quantity, Quantity×UnitPrice, net returns | Неподдерживаемые005 column/operators; не скрытый alias count |
| Category shares/price/stock/exposure | Нужных semantic domains нет; запрет вместо выдуманной metadata |

Actual validator принимает1–64 features и action vocabulary view/cart/purchase, но не знает capability исходного источника. Поэтому он сам не отвергнет view AST на purchase-only events: SQL может вернуть ложные0. Будущий capability gate обязан работать **до** materialization. Новый adapter/registry не получает автоматически acceptance существующего CLI и source verifier018. Ключи сохраняют nominal role; требуемый downstream BIGINT mapping требует отдельного exact bijection/provenance, без float inference и усреднения IDs.

## Один будущий synthetic drill: literal tables

Только после отдельного approval: ≤32 synthetic input rows суммарно,0 fits. Базовый input содержит8 raw lines,2 Q и5 C; T=`2011-01-08T00:00:00Z`. Все prices положительны; invoice C1 объявлен cancellation.

| Invoice | User | Item | Time | Quantity | UnitPrice |
|---|---|---|---|---:|---:|
| I1 | U | X | T−2h | 2 | 3 |
| I1 | U | X | T−2h | 2 | 3 |
| I1 | U | Y | T−2h | 1 | 5 |
| C1 | U | X | T−1h | −1 | 3 |
| I2 | NULL | X | T−3h | 1 | 3 |
| I3 | V | X | T−24h | 1 | 3 |
| I4 | U | X | T | 1 | 3 |
| I5 | U | Z | T−8d | 1 | 3 |

Q={U@T,V@T}; C и **literal expected values** следуют ниже. Count windows включают нижнюю границу и исключают T глобально; recency использует полный observed prefix.

| (User,Item) | user_purchase7d | pair_purchase7d | pair_recency_seconds | item_purchase24h |
|---|---:|---:|---:|---:|
| U,X | 3 | 2 | 7200 | 4 |
| U,Y | 3 | 1 | 7200 | 1 |
| U,Z | 3 | 0 | 691200 | 0 |
| V,X | 1 | 1 | 86400 | 4 |
| V,Y | 1 | 0 | NULL | 1 |

Вторая X строка меняет raw counts, не distinct identity; NULL-customer line увеличивает item X, не userU. U7d содержит3 lines, один invoice и5 units — это разные expected величины, последние две не выдаются за005 features. Cancellation и peerT не участвуют. Known pair V,Y даёт count0/recencyNULL; unsupported view не даёт0 вообще.

Оставшиеся synthetic rows резервируются для empty-C mature query retention, zero-Y query, null-user rejection, conflicting cancellation sign, unknown timezone и fractional/overflow IDs; ожидаются явные compile/policy failures, а не imputation. Добавление future suffix/peer permutation сохраняет прошлые F, rename keys сохраняет keyed features при fixed Q/C; sampling SHA/ranking ties не обязаны сохраняться. Literal schema/types/NULL и все expected rows проверяются отдельно от metamorphic consistency. Этот drill может доказать только adapter mechanics и fail-closed capabilities на fixture, не predictive или cross-dataset generalization. Новый budget, mandatory pilot или quality family не предложены; HYP127/128 остаются reserved refinements typed proof/generalization.
