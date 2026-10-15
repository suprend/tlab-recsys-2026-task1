# Round043 — один внешний validation pilot: Retailrocket

**Предложение после завершения bounded REES46 comparison, не разрешение запуска.** Данные, archives, CSV, download endpoints не открывались; code/install/tests/Pool/fits/scans отсутствуют. Выбран Retailrocket: publisher прямо описывает три необходимых action capabilities, поэтому здесь меньше неопределённости event mapping, чем при выборе только по популярности benchmark. Это внешний источник наблюдений, а не автоматически независимая команда проверки. Новой HYP нет: refinement existing generalization/typed-contract hypotheses.

## Publisher facts и конкретная compatibility matrix

[Официальная Kaggle card](https://www.kaggle.com/retailrocket/ecommerce-dataset/home) прочитана через индексированный текст самого publisher URL; прямое представление пустое. Card заявляет4.5месяца,2756101events,1407580visitors,20275902property rows для417053items,1669category-tree rows; version2 показывает987.5MB. Лицензия указана CC BY-NC-SA4.0. Это утверждения карточки, не наши byte/count measurements; compressed size, RAM, текущий доступ без account и фактическое качество неизвестны.

| Аспект | Primary card/schema | Proposed binding к005/016 | Условие отказа/unknown |
|---|---|---|---|
| Countable relation | timestamp,visitorid,event,itemid,transactionid | Raw event bag; nominal user/item; transactionid не eventID | Не collapse одинаковые строки или целый transaction |
| Actions | view/addtocart/transaction | Явное view→view,addtocart→cart,transaction→purchase | Не заменять unsupported action известным0 |
| Clock | Unix timestamp example1439694000000 | Milliseconds→UTC — проверяемая adapter assumption | Exact endpoints/availability delay первичным источником не установлены |
| Category state | timestamp,itemid,property,value; weekly snapshots compressed в change log | categoryid через отдельно reviewed property resolver | Snapshot clock не доказанный ingestion/available_at |
| Other metadata | categoryid/available раскрыты, остальное hashed; numeric n-prefix | Не включать guessed price/brand/title | available snapshot не current stock/exposure |
| Размер/лицензия | Указанные card size/version/license | Записать source version/terms в prospective register | Размер карточки не resource feasibility proof |

Category tree содержит nominal parent edges, не readable labels. Историческая доступность edges неизвестна. Поэтому ancestor expansion и новые metadata operators не входят в этот pilot. Количественные source facts выше относятся только к card; строки архива и headers не инспектировались.

## Проверяемый вопрос, которого ещё нет в036/040

Первый contrast здесь **correctness**, не ranking: сохраняет ли отдельный adapter значения существующих noncategory count/distinct/full-prefix-recency программ при переходе от REES event schema к Retailrocket event schema? Контргипотезы конкретны: неверная единица времени, transaction-level dedup, future property backfill, fanout после properties join или потерянный NULL mask.

[Featuretools Handling Time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html) связывает время с доступностью данных и отдельно secondary indices; тип timestamp сам по себе не устанавливает knowledge clock. Поэтому adapter обязан явно объявить event-time-as-availability assumption либо отказаться от строгого knowledge claim. Это synthetic mechanics proof при assumption, не установление фактической доставки weekly snapshots.

Current005 получает category из последнего глобального event bucket. Retailrocket property может измениться между последним event иquery. Enrich event его тогдашней category корректно для historical counters, но не реализует latest query property state. Поэтому «все18cores/B41 без изменений переносимы» — заранее отвергаемая формулировка.12noncategory manual cores и noncategory L01–08 имеют совместимую математическую цель; full registry/context/retrieval всё равно требуют нового binding и review.

## Preregistered tiny correctness-only smoke

Предложенный scope:≤32литеральных synthetic input rows,0fits, без raw download. Например10events+6property updates+3Q+5C+2tree edges=26rows; schema/case IDs заранее фиксируются, adapters не выбираются по результату. Independent list oracle и literal expected tables задаются до compiler output; production resolver не используется как expected-value implementation.

| Literal case | Обязательный expected result |
|---|---|
| Два одинаковых U cart X за1h доT | Pair rawcount2, item distinct cart users1 |
| Cart ровноT−24h и ровноT | Первый включён в24h count, второй исключён; peers перестановкой не меняются |
| Единственный cart за8d доT | Weekly count0, observed recency691200s, missing=false |
| XcategoryA→viewX→categoryB доT | Historical view categoryA; query property categoryB; fake view для update отсутствует |
| Latest category bucket known+NULL | Unknown conditional key/flag; older category не восстанавливается |
| Zero-Y Q, empty-C Q, target item внеC | Q cover сохраняется; target не вставляется в C ради score |

Последняя строка проверяет будущий protocol/evaluation boundary отдельно от label-free feature interpreter. Unknown category не обнуляет noncategory counts. Property suffix послеT не меняет past; unrelated available update не стирает category carry-forward. Literal integer/NULL/physical types проверяются точно. Source schema rename требует явного mapping, а не semantic inference по имени.

Pass подтвердит только adapter/transport/operator mechanics на этих witnesses и правильное rejection unsupported paths. Fail опровергнет конкретный portability claim до quality experiment. Ни source coverage, ни real metadata conflict frequency, ни predictive transfer этим smoke не доказаны. Будущий resource/time cap должен быть разрешён отдельно;32rows не создают автоматический execution budget.

## Отдельный quality plan, пока deferred

До любого quality разрешения нужны actual source/version/coverage/clock audit, source-local protocol и label-independent Q/C sampling, maturity endpoints и положительный decision gap. Нельзя копировать October2019 anchors на неизвестные Retailrocket boundaries. [Ji et al. temporal evaluation](https://arxiv.org/abs/2010.11060) обосновывают важность global timeline, но не гарантируют переносимость frozen модели между магазинами.

Предлагаемый предмет quality study — source-local matched manualB против заранее выбранного typed-program pipeline, с одинаковыми Q/C/fullY, training population/settings и заранее фиксированным primary contrast. Он изучает перенос **метода генерации**, если модели обучаются заново; применение прежней REES model было бы другим вопросом. Полный B41 допускается только после отдельной category resolver acceptance. Иначе нужно явно определить event-only B и более узкое утверждение; подмена отсутствующих category/price нулями не сохраняет исходный B.

Source-local budget, calendar, fits и decision rule должны быть приняты как отдельный будущий эксперимент; здесь не назначаются новые attempts или mandatory looks. REES-selected bundle нельзя после внешних labels заменить новым winner и назвать untouched transfer. Negative valid contrast опровергает заявленное улучшение на этой cohort; неопределённость не доказывает эквивалентность. Даже успешный Retailrocket pilot поддержал бы перенос ограниченного метода на один additional source, а не universal schema automation, learned intelligence, causal lift или экономию human-hours.
