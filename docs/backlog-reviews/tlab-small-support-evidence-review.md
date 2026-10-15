# Focused evidence audit —73positive selection queries, tuning и016

15 октября2026. Уточнение существующих rounds019/027/034/042, не новая экспериментальная программа или HYP. Прочитаны опубликованные frozen019 design/backlog и actual evaluator006; ignored scores, модели, raw source и holdout targets не открывались. Новых computations, bootstrap replicates, fits, looks и budgets нет. Число positive holdout queries неизвестно.

**Главный вывод:** ограниченный заранее объявленный поиск делает эксперимент проверяемым, но не превращает reused selection scores в независимое доказательство generalization.73positive queries — фактическая поддержка conditional selection metric, не73новых trials и не универсальный порог достаточности. Нельзя честно вывести power или гарантированную точность лишь из этого count.

## Один prospective primary contrast

Для будущего reporting-only heldout минимальный объект вывода: `Δ = conditional macro-query full-Y NDCG@20(frozen016 choice) − NDCG@20(frozen019 B)` на одинаковых mature Q/C/fullY, с объявленной tie policy. Exact model/program IDs, training population, trained_iterations/scoringprefix, selection rule и primary estimand фиксируются до открытия heldout query-level Y. Остальные уже объявленные estimands/Recall guards остаются прозрачными secondary/support evidence; не становятся новым primary после неудобного результата.

Если selection выберет B как no-change candidate, итоговое deployed decision тождественноB. Нельзя затем найти «лучший непобедивший bundle» по holdout и назвать его primary contrast. Reporting-only confirmation/final не выбирает ни новый winner, ни seed, ни population, ни tree prefix. Конкретный календарь/label-blind prediction driver всё ещё требует отдельного принятия; здесь не утверждается, что current configs уже реализуют25-only policy.

## Что значит73

Published selection имеет4000matureQ/3995users/73positiveQ и73positiveusers. Conditional macro-query усредняет scores только positive queries; большое количество C rows не увеличивает независимую поддержку этого среднего. Аналитический, не измеренный пример: при73равновесных positive Q изменение суммарной query-score разности на0.146 меняет среднее на0.002. Это показывает чувствительность малой practical delta к нескольким ranking изменениям, но не доказывает, что реальный выигрыш обусловлен одной query.

Actual [paired_user_bootstrap](../../scripts/ranking_metrics.py) resamples всех mature users, включая zero-Y-only пользователей; одна кратность пользователя общая обеим моделям и всем его queries. Query-macro draw равен `Σkᵤsᵤ / Σkᵤnᵤ`, не среднему user means. Positive support holdout надо сообщить фактическим, а не перенести73из selection. Если positive denominator0, conditional estimand undefined; нельзя молча заменить его all-query-zero metric и сохранить старое название primary.

## Что interval покрывает и чего не покрывает

[Cameron–Miller](https://www.econ.ucdavis.edu/faculty/cameron/research/Cameron_Miller_JHR_2015_February.pdf) объясняют значение внутри-кластерной зависимости и предпосылки независимости между clusters. Их regression results не доказывают95%coverage данного sparse nonlinear ranking ratio. Здесь paired user interval разумно описывать как условную uncertainty по user clusters при фиксированных наблюдённых датах и уже fitted models. Он сохраняет парность, но не пересчитывает обучение, выбор B/AST или общий каталог.

User bootstrap не создаёт новые независимые дни, не моделирует общий day shock, другую source month или seeds. При двух selection днях и возможном одном confirmation дне нельзя назвать interval temporal generalization guarantee. Undefined zero-positive draws остаются None без redraw; interval только по defined draws и их число должны быть видимы.200repeats дают Monte Carlo approximation endpoints; fixed seed воспроизводит его, но не устраняет Monte Carlo uncertainty. [Hesterberg](https://arxiv.org/html/1411.5279) отдельно различает исходную sampling variability и конечное число resamples. Это не предложение увеличить текущий repeat budget.

## Repeated development looks

Frozen019 предусматривает четыре native fits, по три checkpoints50/150/300, плюс eligible incumbent: до12новых score alternatives и incumbent, а не12independent trained models. Общие300-tree trajectories делают checkpoints зависимыми.016 добавляет до4feature arms на том же development cohort; известные007/008/009 outcomes также часть history. Малое число fits не стирает многократное использование selection criterion.

[Cawley–Talbot](https://jmlr.org/papers/v11/cawley10a.html) показывают переобучение самого model-selection criterion; ordinary winner CI на тех же selection rows не включает selection uncertainty. [Dwork et al.](https://arxiv.org/abs/1506.02629) предлагают специальный controlled holdout-reuse механизм; fixed seeds, immutable logs и наш bootstrap его не реализуют. Нельзя считать13alternatives независимыми тестами или вывести из их числа точную familywise error без соответствующей процедуры. Здесь не предлагаются новые corrections, nested fits или дополнительные holdout looks.

## Разделить четыре исхода

| Наблюдение | Допустимый вывод |
|---|---|
| Valid complete contrast проходит frozen point/Recall/cost rule | Pipeline разрешён правилом screening; statistical/generalization claim ограничен stage и evidence |
| Point effect ниже practical gate, CI включает0 | Улучшение нужной величины не установлено; знак неопределён, эквивалентность не доказана |
| Point effect отрицательный | На этой cohort наблюдается снижение; CI/history определяют силу inference, слово «вреден всегда» недопустимо |
| Resource partial либо semantic/lineage fault | Budget-limited либо invalid/STOP; это не отрицательная оценка полезности признаков |

Ранее обсуждённое `pointΔ≥.002 AND lower95%>0` не доказывает `trueΔ≥.002`; оно не заменяет actual frozen promotion predicate.009/019 point screening и prospective016 decision policy должны цитироваться отдельно. При отрицательном valid016 результате сохраняется evidence реализованной generation/correct calculation, но claim превосходства tuned B не получен.

Предлагаемая краткая формулировка отчёта: «Winner выбран на development с известной историей до12checkpoint alternatives и четырёх feature arms. Основной heldout contrast заранее закреплён; paired user interval условен на наблюдённых датах и fitted pipelines и не учитывает tuning variability. Поддержка, undefined draws и все failed attempts указаны. Confirmation/final только сообщают результат замороженного решения». Дополнительно нужны уже доступные aggregate support/cost/tie/history сведения, а не новые scans или metric looks. Фиксация до открытия targets обязательна для prospective формулировки; после открытия невозможна её ретроспективная имитация.
