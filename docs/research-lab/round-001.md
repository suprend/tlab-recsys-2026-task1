# Research lab, round 001: типизированные реляционные признаки и честный поиск

15 октября 2026. Независимая исследовательская записка. Статусы ниже — предложения для review, не принятые решения и не результаты обучения. Код, данные и Git не менялись; пакеты, модели и датасеты не скачивались. Проверены текущий [план](../experiment-plan.md), [синтез признаков](../features/index.md), [embedding protocol](../embedding-experiments.md) и draft архитектуры/верификации backlog. Каноническая очередь — [backlog](../backlog.md), прежде всего TLAB-005/008/009/014/016. Root владеет temporal implementation.

## Что действительно дают первоисточники

1. **James Max Kanter, Kalyan Veeramachaneni, 2015, “Deep Feature Synthesis: Towards Automating Data Science Endeavors”, DSAA.** DFS строит признаки проходом по связям сущностей и композицией операций. Это основание для языка программ признаков, но не доказательство эффективности неограниченной композиции на REES46. В статье отдельно описаны вручную заданные временные интервалы/категориальные фильтры; переносить опубликованные результаты как успех полностью автономного поиска нельзя. [Авторский PDF, MIT](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf).

2. **Gilad Katz, Eui Chul Richard Shin, Dawn Song, 2016, “ExploreKit: Automatic Feature Generation and Selection”, ICDM.** Генерация unary/binary/groupby-кандидатов отделена от их ранжирования метамоделью, обученной на ранее исследованных датасетах, и дорогой проверки классификатором. Работа относится к плоским данным; сама по себе не задаёт временной replay. Полезна идея экономить проверки, а перенос готового meta-ranker требует отдельного обоснования. [Авторский PDF, Berkeley](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf).

3. **Tianping Zhang, Zheyu Aqa Zhang, Zhiyuan Fan, Haoyan Luo, Fengyuan Liu, Qian Liu, Wei Cao, Li Jian, 2023, “OpenFE: Automated Feature Generation with Expert-level Performance”, ICML.** FeatureBoost оценивает добавочный сигнал относительно исходных прогнозов; pruning и последующая attribution решают разные задачи. В pruning используются случайно выбранные блоки, а теоретический пример — transductive. Это не гарантия strict-past ranking и не разрешение считать proxy-fits бесплатными. [Издание и авторы](https://proceedings.mlr.press/v202/zhang23ay.html), [алгоритмы 2–4](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf). [Авторский репозиторий](https://github.com/IIIS-Li-Group/OpenFE) перечисляет classification/regression; готовый ranking-протокол оттуда не следует.

4. **Noah Hollmann, Samuel Müller, Frank Hutter, 2023, “Large Language Models for Automated Data Science: Introducing CAAFE for Context-Aware Automated Feature Engineering”, NeurIPS.** LLM предлагает код и объяснения с обратной связью. В опубликованной процедуре есть случайные validation splits, несколько итераций, ошибки с повторными запросами и semantic-blinding ablation. Для нашего сравнения полезна последняя идея; опубликованную процедуру оценки копировать нельзя. [Официальный PDF](https://proceedings.neurips.cc/paper_files/paper/2023/file/8c2df4c35cdbee764ebb9e9d0acd5197-Paper-Conference.pdf).

Отдельная практическая находка: Featuretools по умолчанию включает cutoff. Документация показывает, что `include_cutoff_time=False` даёт нужные включённую нижнюю и исключённую верхнюю границы окна. Даже с этой настройкой as-of metadata, fitted state и глобальная обработка секунд остаются обязанностью адаптера. Это документационная проверка, не тест библиотеки в нашем окружении. [Официальная документация времени](https://docs.featuretools.com/en/stable/getting_started/handling_time.html).

## Общий контракт и единственный ledger

Исходный контроль B — уже проверенный сильный manual boosting TLAB-008/009, его зафиксированные гиперпараметры, anchors, C, Y и split. Дополнительные fits baseline не «бесплатны»: здесь предполагается существующий пригодный run; иначе их нужно вычесть из лимита. Сначала независимый review и temporal gates, затем исполнение.

Один слот TLAB-016/HYP-002: **≤12 новых материализованных scalar feature columns, ≤4 новых fits всего, ≤2 CPU-часов**, 2 threads, peak RSS ≤8 GB. HYP-011 конкретизирует пространство HYP-002; HYP-012/013 — альтернативные уточнения её контроля/selector, не независимые бюджетные заявки. Материализация, selector/proxy-fits, ошибки, repair и повторные seeds входят в ledger. Новые support/mask-колонки тоже расходуют лимит; уже существующие supports переиспользуются. Неиспользованный бюджет deferred-ветви автоматически не перераспределяется.

Для ranking: основная metric — conditional macro-query NDCG@20 с полным Y, дополнительно Recall@20, all-query zero-convention, user-macro; candidate coverage обязана совпадать. До запуска фиксируются minimum-useful Δ=0,002 NDCG и guardrail ΔRecall≥−0,002; это предлагаемые пороги. Отдельно short/empty history, missing metadata, repeat/novel и каждый validation day. Публиковать support/missingness, wall time, RAM, число новых колонок и стоимость scoring. Бюджетный/неопределённый результат не объявляется отрицательным доказательством механизма.

При наличии четырёх development-дней: первые два — selection, следующие два — confirmation единственного замороженного победителя; модели обучаются до первого дня. Использованный final test закрыт. Даты и target здесь условны: изменившаяся задача требует заранее изменённого manifest, не подбора endpoints по результатам. Confirmation Δ≥0,002 с парным user-cluster 95% CI выше нуля и guardrails — основание для promotion. Selection intervals описательные: победитель трёх сравнений не получает обычный интервал как подтверждающее доказательство.

## HYP-011 — relative popularity taste через вложенный relational aggregate

**Статус: needs-pilot. Механизм:** schema-guided grammar порождает `log1p(V_i,w(t)) − A{log1p(V_j,w(t)): j∈D_u,h(t)}`, где `D` — distinct товары прошлых просмотров, `A∈{mean,max}`, `w,h∈{24h,7d}`. Восемь программ описывают, насколько популярность кандидата отличается от привычной пользователю. Типы включают grain, event type, unit, window, set/multiset и availability cutoff; одинаковые AST и manual-дубликаты удаляются до вычислений. ID не допускаются в арифметику.

**Новизна относительно backlog:** TLAB-005 содержит прямые user/pair/item/category counts; TLAB-012/HYP-001 — item-item cooccurrence; HYP-003 — hierarchy/lexical. Здесь новый путь user→distinct past items→global item state→user aggregate, без cooccurrence matrix и изменения retrieval. Это конкретизация пространства TLAB-016/HYP-002.

**Контргипотеза:** пользовательский reference лишь переупаковывает item popularity; сама разность с query-constant не меняет порядок popularity, а пользу может дать только взаимодействие с другими признаками boosting. Distinct weighting может проиграть event weighting; последнюю ось сейчас не открываем.

**Inputs/опыт:** past events, фиксированные candidates и manual supports. Grammar arm G выбирает четыре разные программы равномерно без возвращения с заранее записанным seed; B+G против B, один fit. Пустой D даёт missing; support распределения сохраняются в отчёте, отдельные model-колонки добавляются только из оставшегося column budget. Сначала tiny oracle и 100 queries для cost gate.

**Время/стоимость/приёмка:** все вложенные item состояния оцениваются на общем t по `[t−w,t)`, а не на конце месяца; D — `[t−h,t)`. Timestamp t исключён глобально, будущий suffix сохраняет результат. Стоимость измеряется по distinct `(u,t,j)` и числу touches, без user×catalog. ≤4 columns/1 fit из общего ledger; если ≤30 минут bounded materialization или RSS gate не пройдены, fit не запускается. Применяется общий metric/coverage/confirmation gate; без confirmation — только screening. **Переносимость:** любой стабильный user–item event graph; view-family специфичен доступным событиям REES46.

## HYP-012 — семантика LLM должна выигрывать у той же грамматики

**Статус: deferred, design-only до отдельной авторизации внешнего LLM API либо подтверждённого разрешённого локального ресурса.** Механизм — содержательное распределение предложений по той же DSL HYP-011; произвольный Python не исполняется. **Новизна:** уточнение HYP-002/TLAB-016 отделяет пользу понимания схемы от интерфейса предложения. Контроль semantic blindness делает это различие проверяемым; академическая идея уже присутствует в CAAFE.

**Inputs/baselines/точный опыт:** G из HYP-011; S получает описание ecommerce и осмысленные названия; A получает ту же topology/types/windows с обезличенными aliases без доменного описания. Оба предлагают максимум четыре scalar программы из той же восьмёрки одним заранее зафиксированным prompt, без validation feedback. Одинаковые version/temperature/token cap; содержательных пользовательских строк в prompt нет. Invalid/duplicate/manual proposals занимают попытку и не заменяются. Считаются также prompt tokens и ручное время подготовки.

**Бюджет/время:** G/S/A — максимум 12 column slots и три fits с одинаковым seed B; четвёртый fit не используется автоматически. Confirmation — scoring уже замороженных моделей на поздних development-днях, без refit. Пересекающиеся программы можно кэшировать, но число попыток не пополняется. Все arms проходят общий strict-past compiler/oracle; никакие labels/future schema summaries не видны proposer. Платная/недоступная ветвь остаётся deferred, сравнение G с B не доказывает пользу LLM.

**Accept/reject/scope:** сравнение S−G и S−A заранее фиксируется как вопрос семантики: confirmation CI обеих разностей выше нуля плюс общий gate S против B. Если selection выбрал другую ветвь, этот вопрос остаётся неподтверждённым; положительный результат другой ветви не приписывается LLM. Одного seed недостаточно для превосходства стратегии поиска в целом. Coverage идентична, missingness/cost сравниваются отдельно. Это переносимый протокол сравнения proposer, не обещание REES46 SOTA.

## HYP-013 — один совместный residual probe вместо featurewise fitting

**Статус: deferred, альтернативная замена HYP-012 в том же ledger.** Механизм вдохновлён OpenFE: оценивать добавочную пользу относительно B, но одним заранее ограниченным совместным correction model, чтобы учитывать взаимодействия. **Новизна:** в TLAB-016 нет способа распределить четыре fits между selector и конечной проверкой; TLAB-009 проверяет блоки, а не качество selector.

**Контргипотеза:** importance probe отражает корреляции/in-sample ошибки B, а его лучшая loss не соответствует NDCG. Inputs — восемь программ HYP-011, train labels и predictions существующего B. Один shallow probe с fixed offset B и фиксированными 32 trees/depth2, без early-stopping/search; importance выбирает top4. Затем два полных fits B+top4 и B+four seeded-random columns с seed B; confirmation scoring без refit. Это адаптация идеи, не воспроизведение OpenFE. При отсутствии соответствующего baseline score интерфейса работа остаётся deferred, скрытых дополнительных fits нет.

**Время/метрики/приёмка:** selector fit использует только train и зрелые labels до downstream cutoff; его in-sample predictions служат отбору, не выдаются за исторические features. Новые колонки сами проходят strict-past gates. ≤12 columns/4 fits/2 CPU-часа вместо, а не сверх G/S/A; план расходует три fits. Зафиксировать selector loss, последующий ΔNDCG, Recall, coverage и долю бюджета selector. Принять лишь при confirmation против B и top4−random CI выше нуля; если probe съедает >25% времени либо gate не проходит, отвергнуть selector. Generalization — supervised feature selection для event schemas; качество ranking proxy требуется перепроверять на другом домене.

## HYP-014 — готовый ExploreKit meta-ranker переносим без адаптации

**Статус: rejected для текущего бюджета.** Механизм — ranking по метапризнакам сократит проверки. Новизна относительно TLAB-016 — обучаемый cross-dataset selector; контргипотеза — shift от flat classification к censored temporal ranking делает порядок бесполезным.

Нужны provenance/version метамодели и meta-training corpus с результатами feature trials; сейчас такого входа нет. Точный допустимый будущий опыт: на одинаковых 12 strict-past колонках сравнить frozen meta-ranker top4 с seeded-random top4, два полных fits и один confirmation; обучение/адаптация selector тоже должны поместиться в оставшийся один fit и общий wall-time cap, включая получение его labels. Приёмка — общий NDCG/Recall/coverage/cost gate на отложенном домене, не AUC на исходных benchmark. Сейчас добывание корпуса требует множества скрытых fits: гипотеза отклонена, не превращается в bootstrap-проект. Возможная переносимость остаётся непроверенной, отсутствие входа не доказывает научную несостоятельность ExploreKit.

## Второй датасет: compatibility до загрузки

Кандидат — **Online Retail, Daqing Chen, UCI, 2015, DOI 10.24432/C5BW33**, CC BY 4.0. Официальная карточка: 541 909 строк, 1 декабря 2010 — 9 декабря 2011, XLSX 22,6 MB. [Источник схемы и лицензии](https://archive.ics.uci.edu/dataset/352/online%2Bretail).

| Свойство | REES46 October | UCI Online Retail / следствие |
|---|---|---|
| Unit/relations | Event, user/product/session | Invoice line; CustomerID/StockCode/InvoiceNo; не session-only |
| Time | UTC seconds | InvoiceDate содержит дату/время; timezone и фактическую точность ещё проверить; equal-time group обязателен |
| Events/negatives | view/cart/purchase, нет impressions | Transaction/cancellation; views/impressions отсутствуют в опубликованной схеме; conversion-after-view неприменим |
| Metadata | Category ID/code, brand, price as-of | Description, Quantity, UnitPrice GBP, Country; taxonomy/brand primitives отключаются |
| Grain semantics | Нет orderID | InvoiceNo и quantity: count lines, distinct invoices и units различать; код c означает cancellation |
| Horizon/coverage | Один месяц, частичная история | Более года в карточке; completeness, customer missingness и пригодный H требуют проверки самого файла |
| Применимые primitives | Вся проверенная event grammar | purchase/recency/distinct и nested item popularity; не притворяться, что purchase-rows равны views |

Это будущий малый тест schema portability после полезного REES46 pilot; загрузка сейчас не нужна. Успех компиляции на UCI не доказывает качество рекомендаций и не создаёт дополнительный fit budget. Retailrocket пока не включён: первичная Kaggle-карточка не отдала проверяемый текст лицензии через текущий reader, поэтому вторичные пересказы не заменяют license gate.

Рекомендуемый первый шаг — review HYP-011 как конкретного ограниченного среза TLAB-016. HYP-012/013 являются взаимоисключающими продолжениями ledger, HYP-014 сохраняется как обоснованный отказ. Новые исследования не открывают final test и не расширяют поиск автоматически.


## Review appendix — принято координатором 15 октября2026

[Независимая критика](round-001-review.md) сохранила один material finding: поздние development-дни не становятся независимой confirmation после их использования для выбора baseline/loss/manual blocks. До первого008fit canonical backlog резервирует22–23октября как selection и24–25как lockedconfirmation для всех связанных решений; при невыполнении этогоgate вывод screening-only. Availability/maturity и freeze выбранной модели/claim до firstconfirmationquery обязательны. HYP-011 accepted-for-pilot внутриHYP-002/016, HYP-012/013deferred, HYP-014rejected. Это принятие дизайна, не экспериментального выигрыша; исходная записка выше сохранена без переписывания.
