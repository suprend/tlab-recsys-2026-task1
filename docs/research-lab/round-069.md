# Round069 — как подписать bootstrap016 после выбора W

**Focused report addition, 15 октября2026.** Проверены frozen [selector](../experiments/feature-program-selection.md), actual [metrics006](../../scripts/ranking_metrics.py), published small-support review и rounds019/054/059. Новых data/model/metric reads, resampling, fits, tests или policy изменений нет. Calendar25/reporting-only и26–31 используется как поставленная prospective policy, не как подтверждение готовности driver/config/holdout execution. Число positive heldout queries неизвестно.

## Точный объект uncertainty

Primary contrast — conditional query-macro fullY NDCG@20(W)−NDCG@20(B), W выбран из B+I1/I2/R1/R2 замороженным правилом. Recall feasibility, global band, physical/lexical tie и failures остаются прежними. Две I против двух R — descriptive screening, не второй confirmatory primary. Если W=B, contrast тождественно0; нельзя заменить его понравившимся проигравшим arm.

006 resamples **всех mature users**, включая zero-only users, и переносит все daily queries пользователя одной кратностью kᵤ, общей для W/B. Для conditional query macro разность строится из `Σkᵤsᵂᵤ/Σkᵤnᵤ − Σkᵤsᴮᵤ/Σkᵤnᵤ`, где nᵤ — число nonempty-Y queries пользователя. Это не среднее пользовательских средних. Empty-C positive-Y query даёт miss; Y вне C остаётся в denominator/IDCG. Censored Q не negative. Draw без positive support undefined, не перерисовывается; percentile interval использует только defined draws.

[Field–Welsh2007](https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-9868.2007.00593.x), проверено также по [paper text](https://bemlar.ism.ac.jp/zhuang/Refs/Refs/field2007jrssb.pdf), связывают свойства cluster bootstrap с моделью clustered data. Это не blanket theorem для sparse ranking ratio. Наша ограниченная inference требует правдоподобной exchangeability пользователей и относится к fitted pipelines/cohort/наблюдённым датам. Common day/catalogue shocks, новые model seeds, переобучение/retrieval и выбор программы внутри draws не моделируются.

Повторность пользователей25–31 сохраняется внутри cluster, но семь календарных дней не становятся семью независимыми replications. Пользовательская bootstrap population может быть большой при малом числе positive users.73positive development queries не доказывают power/95%coverage и не определяют support будущего периода.

## Почему seed и200draws не решают выбор модели

[Cawley–Talbot2010](https://jmlr.org/papers/v11/cawley10a.html) показывают переобучение finite-sample selection criterion; [Varma–Simon2006](https://pmc.ncbi.nlm.nih.gov/articles/PMC1397873/) различают оценку оптимизированной процедуры и минимум того же CV. Development CI для уже выбранного W условен на принятом winner и не включает поиск по четырём programs,019 checkpoints и ранее просмотренному incumbent. Ни ограниченный search cap, ни точный replay не делают его selection-adjusted или simultaneous CI для всей семьи.

После **реального** model/program/decision lock до открытия reserved query-level targets heldout W−B уже является заранее определённым contrast. Development multiplicity не требует объявлять любой heldout результат недействительным. Но его interval всё ещё условен на этих fitted models/dates и bootstrap assumptions; история human design/whole-month EDA раскрывается, не переименовывается в полностью data-blind исследование. Reporting-only25 не может выбирать новый W/prefix/population либо менять26–31; нельзя выбрать для headline только тот из двух окон, где sign удобнее.

[Hesterberg, author text §3.6](https://arxiv.org/html/1411.5279) отделяет data sampling uncertainty от Monte Carlo variability bootstrap. При200defined draws implementation lower quantile2.5% интерполирует позиции4.975 zero-based sorted samples; upper97.5% —194.025. Это собственная арифметика определения006, не новые выполненные replicates: endpoints опираются примерно на пять tail draws. Seed2026 фиксирует одну approximation при том же ordered user universe/Python behavior; он не повышает statistical support. Меньше defined draws означает ещё меньшую эффективную resolution. Никакого увеличения replicates/смены CI здесь не предлагается.

## Один literal counterexample: positive CI без strategy proof

Два mature пользователя u1/u2, одна query у каждого, C={x,y}, fullY содержит один item. Четыре **заранее фиксированных prediction patterns**, не утверждение о реализуемости конкретных legal AST, задают первый item:

| Pipeline | u1 first | u2 first |
|---|---|---|
| B |x|x|
| I1 |x|x|
| I2 |x|y|
| R1 |y|x|
| R2 |y|y|

Пусть наблюдённые development fullY обоих пользователей={y}. Тогда R2 имеет NDCG20=1 на обеих queries, B=1/log2(3), а Recall20 всех равен1: guard ничего не исключает. Winner R2, каждый user difference `a=1−1/log2(3)>0`. Любой парный bootstrap этих двух clusters даёт a;200draws дали бы percentile[a,a]. Это аналитическое следствие таблицы, **не запущенный bootstrap**.

Теперь зададим возможный data-generating mechanism: на новом дне target каждого того же пользователя — независимая fair coin x/y, недоступная фиксированным scorers. Каждый fixed pattern и B имеют одинаковую ожидаемую NDCG; true future expected contrast R2−B=0. Positive development CI не доказывает future/strategy superiority. Пример также показывает малую-sample degeneracy; он не оценивает реальный false-positive rate при73queries. Выигравший R2 тем более не доказывает преимущество rule-guided I. Не предлагается менять selector или отзывать корректный observed score.

## Готовый reporting template

> «W=[sealed identity/slot либоB] выбран на development22–23 по заранее закреплённому B+4 правилу. Development conditional NDCG20/Recall20=[values], positive support73queries; история0194fits/12dependent prefixes+seen incumbent и016consumed/completed slots раскрыта. Development paired CI — screening после выбора, без adjustment за search».
>
> «Для reporting-only периода[25 либо26–31] проверены[seals/terminal proof]. На одинаковых[Q/C/fullY identities], при[Q mature/censored,users,positiveQ/positiveusers,targets,emptyC/outC counts из existing report], frozen W−B conditional query NDCG20=[Δ], nominal percentile user-paired interval=[L,U],200draws,seed2026,undefined=[count],ordered-user/input versions=[refs]. Interval описывает user variation условно на этих датах и fitted pipelines; не training/seed/time/search-policy variation. После25 никаких адаптаций/рефитов/смены primary».

При L>0 допустимо сообщить положительный nominal fixed-contrast interval с этими ограничениями, не «95%вероятность универсального превосходства». Crossing0 означает неопределённость, не equivalence; отрицательный point не означает universal harm. Practical magnitude и sign interval различны; frozen016 point selector не заменяется CI promotion. Unknown/invalid/resource-partial proof — отдельный outcome, не нулевой gain. Для31Oct/H24 full horizon требует покрытия до1Nov и label maturity; missing coverage не заполняется negatives.

Это готовая вставка existing report/evaluation015/006/016 scopes. **No new task/HYP/looks/caps:** поля support берутся из уже обязательных evidence; новые slices, seeds, p-values, bootstrap или holdout reselection не нужны.
