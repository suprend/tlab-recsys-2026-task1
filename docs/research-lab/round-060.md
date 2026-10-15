# Round060 — fixed-learner feature contrast и совместная настройка: разные вопросы

**Первичные источники и прикладная интерпретация, 15 октября2026.** Продолжает [059](round-059.md) и подробный [OpenFE source trace053](round-053.md). Проверены papers ExploreKit/DFS/OpenFE, public reproduction evaluation script и методология nested evaluation. Никаких новых моделей, тестов, данных или metric looks. Current016 policy не меняется; формулы и примеры ниже аналитические, не measured results.

## Требует ли опубликованная AFE-польза retuning каждого feature set?

Нет единого требования, и три близкие работы нельзя пересказать одной фразой «они настраивали всё совместно».

| Первичный источник | Реально заявленная процедура | Какой перенос недопустим |
|---|---|---|
| [ExploreKit2016, §IV.C,V.A](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf) | Wrapper evaluates candidate additions посредством k-fold CV; C4.5/SVM/random forest — Weka3.7 с default settings | Приписать gain joint hyperparameter search либо бесплатно перенести default learners на наш ranking |
| [OpenFE2023, §5.1–5.3](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf) | Общий train/validation/test split; LightGBM tuning на base features; одинаковая добавочная ширина для сравниваемых методов | Считать каждый expanded set отдельно оптимизированным либо равную ширину равным полным search cost |
| [DFS2015, §IV–VII](https://groups.csail.mit.edu/EVO-DesignOpt/groupWebSite/uploads/Site/DSAA_DSM_2015.pdf) | Data Science Machine объединяет synthesized features с параметризованной learning pathway и Gaussian Copula Process tuning | Отнести whole-system leaderboard результат исключительно к generation или фиксированному learner |

Для OpenFE доступный [author reproduction eval.py](https://github.com/ZhangTP1996/OpenFE_reproduce/blob/master/runs/eval.py), public master без установленного immutable SHA, копирует base tuned TOML для expanded data по seeds0…9, меняя data path. Это конкретное evidence переноса configurations. Оно само по себе **не доказывает** одинаковое фактическое число trees у downstream fits: nested executable может иметь early stopping/default resolution. Попытка дополнительно открыть его lightgbm_.py сейчас получила Internal Error; этот необследованный путь не объявляется проверенным. У016 сильнее явный contract: совпадают и trained iterations, и scoring prefix.

DFS показывает отдельно default и optimized pathway scores. Например, KDD2015 online AUC в TableII меняется.5000→.8621; авторы описывают трудность default setup и настройку нескольких стадий. Это measured system comparison на конкретной competition; нельзя вывести, какая доля прироста принадлежит features, dimensionality/selection, clustering либо forest settings. И тем более это не обещание, что дополнительный retuning спасёт любую нашу отрицательную добавку. Условия split/competition access отличаются от нашего frozen temporal experiment.

## Точный estimand016

Обозначим F₀ — accepted B41, A — три физические добавочные колонки, λB — замороженные **настройки процедуры**, а T — обучение с принятыми population/weights/seed/tree count. Тогда обучаются разные модели:

`f₀ = T(Dtrain,F₀;λB)`;
`fA = T(Dtrain,F₀∪A;λB)`.

Одинаковые λB не означают одинаковые learned weights, splits или predictions. Проверяемый contrast на конкретном evaluation population — `M(fA)−M(f₀)` при fullY, фиксированных C, key ties и scoring prefix. Это условная algorithmic intervention на представление входов; она не является causal lift от рекомендаций пользователям и не оценивает математическую «информационную ценность признака» независимо от learner.

В λB входят не только depth/L2: нужны принятые learning rate, loss, bootstrap/quantization settings, seed, iterations и все effective defaults. Перенести два написанных параметра, оставив остальные автоматически зависимыми от изменившейся схемы, недостаточно для утверждения о том же procedure. Это существующий parameter/schema verification gate, не новый config audit и не найденный runtime defect.

λB выбраны на ручном F₀, поэтому сравнение намеренно условно относительно хорошо определённого manual control. Оно может оказаться неудачным для A, но направление изменения качества без эксперимента неизвестно. Добавление колонки расширяет доступные split candidates; finite greedy optimization, regularization и quantization не обязаны воспроизвести старую модель или улучшить heldout score. Отсюда «новые признаки не могут ухудшить, модель их проигнорирует» — неверная гарантия.

[CatBoost tuning docs](https://catboost.ai/docs/en/concepts/parameter-tuning) отдельно связывают learning rate с необходимыми iterations и рекомендуют выбирать depth/L2 по задаче. Это обоснование возможного feature–learner interaction, а не theorem о необходимости нового tuning для каждой добавки. Сейчас параметры не меняются.

## Что оценивало бы joint/nested исследование

Иной вопрос: «Каково качество процедуры, которая для каждого набора сама выбирает λ в заранее ограниченном пространстве?» Здесь `λ̂A=Select(Dinner,F₀∪A)` и `λ̂₀=Select(Dinner,F₀)`; outer metric сравнивает обе **полные** процедуры. Отличие от fixed contrast включает эффект retuning и ошибки его выбора. Четыре existing016 fits нельзя переименовать в такую оценку; четыре019 fits не являются per-arm tuning credit.

[Varma–Simon2006](https://pmc.ncbi.nlm.nih.gov/articles/PMC1397873/) демонстрируют смещение минимального CV error после настройки и оценивают selection algorithm во внешнем цикле, повторяя настройку внутри каждого outer training partition. [Cawley–Talbot2010](https://jmlr.org/papers/v11/cawley10a.html) рассматривают overfitting selection criterion шире. Следствие для будущей temporal задачи: повторяться должны доступные по времени generation/feature selection/tuning/checkpoint decisions, а не только refit уже однажды выбранных winners. Обычный random nested CV не получает causal/history guarantee автоматически.

Если такой вопрос когда-либо станет приоритетным, сначала нужен **отдельно бюджетированный** protocol: одинаковые inner search opportunities для F₀ и заранее объявленных добавлений, fit/look/cost ledger, chronological outer evaluation, label maturity и positive compute gaps, заново frozen decisions до outer targets. Можно перераспределить будущий бюджет от числа feature variants к tuning; нельзя сохранить все нынешние arms и считать дополнительную настройку бесплатной. Ни численного allowance, ни нового task здесь не предлагается; текущее heldout reporting-only правило запрещает превращать открытый результат в tuning feedback.

## Практическая формулировка и no-add outcome

«Мы измеряем действие ограниченной автоматизации признаков при неизменной принятой процедуре обучения ручного контроля. Выбор W выполняется один раз из B и четырёх additions по замороженному правилу; это не совместная оптимизация feature/learner и не сравнение всех возможных AFE algorithms».

Positive Δ поддержит именно этот bounded recipe; negative/undefined Δ не докажет бесполезность grammar, отсутствие signal либо успешность гипотетического retuning. Результат development winner остаётся screening; независимый heldout может оценить frozen choice при заданных датах, но не всю распределённую search strategy. Две I и две R реализации не доказывают превосходство intelligent search.

Отдельная tuning study была бы новым estimand, стоимостью и access protocol. Backlog уже различает strong019, fixed016 и будущие learned-search ветви. **No new HYP/task:** достаточно report wording и существующих lifecycle/parameter/heldout gates. Заканчивать воспроизводимый текущий experiment приоритетнее расширения grid ради более удобного исхода.
