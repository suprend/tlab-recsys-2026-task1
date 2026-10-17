# Wave100 B FIRST — порядок событий и доступность не заменяют друг друга

Независимый SOURCE-only автор B. Due 2026-10-17 09:45 UTC; первая наблюдённая clock observation 09:47:33 UTC, не точное время начала. Следующий исходный срок 10:30 UTC / 13:30 МСК, шаг 45 минут сохранён. Автор A волны100, его FIRST и сообщения не читались; помощники не запускались. Прочитаны research-campaign/research и прежние исследования. Запись только в три собственных TMP-артефакта. Dataset bodies, raw/DB/Parquet, проектные/backend imports, SQL, prototype/test execution, fit, scoring, canonical/Git mutations: **0**. Только чтение документов, две официальные web-страницы и stdlib metadata hashing/writing.

**NEW 0 / REFINE 1 / proposed MERGE 1 / ADMIT 0.** Одно уточнение HYP-142 (FB-01) и существующего transfer-conformance HYP-002/HYP-046, TLAB-005/016/018; REFINE и MERGE относятся к одному предложению, не двум. HYP-087/HYP-088 зарезервированы и не формулируются заново. Никакой новой обязательной задачи, adapter framework, внешнего датасета, скачивания, fit или положительного quality-критерия.

## B100-1 — один clock нельзя подставить сразу в отбор и в порядок пути

**Что действительно переносимо.** Номинальные entity roles, декларации action capabilities, multiset multiplicity, отдельные masks/coverage, физическая closure, versioned recipe и ограниченное выполнение могут переноситься как явные контракты. Но для order-sensitive оператора нужно отдельно установить (а) когда occurrence стал известен и потому допустим при запросе, (б) когда он произошёл и где стоит в behavioral path. Нельзя вывести оба значения из имени `timestamp`. Без этого даже безошибочное совпадение event counts и последних recencies не удостоверяет path statistic. Передача recipe/typed columns сама по себе также не переносит пользовательскую сущность, смысл actions, target/fullY, кандидатный каталог или полноту наблюдения.

**Первичные основания, проверены 17 октября2026.** [Featuretools 1.31.0, Handling Time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html#secondary-time-index) описывает time index как первую доступность информации строки и secondary time index для полей, ставших известными позже. [Feast, Point-in-time joins](https://docs.feast.dev/getting-started/concepts/point-in-time-joins#retrieving-features-as-of-the-event-time) объясняет: default join ограничивает event timestamp, поздний created timestamp используется при дедупликации, а explicit created filter добавляет ограничение доступности; соответствующая store capability может отсутствовать и тогда должна давать ошибку. Это документированные API-различия, **не** проверка установленных пакетов, не наш adapter и не доказательство доступности исходных REES-событий. В частности, документированное Feast `created<=query` не подменяет наш заранее выбранный strict `<T` global-peer contract.

**Механизм.** У HYP-142 уже задано `A_VC = Σ_{s<r}(n_V(s)n_C(r)−n_C(s)n_V(r))` по occurrence-time buckets после отбора разрешённой истории; одновременным событиям порядок не изобретается. Для literal world с двумя clocks сначала выбираем `valid_at<T AND known_at<T`, затем упорядочиваем оставшиеся buckets по `valid_at`. Если пропустить первый clock, получится будущая осведомлённость; если отфильтровать и упорядочить всё по второму, получится иной путь. Ассоциативное объединение состояний path не разрешает перестановку блоков: здесь операция некоммутативна. Это применение уже зарегистрированного механизма, не новая feature family.

**Литеральный контрпример, ручное рассуждение, не исполненный тест.** Один synthetic user U и item I, Q/C заданы внешне и не проверяют REES active48h eligibility. Все occurrences внутри168h; источник объявляет полное предыдущее окно и отсутствие остальных событий. Время — точные секунды относительно объявленного origin; все `known_at>=valid_at`, clocks сопоставимы, raw multiplicity сохранена. Никаких Y/покупок-целей либо fitted state в тесте нет; буква P ниже означает только исторический purchase action.

| occurrence | action | valid_at | known_at |
|---|---:|---:|---:|
| e1 | V | 1 | 1 |
| e2 | V | 2 | 3.5 |
| e3 | C | 3 | 3 |
| e4 | C | 4 | 4 |
| e5 | V | 5 | 5 |
| e6 | P | 6 | 6 |
| e7 | C | 7 | 7 |

При T=10 все семь уже известны. Behavioral sequence — **VVCCVPC**, `A_VC=5`: вклады трёх C равны1,1,3. Arrival sequence — **VCVCVPC**, `A_VC=3`: вклады C равны−1,1,3. В обоих вычислениях V3/C3/P1, последний V5/P6/C7, один user/item и одинаковые поддержка/обычные counts/последние action recencies. Поэтому проверка только commutative aggregates и последних recencies пропустит ошибку order-sensitive переноса.

При T=3.25 корректно доступны e1/e3: V1/C1/P0, `A_VC=1`. Event-time-only читатель дополнительно берёт ещё не известный e2: V2/C1/P0, `A_VC=2`. При T=3.5 e2 всё ещё исключён нашим strict known_at<T; данные ровно на query peer не продвигаются заранее. Таким образом, простая замена одного имени колонки не исправляет оба вида ошибки.

**Проверяемое предсказание / counterprediction.** Если prospective HYP-142 implementation различает clocks и сохраняет occurrence order, следующие девять tuple-клеток получатся без ремонта после открытия gold. Если же текущая source policy честно объявляет только event-time offline assumption, она не должна автоматически выдавать тот же strict-knowledge claim для двухclock-источника. Контргипотеза к новизне: прежние late-event conformance и path witnesses уже выражают всю эту композицию, тогда достаточно объединить literal witness с существующей записью и ничего не реализовывать. Контргипотеза к необходимости двух clocks для конкретного источника: verified source contract гарантирует known=valid; этот специальный случай допустим с явным основанием, а не как универсальное следствие schema equality.

| Политика расчёта | T=3.25: (V,C,P,A) | T=3.5: (V,C,P,A) | T=10: (V,C,P,A) |
|---|---|---|---|
| declared strict known+valid selection; valid bucket order | (1,1,0,1) | (1,1,0,1) | (3,3,1,5) |
| ошибочно valid-only selection/order | (2,1,0,2) | (2,1,0,2) | (3,3,1,5) |
| ошибочно known-only selection/order | (1,1,0,1) | (1,1,0,1) | (3,3,1,3) |

Это ровно семь literal occurrences × три query cuts, девять ожидаемых value tuples для трёх явно различных определений; неправильные arms — negative controls, не допустимые альтернативы одного estimand. Дополнительно две metadata-only verdict-клетки: (1) запросить strict-knowledge перенос при неизвестном known clock → **UNSUPPORTED/NOT_READY**, без invented zero или silent fallback; (2) передать area AST существующему frozen count/distinct/recency generator → **REJECT unsupported operator**, пока отдельное расширение не принято. Последняя клетка — ожидаемое текущее поведение, не production bug. Закрывать clocks через унаследованный offline assumption можно лишь с заранее другим claim/identity; row-by-row fallback или выбор по quality недопустимы.

**Ближайший эксперимент и бюджет — ПРЕДЛОЖЕНИЕ, UNRUN.** Добавить ровно этот witness в будущий уже предусмотренный literal gate HYP-142, либо провести один независимый ручной пересчёт9 tuple-клеток и2 refusal-клеток без implementation. Oracle должен читать исходную literal table и policy, не normalized producer output. В первом маршруте допускается только маленькая list-arithmetic reference внутри того же gate, без project imports/SQL/backend/нового adapter framework. Предложенный конечный предел: ≤10 CPU секунд /20 wall секунд, 1 thread,128MiB RSS и64KiB output, не более одного запуска; подготовка+review ≤20 person-min. Фактические затраты и достаточность лимитов **UNKNOWN**, это не измерение и не выданный runtime. Artifact: один keyed verdict/value JSON плюс короткое независимое review с исходными таблицей, policy и неизменённым gold. На текущей волне всё это не запускалось.

**Accept/reject/stop.** Принять лишь finite conformance refinement, если независимое review подтверждает все9 tuple-клеток, strict equality boundary и2 capability refusals; expected negative controls должны расходиться ровно в указанных местах. Если extended implementation выдаёт arrival-order area или знает e2 раньше времени, отклонить её перенос до исправления с сохранённой исходной ошибкой. Если первичные данные устанавливают known=valid, сузить этот источник до специального подтверждённого контракта. Если это полностью покрыто прежним literal suite, outcome=MERGED/no new task. Недостаток лимита или инфраструктурная ошибка → INCOMPLETE, без retry и без PASS; новый запуск сначала должен иметь объяснение причины и отдельный конечный контракт Root.

**Польза исходной Task1 / граница решения.** Это дешёвый различающий test для честной переносимости примитивов: он показывает, почему прежняя byte/value parity и counts не доказывают корректность нового order-sensitive оператора на иной observation schema. Он не обещает NDCG gain, не меняет основной выполненный feature pipeline и не делает cross-dataset implementation обязательным. Новую ветку стоит открывать только если Root действительно берёт HYP-142 в реализацию или формулирует переносимость order primitives; до того — сохранённый контрпример, а не растущая execution очередь.

## Дедуп и состояние доказательств

- HYP-142/FB-01 уже содержит семь-event nonalias, unordered peers, rolling expiry и legal nonidentity shuffle. Эти проверки не объявлены моими новыми идеями; добавлен только конкретный composite clock/order witness и место его слияния.
- Existing transfer-adapter-conformance уже разделяет feature/protocol/access compatibility, late availability, historical categories и known-empty. Wave085 Diginetica требует clock origin;088 — layout/bag equivalence;093/094 — censored published counts и units. Они сохраняются, второй аналогичный schema-adapter proposal здесь не создаётся.
- HYP-087/088 остаются reserved согласно existing candidate-generation review; никакой номер не переиспользован.
- Root сообщил при dispatch: current15 принят по75 byte-identical exports из той же processedDB. Это узкая parity, а не новый raw import/formula oracle/quality/available-at proof. Сам автор не проверял фактические75 data bodies. Датированный top-backlog во время чтения ещё помечал current15 UNRUN; live dispatch не переписан мной в canonical документы.
- Seed2027 отрицательный; исторический final и его CI не меняются. Этот SOURCE-only witness не даёт никаких новых ranking measurements или third-seed rationale. Root остаётся единственным координатором/canonical writer/publisher.

Freeze: отдельный JSON фиксирует bytes/hash FIRST и input pins; после него автор останавливается до отдельного поручения Root. Независимость относится к текущей волне100, не к незнанию исторического журнала. Next_due остаётся10:30UTC.
