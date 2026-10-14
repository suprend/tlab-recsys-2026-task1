# Round003: независимая критика schema budget и следующего execution proposal

15 октября 2026. **Вердикт: принять round003 как уточнённый DESIGN HYP-002/TLAB-016 с обязательными поправками ниже; execution budget не одобрен.** Старое предложение «3 intelligent variants +1 random» rejected. Принятый дизайн — **2 intelligent +2 seeded random, ровно3 фактические новые physical columns на arm**, единый legal pool, максимум одна попытка целого bundle на arm. Нового HYP, отдельного бюджета или доказанного quality gain нет. Проверены round003, prospective strong-control proposal, [предыдущие reviews](round-001-review.md)/[round002](round-002-review.md), [backlog](../backlog.md), actual005 compiler/registry и004 retrieval semantics. Repo/Git/dependencies/raw/model artifacts не менялись; training/downloads/production не выполнялись.

## Actual schema gate пройден на synthetic005

SHA actual [compiler](../../scripts/manual_features.py) `e2558299783a04aba34432fe72c0e7e16e6ddbcbfd074bdf18e8b09eae224103` и [manual18](../../configs/features/manual-18.json) `44587dd2106ab9bbfc9ec1faa0c496703969ca401894eea73f84a93700b41d9c` совпали с round003. Независимо выполнены четыре tiny in-memory materialization через accepted005 на существующем synthetic fixture:2 queries/11 candidate pairs, threads2/memory2GB. Все четыре завершились; exact Q×item keys сохранены. Это verification фактического schema delta, без полного semantic oracle новых программ и без cost экстраполяции на production.

| Bundle сверх pinned manual18 | Actual новые columns/types |
|---|---|
| pair cart24h +item cart24h +item purchase168h | 3 BIGINT |
| pair cart observed recency +item cart24h | DOUBLE recency +BOOLEAN missing +BIGINT count |
| pair cart72h +item cart72h | 2 BIGINT +DOUBLE source_coverage_72h |
| user_category cart168h +его share, existing user_cart7d denominator | BIGINT numerator +DOUBLE ratio +2 BOOLEAN missing |

Все четыре примера в round003 верны. Ratio bundle стоит4, поэтому не входит в three-column arm. Count в известном пустом ключе —0; NULL category, отсутствующая recency и нулевой denominator сохраняют missing. Новое окно coverage считается один раз в physical schema данного bundle; существующие24/168 coverage бесплатно не создаются заново. Бюджет включает dependency/flag/coverage, даже если model-input subset впоследствии исключит колонку. Для честного сравнения дополнительно фиксировать одинаковую policy передачи generated physical columns модели; иначе три materialized columns могут означать разное число доступных model inputs.

Supported grammar действительно уже proposed nested HYP-011/045: observed recency без числового window, count/distinct1…744h, только два совместимых matching-count shares. Whitelist24/72/168 — ограничение предлагаемого поиска, не ограничение validator. Unsupported arithmetic/mean-of-popularity нельзя объявлять исполненным registry005. Historical event category и latest global strict-past metadata без older-clean backoff сохраняются, raw duplicate events остаются raw counts.

## Material поправка1: dedup должен охватывать весь frozen B

Round003 удаляет manual duplicates, но prospective example `itemdistinctpurchaseusers7d` уже содержится в [004](../../scripts/candidate_pilot.py#L61) как `popularity_distinct_users`. После union этот столбец присоединяется из **полной** таблицы past popularity, не только top200; recent-only candidate также получает тот же count либо0. При accepted168h и тех же keys/NULL policy новая программа не добавляет новую информацию относительно retrieval/context input B.

Следовательно, grammar pool обязан canonicalize/dedup против полного frozen model-input manifest: manual core, masks/supports/coverage, retrieval/context и принятых009 additions. Одного сравнения с18 registry entries мало. Duplicates до pool freeze исключаются симметрично; попытка, выданная proposer после freeze и оказавшаяся invalid/duplicate, расходуется без replacement. Наблюдаемая коллинеарность на100 queries не заменяет semantic equivalence. Distinct grouping-key indicator не приравнивать raw count; имена features не определяют semantics. Это исправление legal space, не расширение бюджета.

## Material поправка2: единственная policy attempts вместо оставшихся трёх вариантов

Старый execution proposal сохраняет «3variants×4newcolumns +1random» и альтернативную nested/support ветвь. Эти варианты не эквивалентны принятому дизайну и не должны оставаться исполняемой настройкой. Canonical amendment: I1/I2 seeds1601/1602, R1/R2 seeds1603/1604; каждый делает **один seeded draw целого bundle** из заранее замороженного полного pool, затем максимум один fit. Это четыре proposal attempts; не три candidate attempts внутри каждого arm, не best-of-many и не sequential replacement до получения трёх хороших columns.

Для pool P intelligent law ровно pI(b)=w(b)/ΣP w, random pR(b)=1/|P|. Все веса положительны, поэтому support совпадает. Формулу w=1+n(cart/purchase core programs)+n(pair/item core programs) считать по уникальным canonical core AST nodes, не именам, repeats, flags или coverage. Pool ordering, canonical bundle identity, PRNG algorithm/version и sampling independently-with-replacement между arms фиксируются: одинаковый seed без этих деталей не воспроизводит draw. Cross-arm collision сохраняется, уменьшает unique fits, не разрешает refill. Так тестируется слабый domain prior, не superiority обученного интеллекта.

Общий cap остаётся≤12 new physical columns/≤4fits/≤2CPUh с CPU user+system всех процессов, wall120min, threads2/RSS8GiB. Oracle/setup/materialization/failed attempts/repair/scoring/confirmation внутри cap. Новый B или selector не получает бесплатные fits. Разбиение20/30/60/10min — proposal ledger, не измеренная выполнимость; label-independent100Q pilot не устанавливает global scan cost.

## Сильный B и009 обязательны до quality comparison

Первичный confirmation contrast winner−**frozen tuned B** корректно исправляет ошибку B+S из round002. Контрпример остаётся полезным: B=.100, B+S=.090, treatment=.093 — успех против support не качество выше B. B+S допустим только diagnostic/control при заранее оплаченных fits; не подменяет primary B и не добавляется пятым arm.

Но следующий execution proposal пока перескакивает actual009 metadata/block gate. Canonical009 blocked после008; ещё нет принятой counts→distinct/recency→category-share paired table и окончательного model-input manifest. Сначала008 code/accepted collections/bounded smoke, затем reviewed009 block/metadata policy, после этого отдельный prospective strong tuning на окончательном baseline schema. Иначе изменение009 после tuning меняет B, pool/dedup и требует новой cost/identity регистрации. Initial2×50-tree smoke не strong tuned B.

Предложенные4 tuning fits×3 external checkpoints —12 selection looks, отдельный заранее зарегистрированный бюджет, не уже разрешённый запуск и не12 бесплатных checks. Full-Y006 criterion должен реально выбирать checkpoint, native candidate-only metric/OD его не заменяет. Training query cap6000 — provisional; rare-positive support, pairwise informative population и actual CPU/RSS требуют измерения. Все extension arms используют один frozen objective/population/params/trees/train seed; retuning каждого bundle вне дизайна.

## Chronology и источники

Текущий confirmation24Oct00 совпадает с selection-label availability24Oct00: решение не имеет доказанного positive compute gap. Предпочтение confirmation25only или selection22only — ещё proposal, не manifest change. До раскрытия нужны согласованный calendar, actual metric/model/decision availability и immutable timely lock; если gap не обеспечен, вывод screening-only. Final26+ закрыт; новый literature round не переоткрывает использованную confirmation. Winner selection среди четырёх arms допустим с заранее одним primary contrast; best-of-two I против best-of-two R остаётся screening,2 seeds не подтверждают superiority стратегии. Threshold ΔNDCG≥.002/CI lower>0/Recall guard — prospective, не измеренный успех.

Source claims проверены по первичным материалам. OpenFE §5.3 действительно настраивает LightGBM на base features и сравнивает одинаковое число новых features; перенос этого правила в наш budget — design inference, не доказательство результата. [Официальный PDF](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf). Featuretools1.31 документация подтверждает include priority и `[lower,t)` при include_cutoff_time=False; это не выполнение наших nested joins. [Options](https://featuretools.alteryx.com/en/stable/guides/specifying_primitive_options.html), [Handling Time](https://docs.featuretools.com/en/stable/getting_started/handling_time.html). Прежние DFS/ExploreKit/UCI source audits сохраняются; новых installs/downloads не требуется. Synthetic renamed schema с refund/NULL/conflicts/boundaries проверяет adapter compatibility, не statistical generalization.

**Следующий ready результат:** exact legal pool/closure/model-input manifest с2I+2R policy и independent semantic oracle. Quality execution ждёт008 acceptance,009 metadata/block gate, tuned B, resource budget и исправленной chronology. HYP-091/092 остаются свободными, nested/residual/LLM alternatives deferred внутри общего016 scope.
