# Research lab, round036: Retailrocket — отдельный metadata/availability contract

15 октября2026. **Schema-only prospective adapter drill**, уточняющий [004](round-004.md)/[011](round-011.md) и противопоставленный [031Taobao](round-031.md)/[021UCI](round-021.md). Архивы/CSV/binaries/download endpoints не открывались, network data files не запрашивались. Source quality, SQL/tests/Pool/fits не проверялись; Root/code/approvals/budgets не изменены.

## Publisher facts и пределы доступа

[Официальная Retailrocket Kaggle card](https://www.kaggle.com/retailrocket/ecommerce-dataset/home) доступна через индексированный текст того же publisher URL; прямое открытие возвращает пустое представление. Издатель описывает три логические relation: events `(timestamp,visitorid,event,itemid,transactionid)`, timestamped properties `(timestamp,itemid,property,value)` и category tree child/parent. Actions: `view/addtocart/transaction`. Заявлены4.5месяца,2756101events/1407580visitors,20275902property rows/417053items,1669tree rows; version2 показана987.5MB. Это **card claims**, не наши counts/byte measurements.

Properties — weekly snapshots, сжатые удалением последовательных неизменных значений. Явно раскрыты `categoryid` и `available`(1/0); другие свойства анонимизированы, numeric values помечены `n` с тремя decimal digits, text words stemmed/hashed. Это не читаемые titles. Unix example1439694000000 согласуется с milliseconds: unit inference из примера, не найденная отдельная formal unit guarantee. Точные календарные endpoints/ingestion delay не установлены.

Card указывает **CC BY-NC-SA 4.0**. [Официальные условия CC](https://creativecommons.org/licenses/by-nc-sa/4.0/) требуют attribution/указания изменений, noncommercial use и ShareAlike при распространении адаптаций. Сведения не заменяют проверку применимых условий перед будущим использованием. Текущая возможность download без login/account не проверялась; size card не считается compressed archive size или memory estimate. Данные не получены.

## Минимальный event contract

Предлагаемый mapping: visitorid→nominal user key, itemid→nominal product key; `view→view`, `addtocart→cart`, `transaction→purchase`. Visitor не доказанный person/login; transactionid не eventID и не разрешение collapse всех одинаковых строк. Purchase core005 считает raw transaction-event rows, fullY — distinct purchased items; ни то ни другое не число заказов/единиц. Все точные raw duplicates сохраняются. Noninteger/NULL/unknown keys/actions требуют explicit validation policy, не guessed conversion.

Clock adapter должен закрепить epoch units и UTC conversion без local-time guess; schema-only milliseconds assumption остаётся pending primary/adapter review. История `[max(S,t−W),t)`, recency `[S,t)`; peers ровноt исключены глобально. Source completeness/наблюдаемые интервалы объявляются отдельно: min/max events не доказывают coverage, наблюдаемый user age не exposure. Q eligibility/hash selection толькоpast, доtargets; target `[t,t+H)`/maturity и календарь — новый protocol, не копия REES46 dates.

## Отдельные часы properties: главный compatibility seam

**Предлагаемая semantics:** последнее известное значение каждого `(item,property)` определяется отдельно по strict-past snapshot timestamps. Внутри latest property timestamp bucket одинаковые duplicates не конфликтуют, разные значения или known+NULL→unknown; older backoff запрещён. Отсутствие нового snapshot для constant property не означает deletion. Carry-forward относится к последнему **наблюдённому** snapshot, не утверждает непрерывно верное stock/category между недельными наблюдениями.

Snapshot timestamp не доказывает available_at. Возможны поздняя доставка/выгрузка и изменения между snapshots; event-time-as-availability допускается только как явная offline assumption. Первая найденная позже category не backfills earlier events. Для исторического event category нужен property state, доступный строго перед event; для candidate current category — state передquery. Один final dictionary из всей property relation нарушает обе границы. Actual2026 audit/sealing clock отдельно от simulated source timeline; файлы не обязаны были физически существовать в2015.

Frozen [005](../../scripts/manual_features.py) разрешает currentcategory из последнего глобального **event** bucket. Простого enrichment каждого event недостаточно: category может измениться после последнего event товара, доquery. Добавлять property rows как fake views нельзя. Поэтому полный manual18 не объявляется drop-in portable. Возможны только явно изменённая last-observed-event semantics либо separately reviewed property resolver/adapter; ни один вариант здесь не реализуется и не расширяет vocabulary.

Category tree — nominal IDs/parent relations, не readable category codes. Историческая доступность taxonomy edges неизвестна. Ancestor expansion — отдельная membership relation, не raw-event join: иначе один view становится несколькимиcounts. Нельзя из tree IDs угадывать названия/порядок/brand. `available=1` при прошлом snapshot не доказывает stock сейчас, показ или eligibility покупки; metadata-only item не автоматически включается в prior-event catalog.

## Capability matrix: что переносится и что меняется

| Схема | Existing005/016 после явного adapter contract | Непереносимая часть без нового review |
|---|---|---|
| REES46 current contract |18cores, event-embedded historical category/latest global event bucket;016noncategory vocabulary | Observed catalog уже proxy, не stock; no title assumption |
| Retailrocket |12noncategory manual18cores иL01–08 count/distinct/recency definitions |6category cores/current context требуют property-as-of seam; fullB41 parity пока не доказана |
| Taobao031 |Пятиколоночный consumer; action mapping покаproposal, terms/clock unknown | Нет подтверждённого property changelog/price/brand/code; fav domain отдельно |
| UCI invoice-only |Purchase-row count/distinct/recency после return contract |Views/cart unsupported, все нынешние016wholebundles не открываются автоматически |

[UCI publisher](https://archive.ics.uci.edu/dataset/352/online%2Bretail) явно описывает invoice lines/Quantity/UnitPrice/Description; такой подтверждённый UnitPrice принципиально отличается от неизвестного numeric property code Retailrocket. Наличие `n...` не даёт currency/units или имениprice.009price/brand/text features нельзя восстановить из guessed property IDs либо заполнить0. B retrievalscores/ranks/context иsourcepins должны быть выведены заново; схема events не переносит старые C или качество REES46models.

## Один будущий literal drill, без исполнения

Предложение≤32synthetic input rows суммарно,0fits; даже этот drill требует будущего разрешения внутри уже согласованного ledger. Fixture: S=1June,T=10JuneUTC; XcategoryA вT−4h, UviewX вT−3h, XcategoryB вT−1h, availableX=0 вT−30min. Golden currentcategoryX=B, historical viewX остаётсяA, unrelated latestavailable не стираетcategoryB. Добавить YcategoryB и VviewY: для candidateX currentB conditionalviewcount0/share0 при полномcategoryBdenominator1.

Два одинаковых UcartX→paircount2/itemdistinctcartusers1; VcartY вT−8d→observedrecency691200seconds, weeklycount0. Zlatestcategory known+NULL→unknown, noncategorycounts сохранены. PropertyX послеT и event ровноT не меняютpast. Future transactionW внеC остаётсяfullYmiss; zeroY/emptyC Q сохраняются. Два tree ancestors не удваивают view; numeric opaque property не включает price capability.

Literal expected tables должны отдельно показать eventbag, per-property state, historical event categories, query category, counts/distinct/recency/masks и exactphysicalkeys. Missing availability metadata обозначается unknown, неknown0. Проверка докажет только mechanics/capability rejection; реальные duplicates/NULL/coverage/calendar/cost/performance/generalization останутся неизвестны. Никакой dataset request, pilot approval, дополнительных model looks или execution budget этим исследованием не выданы.
