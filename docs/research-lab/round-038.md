# Research lab, round038: adaptive search как будущая альтернатива frozen016

15 октября2026. **Literature/design-only**, без implementation/dependencies/cloud/data/SQL/tests/Pool/fits/новыхlooks. Current019/016не заменяются; их budgets, selected bundles и no-refill сохраняются. Прочитаны [019freeze](../backlog-reviews/strong-worker-design-freeze.md), [016pool026](round-026.md), [claims034](round-034.md), [chronology014](round-014.md), current backlog/confirmation config. Ниже три первичных алгоритма и focused final-calendar audit, без novelty quota/разрешения исполнения.

## Что именно сравнивается

Current016 — две human/staticI bundles и две seeded uniform R draws из общего typed legal pool с replacement; collision consumed/no redraw,≤12physical new columns/≤4nativefits/≤2CPUh совместно. Все arms наследуют один019winning B, train population, weights, trainediterations и scoringprefix. Это bounded comparison выбранных pipelines, не trained proposer и не доказательство strategy superiority по двум random draws.

BO/SMAC/Hyperband/BOHB решают иной вопрос: **какую следующую configuration и с каким ресурсом испытать после наблюдения прошлых outcomes**. Они не генерируют legal relational AST автоматически, не доказывают feature formulas и не предоставляют бесплатные labels. Их published improvements на других задачах не являются прогнозом выигрыша в нашем8bundle/4fit experiment.

## Три source-faithful механизма и конфликты

| Первичный алгоритм | Механизм и потенциальная польза | Counterhypothesis / почему deferred сейчас |
|---|---|---|
| [SMAC, Hutter–Hoos–Leyton-Brown, авторский extended paper](https://www.cs.ubc.ca/~hutter/papers/10-TR-SMAC.pdf) | Fit performance-response model; default random forest поддерживает categorical configuration dimensions. Acquisition предлагает promising settings; intensification сравнивает configurations на instances/seeds | Surrogate может направлять scarce trials, но несколько noisy points не дают надёжного landscape. Sequential outcomes меняют последующие choices, что нарушает frozen2I2R; racing/incumbent repetitions не разрешены4nonrefillable slots |
| [Hyperband, Li et al.](https://arxiv.org/pdf/1603.06560) | Random configurations, brackets разных initial resource allocations, successive halving с остановкой худших и увеличением ресурса survivors | Economize может лишь при информативной low fidelity. Поздно раскрывающийся лучший arm может быть отсечён; fixed preparation/source-verification overhead может доминировать. Current016не разрешает менять trainediterations/population по промежуточным scores |
| [BOHB, Falkner–Klein–Hutter](https://proceedings.mlr.press/v80/falkner18a/falkner18a.pdf) | Hyperband scheduling плюс TPE-like density estimation; модель берётся на максимальном budget с достаточными observations, часть configurations random | Learned guidance и fidelity allocation требуют observations/model fitting; не GP по умолчанию и не безусловная meta-knowledge. На tiny history overhead/ошибочная low-budget ordering могут перевесить пользу; conflicts обоих предыдущих методов остаются |

SMAC paper явно считает время FitModel/SelectConfigurations частью optimization overhead. Hyperband обсуждает iterations/time/data subsampling как разные ресурсы и initialization/loading/validation overhead; число nominal training units не равно actualCPUseconds. BOHB допускает, что low budgets вводят в заблуждение, и опирается позже на более высокую fidelity при достаточном evidence. Поэтому «sample efficient» означает hypothesis об allocation policy при заданных предпосылках, не гарантию fewer paid fits или меньшего общего бюджета здесь.

## Почему existing checkpoints не скрытый Hyperband

019полностью train300 до любого50/150/300 checkpoint score; late failure делает wholearm ineligible. Это fixed checkpoint selection, не successive halving с ранним прекращением неудачных fits.016inherits trained300/scoring50 либо150, если такой019winner; cheap50tree proxy вместо300tree procedure меняет вмешательство. Если incumbenttrained50wins, его fixed50 также не новая fidelity ladder. Prefix copy zero-refit, но compute/scoring/validation и consumed looks не бесплатны.

Low training population6000 вместо26000 меняет обучаемый pipeline и support, даже если fullY evaluation estimand/formula остаются теми же. Если subsample ещё и evaluationQ/labels, меняются finite-cohort target/uncertainty; нельзя смешатьproxy иfinal scores как одну observation без fidelity/context field. Source features всё равно historical strict-past, Q/Cpopulation не фильтруется по будущимpositives. Metadata/encoder/AST knowledge availability и search history остаются явными.

Каждый surrogate/proxy training, feature materialization, acquisition search, failed/censored trial, cache validation, retry/resume и outcome opening должен попасть в ledger. Surrogate fit не обязательно nativeCatBoost fit, но это **дополнительное learned computation**, требующее собственного заранее разрешённогоscope и учета; label «optimizer overhead» не легализует hidden fits. Нельзя превратить сэкономленное ранним stopping время в пятый configuration/newseed/refill без иной заранее утверждённойpolicy. Сейчас такойpolicyнет.

## Когда learned proposer мог бы утверждать transfer

Нужны frozen descriptor/AST encoding, target/metric/fidelity definitions, complete provenance предыдущих tasks/configurations/outcomes и стоимость получения priors. Обучениеproposer заканчивается до его использования; использованныеlabels зрелы, feature state не backdated. Независимые future tasks/time contexts должны оставаться вне meta-training/selector tuning. 008/009на одной selection — prior-known development history, не independent multi-task transfer benchmark. Хорошее предсказание уже посмотренных outcomes не подтверждает generalization.

Будущий эксперимент возможен только как **новая predeclared замена allocation**, а не добавка к нынешним4fits: часть ограниченного бюджета уходит на initial observations/surrogate, остаётся меньше full-fidelity candidates; одинаковые legalpool/B/fullY/cost accounting нужны обеим стратегиям. Alternative fidelity study заранее тратит slots на proxy и проверку его отношения к final procedure, оставляя меньше candidates; если такого evidence не помещается, defer. Ни число новыхfits/looks, ни fresh holdout этим описанием не запрашиваются. Для проверки controller можно предложить0fit literal outcome table с crossing learning curves и failed receipt: она проверяет scheduling/consumption, не качествоoptimizer.

[Cawley–Talbot](https://jmlr.org/papers/v11/cawley10a.html) предупреждают об overfitting selection criterion; [Dwork et al.](https://arxiv.org/pdf/1506.02629) дают специальный controlled-feedback reusable-holdout механизм. Здесь он не реализован. Нельзя повторно использовать уже looked selection и назвать adaptive trial подтверждением стратегии; predeclaredfuturepolicy нужна до новых outcomes.

## Focused audit: confirmation25→final26 оставляет второй zero gap

Finding **уже есть** в published014, counterexample «Confirmation→final», но решение не найдено: actual [confirmation config](../../configs/development/confirmation.json) по-прежнему24–25 и `final_holdout_start=26Oct00`; [backlog](../backlog.md)215–217/019freeze оставляют calendar отдельнымopen gate.25-only пока prospective, не утверждённый schedule.

Если одинconfirmation anchor25Oct00/H24/δ0, maturity=`Mconf=26Oct00`. Adaptive promotion/refit требует `Afinal≥Mconf+positive_compute_allowance>26Oct00` и `Afinal<first_final_query`; final26Oct00 не удовлетворяет обоим. Physical2026sealing доtarget opening обязательно, но не устраняет simulated dataset-clock contradiction.

**Decision gate до любого opening:** либо confirmation только reporting, models/features/control/finalpolicy frozen после24+compute, до25 и final26неизменен независимо отconfirmationmetrics; либо adaptive finaldecision требует отдельно reviewed более позднегоfirstfinalanchor с положительнымgap (27Oct+ — пример, не разрешение). При refit добавляются его matureinputs/fitend/available_at. Нельзя послеconfirmation выбрать удобный вариант, изменитьthreshold/ветвь или скрыть finalevaluation из-занеудачи. Calendar и рольconfirmation нужно фиксировать **до открытия targets**; budget/schedule/config mutations здесь отсутствуют.

### Independent critic новой Root policy: design acceptable с обязательными gates

Root предлагает confirmation25 reporting-only, final26+ неизменными frozen B/016winner: programs/params/population/trainediterations/scoringprefix. Это закрывает adaptive gap **условно**, не утверждает calendar/config/execution. Decision lock после maturity24+positive compute, до25; все held-out predictions sealed **до открытия query-level Y25/evaluation**. Confirmation quality failure отражается честно, без смены модели/refit/promotion; integrity failure — STOP, не rescue.

Статически [prepare_model_data](../../scripts/model_data.py) всегда читает `refs['labels']`, строитchosenY и joinlabels. Поэтому нужен отдельно reviewed label-blind inference path; существующий training loader не доказывает такое sealing.26+features законно читают25purchase events как strictpast, но запрещено использовать их для выбора. Whole-month EDA/source access уже известны: абсолютная raw-byte blindness не заявляется.

[Source end](../../configs/protocols/clock-48h.json)=Nov1; final31/H24 зрел толькоNov1 приδ0/fullcoverage. Поздние/incomplete horizons censored, неzeroY. Любое postconfirmation изменение→STOP prospectiveclaim, без бесплатного сдвига schedule. Политику фиксировать доopening; исходный finding выше сохранён.
