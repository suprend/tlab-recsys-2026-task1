# Research lab, round 005: что можно доказать при малом purchase support и адаптивном поиске

15 октября 2026. Первичные статьи проверены; выводы предназначены для исполнения TLAB-008/016, без нового метода или увеличения бюджета. Прочитаны [backlog](../backlog.md), [boosting plan](../experiments/boosting-baselines.md), round001/002. Новые raw, scores, queries и test labels не читались; код/Git/данные не менялись, обучения/установок/downloads datasets не было. Выполнены только элементарные вычисления по опубликованным агрегатам, без simulation или модельного эксперимента.

## Пять первичных оснований

**Gavin C. Cawley, Nicola L. C. Talbot, 2010, “On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation”.** Оптимизация шумного validation-критерия сама способна переобучаться; выбирать и оценивать победителя на одном наборе некорректно. Оценивать нужно комбинацию learning+selection procedure. Их nested-CV аргумент не означает, что нам бесплатно доступны дополнительные fits или допустим shuffled temporal split. Практический вывод: ledger включает выбор features, loss и checkpoint. [JMLR, §§4–5](https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf).

**Cynthia Dwork, Vitaly Feldman, Moritz Hardt, Toniann Pitassi, Omer Reingold, Aaron Roth, 2015, “The reusable holdout: Preserving validity in adaptive data analysis”.** Авторы предлагают механизм контролируемого доступа к holdout на основе differential privacy; это не разрешение многократно смотреть обычную точную метрику. [Первичная публикация Science / abstract](https://pubmed.ncbi.nlm.nih.gov/26250683/).

**Те же авторы, 2015, “Generalization in Adaptive Data Analysis and Holdout Reuse”.** Полный технический текст задаёт Thresholdout: сравнение train/holdout, шум, порог и расходуемый overfitting budget. Гарантии формулируются для i.i.d. holdout и контролируемого механизма ответов. Обычный bootstrap после выбора features таким механизмом не становится. У нас repeated users/time shocks и sparse conditional metric; готовые theorem constants переносить нельзя. Новый Thresholdout-компонент здесь не предлагается: он требует отдельной sensitivity/unit policy и реализации, не решает бесплатно недостаток поддержки. [Авторский текст, §4](https://arxiv.org/pdf/1506.02629).

**Avrim Blum, Moritz Hardt, 2015, “The Ladder: A Reliable Leaderboard for Machine Learning Competitions”.** Ladder выдаёт обновлённый округлённый результат лишь при достаточном улучшении; theorem предполагает i.i.d. observations и bounded loss. Существенная деталь: авторы прямо называют significance-test вариант эвристическим при adaptive reuse, без контроля multiple comparisons. Поэтому правило «принять, если очередной paired CI выше нуля» не получает гарантии Ladder. Полезный принцип — ограничить feedback и заранее зафиксировать выбор; формальный алгоритм сейчас не внедряется. [ICML, §§1.3,3,4](https://proceedings.mlr.press/v37/blum15.pdf).

**Christoph Bergmeir, Rob J. Hyndman, Bonsoo Koo, 2018, “A note on the validity of cross-validation for evaluating autoregressive time series prediction”.** Статья допускает стандартный CV при специальных autoregressive/uncorrelated-errors условиях. Это не универсальный запрет случайного CV и не оправдание его для наших user–item purchase labels. Условия не проверены; сохраняются глобальная хронология, зрелость labels и actual availability. [Авторский PDF](https://robjhyndman.com/papers/cv-wp.pdf), [publication metadata](https://robjhyndman.com/publications/cv-time-series/).

## Какая поддержка есть фактически

Source-reconciled TLAB-017: **train 26 000 Q /496 positive Q /619 full targets; selection 4 000 Q /73 positive Q /96 targets**. Counts сохранены в [backlog/017 acceptance](../backlog.md). Это support коллекций, не число реально использованных training positives: label-independent subset отдельного fit может быть меньше. Сотни тысяч candidate rows не дают столько независимых наблюдений ranking quality; target items одной query также зависимы.

Primary estimand сохраняется как conditional macro-query NDCG@20 по полному Y. Query с покупками, потерявшая все targets при retrieval, остаётся с NDCG=0; её нельзя удалить ради precision. По zero-convention all-query NDCG на этих же Q выполняется `M_all=(73/4000)·M_positive`. Поэтому conditional Δ=0,002 соответствует всего **0,0000365** all-query Δ. Большой all-query denominator не создаёт 4000 положительных ranking-сигналов. Другие zero-conventions и user-macro — отдельные estimands.

## Before-experiment precision: расчёт чувствительности, не обещание power

Пусть `Dq=NDCG_A(q)−NDCG_B(q)∈[−1,1]`. Для иллюстрации используем `n=73`, **предполагая независимые положительные queries и фиксированную до evaluation пару моделей**. Реальная SD парных различий, число уникальных positive users и support будущей confirmation неизвестны; её labels не открывались. Следующая таблица не оценивает actual variance по selection и не объявляет будущую выборку равной 73.

Нормальное приближение: `SE≈σD/√n`; half-width95%≈`1,96SE`; detectable Δ при 80% power двухстороннего α=0,05≈`(1,96+0,84)SE`. SD выбраны исключительно как sensitivity scenarios.

| Предполагаемая σD | Half-width95%, n=73 | Приблизительная detectable Δ, 80% | n для Δ=0,002 при тех же предположениях |
|---:|---:|---:|---:|
|0,05|0,0115|0,0164|4 900|
|0,10|0,0229|0,0328|19 600|
|0,25|0,0574|0,0819|122 500|

Эти числа — инженерная арифметика, **не запрос увеличить выборку/бюджет**. При почти одинаковых rankings σD может быть намного меньше; counts этого не определяют. Conservative fixed/i.i.d. Hoeffding для диапазона ширины 2 даёт half-width `√(2 ln40/73)≈0,318`. Bound слабый, но не требует угадать variance; он также неприменим напрямую к уже выбранному на selection победителю. Значение 0,002 — порог практической полезности, а не доказанная detectable величина. Selection variance после поиска можно описать, но нельзя выдавать за независимую prospective power verification.

## Исполнимый предел адаптации

Prospective strong tuning: **4 fits×3 объявленных checkpoints=12 metric looks**, не 12 независимых опытов. Контроль B выбирается внешним full-Y критерием; native best-model не подменяет выбор. Записать все looks, включая прежние smoke/manual-block решения на той же selection. Correlation checkpoints не делает просмотр бесплатным; простой Bonferroni по 12 также не исправит произвольно adaptive hypotheses с невалидными исходными p-values.

TLAB-016 остаётся **2 intelligent +2 random fits, ≤12 физических scalar columns суммарно, ≤4 fits, ≤2 CPUh**. Masks/supports и failed attempts входят в cap; 12 columns нельзя выдать каждому arm. Grammar/seed/proposer inputs/checkpoint rule и порядок feedback фиксируются до запуска. Frozen B scoring расходует время, хотя не новый fit. Validation-feedback proposer допустим только как зарегистрированная selection-адаптация, без confirmatory CI на той же selection. Неиспользованные/неудачные попытки автоматически не заменяются, поиск прекращается по заранее объявленному cap, а не при достижении significance.

Выбрать **один frozen primary claim**: автоматизированный победитель A против сильного B, одинаковые Q/C/Y/features-time semantics. Random-arm comparisons, days, repeat/novel и support slices — заранее перечисленные secondary diagnostics. Такой claim проверяет пользу полученных автоматизацией features; superiority intelligent search над random не следует из одного выбранного A−B. Для отдельного primary A−random потребовалось бы заранее иное распределение claim/бюджета, которого эта записка не разрешает.

## CI, stopping и трактовка результата

После freeze на действительно неиспользованной confirmation можно предложить paired **user-cluster bootstrap**: resample пользователей вместе со всеми их queries/днями, пересчитывая тот же conditional query-macro ratio. Не resample item rows и не заменять query-macro средним по user means. Число clusters/positive clusters, policy undefined replicates и seed/число repetitions фиксируются заранее. Такой CI требует правдоподобной exchangeability пользователей условно на наблюдённые дни; один пользователь в нескольких queries не создаёт независимые копии.

Selection содержит мало дней; confirmation25 — один prospective день. User-bootstrap не оценивает общий дневной promotion/traffic shock; два day-blocks не дают надёжной оценки распределения будущих дней. Публиковать day results как descriptive. Никакое число bootstrap repetitions не добавляет событий или устраняет selection bias. CI на selection остаётся screening-only; bootstrap всей повторно выбранной процедуры потребовал бы отдельных fit costs и temporal design, сейчас их нет.

Сохранить объявленный promotion gate: point Δ≥0,002, interval lower>0, Recall guardrail и cost/coverage gates. Это evidence положительного эффекта с point estimate выше practical threshold, **не** доказательство истинного Δ≥0,002. Если CI пересекает 0/порог — inconclusive, не «автоматизация бесполезна». Если upper<0 — evidence harm в заявленном estimand; если upper<0,002 — можно исключить практический минимум в рамках допущений CI, без доказательства равенства моделей. Resource exhaustion означает budget-limited/deferred; semantic failure — invalid experiment. После единственной confirmation не добавлять seeds/features/checkpoints ради успеха и не переносить границы уже раскрытого holdout. Отрицательные и неопределённые результаты сохраняются.

## Последний календарный gate

**Confirmation25 пока prospective/config-review**, не принятая новая reservation. При H24h labels25 становятся доступны26Oct00, когда может начинаться final26. Если B/A/claim уже заморожены и доступны до25 и заранее должны оцениваться на final26 независимо от результата25, сами старые модели не требуют нового fit/compute gap. Обновление past histories26 по зафиксированным правилам допустимо.

Если же результат confirmation25 определяет новую модель, refit, новую ветвь/claim или checkpoint для final26, это **новое решение**. Нужны actual metric availability→decision→compute→available_at строго до first final query; нулевого промежутка26Oct00 недостаточно. Нельзя выдать задним числом этот путь за frozen-model evaluation. Конкретное исправление chronology требует отдельного prospective reviewed config; эта записка не назначает принятую дату final и не читает его labels.

HYP-095/096 остаются reserved/unformulated. Ledger, freeze, power sensitivity и честное inconclusive reporting — уточнения исполнения существующих hypotheses, не новый feature-search механизм или академическая новизна. Для task1 полезный результат сейчас — воспроизводимый ограниченный search относительно tuned B с точно сформулированной силой доказательств.
