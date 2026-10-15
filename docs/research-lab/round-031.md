# Research lab, round031: Tianchi UserBehavior и совместимость005/016

15 октября2026. Это **schema-only compatibility proposal**, уточняющее [004](round-004.md), [026](round-026.md) и [030](round-030.md). Прочитаны карточка издателя, авторские статьи/код и frozen [manual18](../../configs/features/manual-18.json)/[005](../../scripts/manual_features.py). Архивы, ZIP, CSV и dataset binaries не открывались и не скачивались; scans, compiler, Pool, fits и tests не запускались. Root019/016, бюджеты и approvals не изменены. Новая гипотеза качества не заявляется.

## Что подтверждено первичными источниками

[Карточка Tianchi649](https://tianchi.aliyun.com/dataset/649) существует под названием «淘宝用户购物行为数据集». В доступном текстовом представлении получен только заголовок; legacy URL перенаправляет сюда. Browser fallback недоступен. Поэтому точные календарные границы, полный официальный словарь действий, размеры файла, численности сущностей, source completeness, license и текущие условия доступа **не подтверждены этой проверкой**. Это ограничение чтения, а не утверждение, что лицензии нет. Условия репозитория с кодом не заменяют разрешение на dataset; third-party notebooks не используются для заполнения пробелов.

[Alibaba NANN README](https://github.com/alibaba/nann/blob/master/README.md) прямо связывает демонстрацию с UserBehavior. Его [авторский converter](https://github.com/alibaba/nann/blob/master/NANN_impls/nann/data_provider/convert_UB_to_tfrecord.py) читает пять позиций: user, item, category, behavior, timestamp. Число100150807 задано как progress-bar total, а не результат проверенного подсчёта. Код игнорирует behavior, строит item→category по всему входу и случайно разделяет пользователей. Это подтверждает формат потребителя, но не полноту выгрузки, календарь, timestamp units/timezone или словарь actions. Whole-file category map нельзя наследовать для наших исторических признаков.

Название Taobao не определяет dataset. [DSIN, §4.1](https://arxiv.org/pdf/1905.06482) использует публичный Alimama display/click dataset, ссылаясь на Tianchi56, и отдельный промышленный recommender log; это не649. [DIEN, раздел Datasets](https://arxiv.org/pdf/1809.03672) описывает Amazon reviews и industrial advertising impressions/clicks. Ни одна статья не служит подтверждением размера/дат/лицензии649; их AUC и отрицательные рекламные impressions нельзя переносить на purchase/fullY задачу.

## Минимальный явный adapter contract

**Предложение после подтверждения publisher semantics:** predicates `behavior='pv'→view`, `='cart'→cart`, `='buy'→purchase`. `fav` не превращать в cart/view; неизвестный token не становится нулём известного действия. Сначала reviewer фиксирует action dictionary, null/unknown policy и точные исходные типы. Пятиколоночный consumer сам этого не доказывает.

Самый небольшой вариант — canonical relation только из трёх разрешённых predicates, с сохранением каждой raw строки, включая точные дубликаты. Это **изменённый observation domain**: fav-only item/user не становится наблюдавшимся в нём; observed age, eligibility, current category и candidate catalog считаются по этой relation. Если нужна наблюдаемость по всем четырём actions, потребуется отдельно согласованная all-action relation и lineage; не объявлять её существующей возможностью005. Fav-only user не должен случайно пройти фильтр активности трёх действий.

User/item/category — nominal exact keys даже при integer storage. Никаких средних ID, taxonomy ancestors или readable category codes из числового порядка. Нельзя объявить `(user,item,time)` уникальным eventID. Missing brand/price — unsupported capabilities, а не известные0; добавление NULL canonical fields не делает009 price/brand features переносимыми.

Event timestamp требует подтверждённых units/epoch/timezone и UTC conversion policy. Нет отдельного available_at — event-time-as-availability только явное offline допущение, без доказательства online serving. Source bounds/completeness объявляются независимо от min/max observed events: отсутствие строки не означает exposure/stock или непрерывную регистрацию. Исторический category хранится на событии; current category выбирается из последнего **глобального** past timestamp bucket, conflict/NULL mixture→unknown, без older backoff и whole-file backfill. Подтверждение, что поле было известно при событии, остаётся человеческим annotation obligation.

## Capability matrix для существующего vocabulary

| Блок | Что можно сохранить условно | Что меняется или unsupported |
|---|---|---|
| 12 noncategory manual18 cores | U/P/I count, distinct и full-prefix recency после mapping; bag и strict past | Значения/observed prefix/cohort новые; это не перенос готовых F |
| 6 category manual18 cores | Historical event-category counters, conditional latest-past key, shares с полным знаменателем | Нужны category availability/NULL contracts; статичность не выведена из schema |
| Masks/coverage/age | NULL vs known-empty, coverage24/168, missing recency | Source clock и observation domain новые; coverage≠exposure, age≠coverage |
| Остальная B41 retrieval schema | Можно заново вывести популярность/repeat/ranks из согласованной истории | Старые C, flags, scores, pins и cardinality не переносятся |
| Generated016 L01–08 | Count/distinct/cart-recency используют те же три действия и24/168 windows | Closure ровно3 physical columns проверяется заново против нового B; пока не implementation |
| 009 brand/price/code block | Нет подтверждённого входа | Не заполнять zeros, не заявлять полный feature parity |

Три category-count cores, две shares и category-recency требуют отдельной проверки grain. Например denominator category share охватывает все observed products категории, не только C. Current item category и historical category события могут различаться; последняя категория не переписывает старые counters. Смена источника меняет context identity даже при одинаковом registry JSON.

## Q/H/C и ограниченная будущая проверка

Purchase target можно **предложить** как distinct buy-items в `[t,t+H)`, независимо от C; история `[t−W,t)`, global peers не видят друг друга. H=24h и7-day activity сохраняются лишь при достаточном подтверждённом календаре/coverage/maturity. Месячный REES46 split не копируется. Короткий календарь может не вместить warmup, train, selection, положительный decision compute gap и confirmation — тогда полноценный протокол unsupported, а не автоматически сокращён. Dataset claims о датах здесь остаются unknown.

Q выбирается только по past eligibility и frozen hash до labels. C — prior-observed catalog proxy, не stock; unseen/outside-C purchases остаются fullY misses, zeroY/emptyC queries сохраняются. Такой protocol создаст отдельную observational purchase-ranking задачу; он не воспроизводит NANN next-event preprocessing или DSIN CTR evaluation и не доказывает cross-dataset quality.

Будущий **только synthetic** conformance proposal: ≤32 literal rows,0fits, вход≤64KiB; перспективный лимит≤5min/2threads/512MiB требует отдельного разрешения. Gold table включает duplicate pv→rawcount2/distinct1; cart peer ровноt→past0; old cart вне7d→finite full-prefix recency; fav-only item→absent в выбранном domain; conflicting categories→conditional NULL/noncategory count сохранён; buy outC→fullY miss; buy наt+H→excluded. Дополнительно reject unknown clock/token, lost BIGINT precision, missing price capability и future category backfill. Output: adapter policy, capability/rejection matrix, exact Q/C/F schema и literal expected values. Это проверит mechanics/closure; без реального source audit не установит completeness, стоимость100m строк, качество или generalization. Download, реализация и новый execution budget этим note не запрашиваются и не разрешаются.
