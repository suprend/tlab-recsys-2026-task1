# Round014: availability решения и переносимый experiment lock

15 октября2026. **Research/design-only:0scans/fits/benchmarks, без code/repo/approval changes.** Прочитаны актуальные [backlog](../backlog.md), [task1 requirements](../task1-requirements.md), rounds[005](round-005.md)/[010](round-010.md)/[011](round-011.md)/[013](round-013.md), accepted017phase schema. Ни25-only confirmation, ни новый бюджет этим документом не утверждаются. HYP113/114 остаются reserved: refinement существующих execution/002/046/015 obligations, без нового quality mechanism.

## Четыре первичных основания

**Ji et al.** показывают, что per-user leave-last-out может обучать recommender на взаимодействиях других пользователей из будущего относительно test query. Их timeline scheme требует использовать модель и items, доступные на соответствующем global time. Статья обосновывает temporal gate, но не задаёт наш purchase horizon, compute delay или schedule. [Авторский текст, §7](https://arxiv.org/pdf/2010.11060).

**Kaufman et al.** определяют leakage через информацию, нелегитимно доступную для поставленной prediction-задачи, и предлагают learn–predict separation. Здесь проверен abstract на странице учреждения авторов; полный technical proof не использован. Следствие для нашего contract: event time сам по себе не удостоверяет available time. [TAU primary publication record](https://cris.tau.ac.il/en/publications/leakage-in-data-mining-formulation-detection-and-avoidance/).

**Cawley–Talbot** показывают overfitting самого model-selection criterion и subsequent evaluation bias. Поэтому feature block, population, objective, checkpoint и threshold decisions входят в selection history; обычный CI выбранного победителя на той же selection не становится независимым подтверждением. [JMLR](https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf).

**Dwork et al.** дают controlled holdout-reuse mechanism с ограниченным feedback и предпосылками распределения. Наш immutable lock такого механизма не реализует: он ограничивает процедуру и делает её audit-able, но не превращает repeated exact metrics в безопасный reusable holdout. [Авторская работа](https://arxiv.org/pdf/1506.02629). Эти основания продолжают005; новая практическая часть ниже — dependency chronology lock, не новый статистический метод.

## Фактическая календарная граница017

[Selection](../../configs/development/selection.json) имеет anchors22–23Oct и labels available_before24Oct00; [confirmation](../../configs/development/confirmation.json) начинается24Oct00. `validate_phase_set` допускает равенство этих границ. `authorize_phase_execution` проверяет checkpoint `available_at≤frozen_before≤first_query`; documentation прямо оставляет actual selected-decision availability будущему runtime. Accepted017 не объявлял selection победителя завершённой. [Code](../../scripts/development_collection.py), [scope](../experiments/development-collection.md).

Таким образом, существующая схема достаточна для своего accepted planner/collection scope, но не доказывает готовность нового019/016решения к24Oct00. Даже reused checkpoint, доступный22Oct, может быть выбран только после получения selection outcomes. Prospective25-only — возможная отдельная calendar amendment, ещё не принятая и не гарантирующая достаточного compute budget/support.

## Точные inequalities — предлагаемые runtime obligations

Пустьa — label anchor, H — horizon, δ — заранее объявленная availability delay, F — fit-data cutoff, A — доступность fitted artifact, C₀ — first confirmation query.

- History сохраняет `event_time∈[t−W,t)`, availability проверяется отдельной policy. Для явно выбранного strict knowledge contract `available_at<t`; неизвестный ingestion lag остаётся offline replay assumption, не автоматически нулём.
- Для принятого right-open target `[a,a+H)` maturity кF означает `a+H+δ≤F`. Right-closed endpoint потребовал бы `<F`. Равенство допустимо для open target, потому что событие на его правой границе исключено. Это соответствует [temporal_contract](../../scripts/temporal_contract.py).
- Fitted artifact требует `F≤fit_start<fit_end≤A≤first_downstream_query`. Dependency artifacts должны быть доступны к началу своего использования; train-output model не обязан существовать до исторических anchors собственного training set. Данные feature-строк всё равно вычисляются по их as-of contract.
- Обозначим `S=max(a+H+δ)` по selection anchors; metric report готов вR, решение вD, immutable lock вL. Требовать `S≤R≤D≤L≤C₀` и **`L>S`** с объявленным положительным compute gap. R/D/L включают evaluation, выбор, serialization/review/sealing; нулевая стоимость не предполагается. Одного старого model A≤C₀ недостаточно.
- Если после выбора нужен refit, все его inputs/зрелые labels доступны кfit_start; `max(D,input_available)≤fit_start<fit_end≤A_refit≤C₀`. При включении selection labels дополнительно `F_refit≥S`. Refit policy, population и параметры фиксируются до confirmation, без её outcomes.

Это две шкалы: historical replay timestamps2019 и actual audit execution timestamps2026. Machine mtime не доказывает readiness в2019; backdated JSON также ничего не подтверждает. Replay availability обосновывается declared data/delay/compute policy и dependency evidence, actual audit — измеренным исполнением/порядком доступа. Их нельзя подменять друг другом или объявлять offline replay реально состоявшимся online deployment.

## Portable lock без нового framework

Предлагается один versioned decision manifest, проверяемый существующими hash/schema principles:

| Обязательство | Что связывает lock |
|---|---|
| Data/protocol | Exact phase/Q/C/fullY identities, source/config/code/lock pins, endpoints/δ/coverage |
| Selection history | Все008/009/019/016looks, timestamps открытия evidence, failed/unattempted choices |
| Выбор | Retention009 predicate, eligible incumbent, GridC/tie/Recall policy, выбранные schema/population/checkpoint |
| Automation | Typed AST/physical closure/masks/supports, proposer inputs, seeds,2I+2R/no replacement, exact winning B settings |
| Chronology | S/R/D/L и fitted availability, dependency digests, declared compute gap/refit policy |
| Confirmation/final | Единственный frozen claim/branches, evaluator/ties/estimand, access policy и immutable consumed state |

Hashes удостоверяют байты относительно внешних ожиданий; producer не выдаёт собственное approval. Изменение source/config/model/schema/decision policy требует нового reviewed identity, не silent reseal. Runtime должен предотвращать повторные попытки через новый outputroot; failed attempts и cost ledger не исчезают. Новые исследования после freeze записываются в future development, использованный holdout не переоткрывается.

## Четыре synthetic counterexamples

**Open endpoint:** anchor23Oct00/H24h/δ0 зрел к24Oct00; purchase ровно24Oct00 не входит вY. Это maturity, ещё не готовый metric report/decision.

**Старый model, новое решение:** A=22Oct, S=24Oct00, scoring+selection+seal занимают60секунд. L≥24Oct00:01:00, поэтому C₀=24Oct00 недопустим, хотя старый017checkpoint timing проходит.

**Позднее поле:** event20Oct, available24Oct, query22Oct. Event-time predicate проходит; strict knowledge gate не проходит. Whole-file source hash не делает поле доступным раньше.

**Confirmation→final:** hypothetical25-only labels зрелы26Oct00. Если они выбирают новую ветвь/refit для final26Oct00, снова нулевой decision gap. Если обе модели и final-evaluation policy уже заморожены до25 и final выполняется независимо от confirmation результата, нового выбора нет; causal history updates по frozen rules допустимы.

## Цена поздней фиксации

Whole-month EDA/schema inventory и source hashing раскрываются отдельно от held-out query targets/metrics. Hash не читает ranking quality; полный source inventory не разрешает future priors/catalog backfill. Опубликованные агрегаты EDA означают известный development context, поэтому абсолютную информационную blindness заявлять нельзя. Новая policy после просмотра009/019results prospective только для следующих неизвестных результатов; история просмотров сохраняется.

Поздний freeze сокращает доступное calendar пространство и может оставить confirmation infeasible/результат screening-only. Сдвиг anchors, новый holdout или refit требуют отдельного решения и cost evidence, без бесплатного rescue.019→016 наследует точный winning pipeline без incumbent refit;015 фиксирует финальное решение до test access. Эти lock obligations не исполняют новый run, не добавляют metrics/budgets и не утверждают25-only schedule.

## Explicit two-clock clarification после исходного вывода

Coordinator уточнил границу без отмены finding: **physical model files не обязаны были существовать в2019**. Dataset/simulated availability используетOctober2019; actual execution/audit —October2026. Actual model/decision artifacts sealed+hashed **до открытия reserved query targets сейчас**. Physical log доказывает этот порядок доступа, не deployment2019. Simulated `decision_available_at≥max_used_label_maturity+positive_compute_allowance` и **`decision_available_at<first_confirmation_query`**; dependency fit/availability times согласованы. Declared allowance обосновывается policy/измеренной стоимостью, не backdated mtime. Это уточняет более слабое≤отношение existing017schema и таблицы выше для нового decision runtime.25Oct здесь только пример prospective amendment, не утверждённый schedule/разрешение. Исходный zero-gap finding сохранён:24Oct00→24Oct00 не оставляет compute allowance ни в одной корректной интерпретации.
