# Research lab, round027: что покажет маленькое static-I/random сравнение

15 октября2026. Прикладное уточнение [pool026](round-026.md), [backlog016](../backlog.md) и retrospective chronology. Это design interpretation, не результаты imminent run. Read-only source research; compiler/Pool/fits/tests/scans и новые metric looks не выполнялись. Ни frozen код, ни budgets не менялись. HYP137/138 остаются refinements002/closure, новые IDs не нужны. Вероятности ниже — **собственная аналитическая арифметика**, без simulation и фактического random draw.

## Три первичных основания

[Bergstra–Bengio2012](https://jmlr.org/papers/volume13/bergstra12a/bergstra12a.pdf) обосновывают random search как воспроизводимый baseline для hyperparameter optimization и показывают преимущество перед grid при низкой effective dimensionality. Это не theorem, что две случайные попытки из восьми feature bundles достаточно сильны или репрезентативны. В статье возможность добавлять независимые trials/игнорировать failed trials обсуждается как практическое свойство random search; текущая no-replacement/no-refill policy016 **строже** и этим текстом не отменяется.

[Cawley–Talbot2010](https://jmlr.org/papers/v11/cawley10a.html) показывают переобучение finite-sample model-selection criterion. Winner среди четырёх вариантов не получает независимую оценку только потому, что seed фиксирован. [Dwork et al.2015](https://arxiv.org/html/1506.02629v2) дают controlled holdout-reuse mechanism с предпосылками и ограничением feedback. Наш ledger не реализует этот mechanism; точные reused selection metrics и обычный bootstrap не приобретают его guarantees.

## Конкретная probability law

026 предлагает общий sorted pool L01…L08, два различных static bundles I1=L02 иI2=L06 и два независимых uniform R draws с возвращением. Pool fixed до новых scores; R может выбрать I bundle либо повторитьR. Такой draw расходует slot, не даёт replacement/refit с другим seed. Для подсчётов предполагаются восемь legal distinct bundles, два успешно вычисленныхI и отсутствие resource/integrity failures. U — число различных выбранных bundles в объединении I/R; это не число completed models при реальной ошибке.

Каждый из шести не-I bundles попадает хотя бы в одинR с вероятностью `1−(7/8)²=15/64`. Поэтому `E[U]=2+6·15/64=109/32=3.40625`. Ожидаемое число различных R bundles само по себе `8·15/64=1.875`; новых относительноI —1.40625. Это разные знаменатели.

| Уникальных bundles U | Аналитическая вероятность |
|---|---:|
| 2: обаR внутри двухI | 1/16=6.25% |
| 3: ровно один новый distinct bundle | 15/32=46.875% |
| 4: два разныхR внеI | 15/32=46.875% |

R1=R2 имеет вероятность1/8; хотя бы одинR попадает вI — `1−(6/8)²=7/16`. Эти события перекрываются и не суммируются. Если ровноm из восьми bundles удовлетворяли бы некоторому **заранее заданному** quality predicate, шанс хотя бы одного такогоR равен `1−(1−m/8)²`. Сейчасm неизвестно: формула не является measured power или разрешением оценить все восемь. При resource stop вероятности completion меняются; таблица описывает proposals, не обещанные fits.

## Что означает fairness

У каждого slot одинаковый physical cap3 новых columns после masks/support/coverage closure; всего≤12 columns/≤4 fits/≤2CPUh. Три cores и recency+mask+count имеют одинаковую ширину, но различную информацию и стоимость. Duplicate R может дать меньше уникальных calculations/fits; это честный результат объявленного sampling law, а не повод «выровнять успешные попытки» redraw. Номинальные slots, distinct programs, actual new columns, completed fits и CPU показываются раздельно.

Common pool и одинаковый B обеспечивают сопоставимость **возможностей и ограничений**, а не автоматически равное observed compute I/R. Shared cache/preparation оплачиваются один раз с видимой attribution; validation/hash/read не бесплатны. Fixed execution order и cumulative budget могут оставить позднийR unattempted. Такой partial comparison нельзя интерпретировать как победуI над ресурсно недоступнымR. Для совпавшего bundle можно сослаться на тот же verified pipeline/result при reviewed reuse, но это не второе независимое качество или бесплатная новая попытка. Отдельный fit ради seed variability запрещён.

## Label-free evaluation не означает blind proposer

Core counts/recency вычисляются без labels и strict-past для каждой training query. Но автор static choices уже знает007/008 результаты,009 design/source decisions и после завершения может знать009 retention;019 выбирает B по development. Это человеческий semantic prior и adaptation history. Удаление numeric scores из proposer JSON не делает его независимым от этой истории. L02/L06 фиксируются относительно **следующих** неизвестных016 results; pool не выдается за найденный без человеческого знания.

I не обучает метамодель, не выполняет OpenFE probes и не является универсальным intelligent search. Здесь automatic component — воспроизводимое typed enumeration/dedup/closure, fixed priority selection и correct calculation. Model/scaler/proposer availability не backdated к старым training anchors. Исторические primitives используют `<anchor`, а019→016 decision остаётся retrospective development; confirmation требует отдельного positive compute gap и actual2026 seal до открытия reserved targets, без утверждения25-only schedule.

## Prospective reproducible selection и wording

Предлагаемый lock до новых016 scores связывает final019 B/input/settings/checkpoint, exact pool/AST/closure SHA, I1/I2, ordered PRNG/version/state/seed и два draws, execution order, source/oracle gates, caps и failed-slot policy. Никаких дополнительного selector fit, full-pool materialization, postscore pruning или новых seeds. PRNG seed выбирается один раз без seed shopping; saved actual draw важнее заявления об ожидаемом coverage.

Для final review предлагается явный selector: eligible complete arms проходят source/resource и уже объявленный Recall guard `ΔRecall≥−.002` относительноB; основной score — conditional macro-query full-Y NDCG20. ВключитьB как no-change candidate; выбрать global maximum, tolerance set `score≥max−1e−12`, ties предпочитаютB, затем меньший bundle ID. Это prospective tie proposal016, не подмена canonical019 fewer-trees→depth→incumbent→configID. Неполные/failed arms не получают fictional zero; integrity fault означаетSTOP.

Контргипотеза «это recent-repeat/popularity, а не добавочная информация» остаётся содержательной. Практический gate уже зафиксирован как pointΔNDCG≥.002, lower95%>0 и Recall/cost/coverage guards; он **не** доказывает trueΔ≥.002. На reused selection это screening, не confirmatory refutation. CI пересекает0 — sign-inconclusive; point ниже.002 не проходит practical gate; cost exhaustion — budget-limited, semantic failure — invalid. Не добавлять отдельный I−R bootstrap look или новые attempts ради опровержения.

Допустимый итог: «Из восьми заранее зафиксированных bundles два static semantic choices и два seeded random slots далиU уникальных допустимых pipelines; winner выбран по указанному development rule. Его contrast с frozen B описывает этот pipeline и cohort. Best-I против best-R — descriptive; превосходство learned intelligence, универсального search или стратегии по двум draws не установлено». R winner и отсутствие gain equally valid; неудача двухR не доказывает бесполезность random search. Ни новые fits, looks, бюджеты, обязательные evaluations или research quota не выданы.
