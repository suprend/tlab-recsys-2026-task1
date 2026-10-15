# Round070 — MIND: перенос арифметики, смена recommendation contract

15 октября2026. Primary-source/schema-only assessment для будущего generalization раздела. Дедуп [031](round-031.md), [040](round-040.md), [052](round-052.md), [068](round-068.md): здесь принципиально другой источник — logged news impressions, а не очередное переименование product actions. Архивы/датасет/API/models не открывались; downloads, SQL/tests/fits/jobs/code changes отсутствуют. Frozen016/25–31, HYP/tasks и бюджеты не изменяются.

## Publisher facts и границы проверки

[Официальная карточка MIND](https://msnews.github.io/) описывает anonymized Microsoft News logs: около160тыс. English news, более15млн impressions,1млн users; MIND-small —50тыс. sampled users. Это publisher cardinalities, не наши измерения размера файлов/RAM. Exact compressed bytes/checksums/current archive availability не проверялись; download buttons не нажимались.

[Wu et al., ACL2020, §3](https://aclanthology.org/2020.acl-main.331.pdf) уточняет161013news/15777377impressions, период12Oct–22Nov2019 и выбор users с≥5clicks за шесть недель. Последняя неделя — test, пятая — training, её последний день — validation; history training извлечена из первых четырёх недель, test — первых пяти. Сохранены samples с непустой history. Поэтому это не prospective past-active48h sampling всех пользователей: population selection зависит от активности за весь период. Это характеристика benchmark cohort, не автоматическое обвинение каждой feature в leakage.

[Publisher format document](https://raw.githubusercontent.com/msnews/msnews.github.io/master/assets/doc/introduction.md) указывает non-commercial research use/free access и ссылку на Microsoft Research terms. Полный license PDF при данном чтении не извлечён; не утверждаю CC/MIT, право перераспространения или действующие права на все тексты. Dataset rights не наследуются от лицензии кода.

Behaviors имеет impressionID,userID,time,History,Impressions. History — упорядоченные clicked news IDs; **времен отдельных кликов нет**. Impressions содержит newsID-clicklabel, порядок кандидатов shuffled. Timestamp format — AM/PM string; timezone/ingestion availability/точный response-delay здесь не объявлены. News содержит category/subcategory/title/abstract/URL/entities, без revision/available_at. Документ говорит «7columns», перечисляя8; [Microsoft Learn пример reader](https://learn.microsoft.com/en-us/azure/open-datasets/dataset-microsoft-news) задаёт8 names. Это наблюдаемое противоречие документации, не проверенный header файла. Там же уточняется: full body не распространяется, несмотря на широкое описание контента карточкой/статьёй; URLs могут быть недоступны.

## Почему нельзя назвать это прежней задачей

В MIND естественный query — конкретный impression, C — реально показанный список, Y — clicked entries именно этого списка. Nonclick0 — recorded outcome при logged exposure; это не наш purchase0 для непокупки из past-popular C. Внутри данного impression positive Y⊆loggedC по конструкции; это не evidence высокой retrieval coverage и не наблюдение всех будущих предпочтений пользователя.

Наш daily purchase target `[t,t+24h)` независимо от C сохраняет cold/outC misses. Подмена его MIND clicked-in-impression target меняет objective, query weighting, candidate domain и maturity. Current news article может присутствовать в logged C, впервые появившись ровно при query: удаление его как «не past observed catalog» создаст другой эксперимент. Logged exposure также не даёт автоматически propensities/original display positions: shuffled order нельзя использовать как исходную позицию или causal randomized exposure.

[Official evaluate.py](https://raw.githubusercontent.com/msnews/MIND/master/evaluate.py) читает impression-specific labels/ranks и вычисляет AUC/MRR/nDCG5/10. Это иной benchmark contract, не аргумент заменить наши frozen006 metrics. Его наличие не устанавливает endpoint/availability guarantees нового adapter.

## Capability matrix: что действительно переносимо

| Primitive/obligation | Будущее допустимое binding | Что сейчас unsupported |
|---|---|---|
| COUNT/history breadth | Количество entries в данном HistorySnapshot; DISTINCT news IDs внутри него | Конкатенация повторённых snapshots как новых rawclick events |
| User/item/pair window counts | COUNT прошлых impression exposures при explicit exposure grain и clock | Click24/168h из нетаймированных History; click→purchase/cart/view shortcut |
| Recency | Время последнего prior impression при новом action/availability contract | Seconds since historical click; ordinal position не elapsed seconds |
| Category affinity | Snapshot-category join при явном metadata knowledge assumption | Event-time category, revision/asof proof, brand/price/stock из news metadata |
| Q/C/Y | Impression IDs и отдельно сохранённые candidates/labels | Daily active48h/full-future-purchase equivalence |

Это перенос count/distinct арифметики и typed dependency checks **после новой binding**, не drop-in capability current005/016: их canonical actions/windows/schema строго ограничены. Отсутствующие cart/purchase — unsupported, не observed0. Отсутствующее время исторического click — unknown, не impression timestamp, «давно» или NaN model feature под видом доказанного recency. Static news/category также не устанавливает, какая версия была доступна раньше.

Особая access obligation: candidate IDs и labels упакованы вместе, например N1-1. Future trusted de-labeling должен создавать Q/C без ветвления по suffix и escrow Y отдельно. Предиктор не получает labels/evaluator; label-mutation invariance проверяет независимость Q/C/F. Физическое чтение исходных packed bytes таким preprocessor не равно query-level outcome blindness; эту границу нужно назвать честно. Поздние clicked outcomes нельзя обновлять в earlier feature state лишь по impression time без отдельного knowledge/delay assumption.

## Future literal fixture≤32rows,0fits — только спецификация

Предложить19rows:3Q,6History entries,6candidate rows,4news records. Q1=(U1,T),Q2=(U1,T+1h) имеют **одинаковую** History=[A,A,B]; Q3=(U2,T) пустую. Q1 C=[X1,Y0,Z0], Q2 C=[Y1,X0], Q3 C=[X0]; news A/X=Sports,Y=Politics,B.category=NULL, Z отсутствует. Это искусственный stress fixture; empty-history Q проверяет adapter retention, не утверждается наличие такого sample в release.

Literal gold: Q1/Q2 history_count3, distinct2, pair_history(A)2, pair_history(X)0; Q3 count0/distinct0. Повтор snapshot не превращает3 в6. Current X1 не добавляется в Q1 history; Q2 также получает supplied snapshot, а не скрыто обновлённую историю из Q1label. Windowed click_count24/168 и click_recency_seconds **reject unsupported**. Known empty category match может дать0 по separately declared snapshot operator; NULL/missing news metadata даёт unknown, не общий fake category. Перестановка shuffled C и изменение всех suffix labels сохраняют Q/C/F; меняется только Y. Two same-time impressions не обмениваются current labels. При synthetic available_at>T metadata не backfills Q1; unknown availability останавливает strict-PIT claim. Q3 проверяет retention, не scorer: allzero labels не определяют AUC, а published nDCG делит нанулевой IDCG.

Future pass подтвердит только capability rejection/typed transport/row grains на literals. Он не докажет реальный knowledge clock, source completeness, MIND quality gain или переносимость B41. Практический итог — добавить MIND как **контрпример универсальности time-window grammar** в существующий generalization раздел: reusable arithmetic требует observation/availability annotations, а другой objective и logged C требуют нового source-local protocol. Новых HYP, задач, fit allowance или изменений нынешнего исследования нет.
