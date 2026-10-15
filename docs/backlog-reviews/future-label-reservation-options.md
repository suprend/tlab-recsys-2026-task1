# Следующий месяц REES46: возможная новая reservation, не продолжение October approval

15 октября2026. Publisher metadata/documentation only: прочитаны официальные каталоги, индексированный текст авторской Kaggle card и опубликованные project provenance notes. Никакие archive/CSV/event/label bytes, existing ignored fragments, actual models/scores или hash streams не открывались; download/HEAD/Range/SQL/jobs/fits/Git отсутствуют. Предложение не меняет frozen October study и не предоставляет нового бюджета/доступа.

**Рекомендация:** November2019 — правдоподобный ближайший источник для отдельной temporal replication, но **defer до сдачи текущего T-Academy результата**. Не считать его полностью unseen; не обещать ID continuity, готовую лицензию стандартного формата или возможность запуска existing October configs. Новая HYP/task не нужна: existing014 research,015 evaluation,018 bootstrap и будущие выбранные HYP уже имеют подходящие seams.

## Что подтверждено publisher, а что нет

| Поле | Primary metadata fact | Ограничение проверки |
|---|---|---|
| Семейство/период | [REES46 catalog](https://rees46.com/en/datasets): Multi-category behavior, Oct2019–Apr2020 | Это продолжение того же publisher/store family, не новый независимый магазин |
| November availability/size | [Official data landing](https://data.rees46.com/) перечисляет `2019-Nov.csv.gz`, label2.69Gb | Listing inspected; файл не запрашивался, точные bytes/SHA/CRC/current download access неизвестны |
| CSV/schema | [Авторская Kaggle card, cached publisher URL](https://www.kaggle.com/mkechinov/ecommerce-behavior-data-from-multi-category-store/tasks): November CSV9.01GB;9fields: event_time/type,product/category IDs,code,brand,price,user/session IDs | Publisher description, не измеренные header/types/rows нашего будущего source |
| Time/actions | Та же card: UTC; view/cart/remove_from_cart/purchase | Landing page также упоминает category views; actual per-file token inventory не проверен |
| Rights | Card: free use с указанием card и REES46 | Формальный license identifier/dropdown сейчас не раскрыт; CC/MIT не установлены |
| Identity | Card: permanent user ID; product ID; temporary session ID | Нет найденной явной гарантии cross-month product identity/no ID reuse/metadata version stability |

Прямое открытие canonical Kaggle page дало пустой текст; факты card прочитаны через индексированный **тот же publisher URL**, не сторонний notebook. Directory `/datasets/marketplace/` был недоступен; источник размеров — HTML landing, не archive response. В текущем индексированном Data Explorer видны Oct/Nov, тогда как каталог перечисляет семь месяцев; совпадающее имя файла не доказывает byte identity двух способов доставки. Не использую сторонние row counts или объявления о лицензии как publisher evidence.

## November уже частично использован, но не как текущий target test

[Published category audit](../category-recovery.md) прямо сообщает, что14октября2026 скачаны первые16MiB compressed каждого следующего месяца; November prefix содержит411162полных событий. Проверялись category codes и product/category/brand overlap с October. В этом исследовании эти fragments не перечитывались. Поэтому фразы «никто не видел November» и «никаких future bytes» неверны. Published checks не являются November query-level ranking evaluation, но их informational exposure нужно включить в future decision record.

Та же audit показывает изменения category assignments между месяцами. Это не доказательство, что product IDs переиспользованы для других SKU: измениться мог атрибут прежнего товара. И наоборот, overlap ID/похожесть brand не удостоверяют универсальную identity continuity. Intent автора о permanent users — полезная опора, однако перенос user/item histories остаётся явно названным dataset assumption с проверяемыми несовместимостями, не восстановленной ground truth.

Прежде чем назвать конкретный domain reserved, будущий уполномоченный reviewer должен установить extent уже inspected prefixes из прежнего provenance, проверить отсутствие прежних query-target/metric accesses для выбранных queries и сохранить это evidence. Нельзя молча выбросить inconvenient exposed queries после результатов. Public descriptive metadata и full-source checksum сами по себе не равны использованию будущего target как model-selection feedback; запрещать «любые future bytes» было бы ложным описанием нашего offline режима.

## Неочевидный adapter gate: четвёртый action влияет не только на counts

Current016 grammar фиксирует три actions и canonical schema. `remove_from_cart` нельзя переименовать в cart/purchase. Простое отсутствие его в count FILTER тоже недостаточно для утверждения «протокол неизменён»: past-any-event eligibility, U(t), recent items, observed first_seen и latest-global metadata могут читать этот event. [Current source semantics](../experiments/feature-programs.md) требуют отдельного explicit capability/adapter contract.

В новом protocol надо заранее выбрать token domain **каждой** relation: raw bag, Q eligibility, popularity, recent history, metadata/age и target. Например, сохранить полный raw source, но явно ограничить model/business history тремя прежними типами — допустимое новое предложение, а не уже принятое правило. Если выбрать any-source-event domain с remove, это тоже объявляется как изменение наблюдаемой поддержки. Unknown category-view token требует установленного mapping/rejection; ничего не отбрасывается silently. FullY остаётся distinct purchase-items, не оплаченные orders; stock/exposure/ingestion clocks не появляются от смены месяца.

## Один компактный будущий вариант, без новой learning search

После completion текущего claim возможно отдельно зарегистрировать **frozen B/W temporal replay** на заранее выбранном November block, с теми же model/program/weights/params/trained iterations/scoringprefix и одной primary full-Y query-macro comparison. Это оценка тех же fitted pipelines на других датах того же source, не перенос качества между datasets и не повторное обучение search procedure. При W=B прозрачный identical-model reuse даёт нулевой contrast; нельзя выбирать проигравший October arm вместо него ради интересного followup.

Пример planning domain — Nov8–14 с H24 и observed source отNov1: он даёт полный7d window с первого anchor и nominal maturity доNov15. **Это кандидат календаря, не reservation/config approval.** Он допустим лишь после проверки prior exposure, покрытия/availability и положительного simulated decision gap после всех использованных October outcomes. Actual2026 seals должны предшествовать открытию новых reserved query-level Y; simulated2019 times определяют допустимость replay, не существование моделей в2019.

Для carryover есть два разных contracts, выбрать один до outcomes:

- **Continuous Oct+Nov prefix:** early-Nov histories используют admissible October events, включая уже потраченный October test. Это обычное новое past context, не изменение старого test; требует declared ID continuity и source-union identity, global peers/duplicates/boundary proof.
- **November-only reset:** не переносит histories между месячными ID namespaces; S=Nov1, age/full-prefix-recency относятся только к этому observed source. Получается cold/reset replication с потерянной старой историей, а не точный continuous-serving replay. Достаточно полного7d не восстанавливает lifetime recency/age.

Нельзя после качества выбрать более удобный вариант или прогнать оба как «бесплатную sensitivity». При недостаточной identity evidence reset — консервативный prospective вариант, но его иной context обязан отражаться в report. Metadata берутся только из допустимого нового past bucket, без recovered future names или whole-month mappings. Known+NULL/conflict остаётся unknown; source coverage не доказывается отсутствием gaps между минимальным/максимальным event.

## Обязательные будущие gates и цена

Existing October protocol/heldout config закрепляют иной calendar/source identity и не допускают November как новый path argument. Нужны новое versioned source/import policy, schema/token/ID/carryover contract, new Q/C/context lineage, independent formula/key proof, resource owner/approval и prediction-before-target unlock. Old304-pin control/source approval не становится разрешением нового source; fresh hash не external semantic acceptance.

Сначала source-free≤32-row conformance: два месяца с одинаковым/новым ID, changed category, remove token, boundary cart, global peers, exact duplicates, old cart recency, emptyC/zeroY/coldY и last-H maturity. Literal expectations задаются отдельно для continuous/reset policy; тесты сейчас не запускались. Затем лишь отдельно approved bounded label-blind100Q source/cost gate; output cap не ограничивает import/hash/CRC/popularity scan. Publisher2.69Gb/9.01GB не прогнозируют DuckDB size, RAM или runtime.

Новый budget должен покрыть acquisition/import/CRC/hash, source recomputation, all-day B/W predictions, independent saved-model replay/evaluation, failures и cleanup.0новых fits для frozen-model варианта не означает0cost/0looks. При отсутствии целевого support conditional result undefined, без redraw/смены dates; quality loss — reporting, integrity/resource failure — остановка с сохранённым evidence. Ни данных, ни исполнения, ни дополнительных fits этот документ не разрешает.

Практический итог: **worth retaining as deferred temporal-replication option**, особенно как источник действительно новой заранее закрытой query-target domain после October. Для текущей сдачи важнее accepted016/015 outputs, readable negative/uncertain conclusion и018/README reproduction. November не должен становиться новой critical path или оправданием повторного «untouched October» claim.


## Publication scope appendix — 15 October 2026

Original note SHA256 fa6e131e3e1babea5a9c125ca6d11fac50381af4702beed8db5a9f5711b6278a. This retained research snapshot predates the locally accepted actual016 model evidence in the current [progress report](../progress-report.md). Its future tense is historical scope, not the current canonical execution status. No new hypothesis execution, resource grant, fit, source download or reserved-target access is authorized by publication. Current accepted development winner is R2; this does not establish guided-strategy superiority or heldout improvement.
