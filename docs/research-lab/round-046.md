# Round046 — LLM proposer: реальные loops и будущая typed граница

**Primary-literature research, без LLM calls, реализации, dependencies, данных или execution.** Три реальные работы проверены по полным первичным текстам; текущий frozen016/019WIP не читался. Нынешние12columns/4fits не расширяются. Это future branch после bounded016, не переименование staticI в learned intelligence и не новая обязательная HYPquota.

## Три разных метода, а не общий ярлыкLLM

**CAAFE, Hollmann–Müller–Hutter, NeurIPS2023.** Context/task description, feature names/types, train-only missing statistics и10random rows формируют prompt. LLM выдаёт Python feature alterations и пояснения. Downstream classifier обучается, изменения оцениваются на validation и сохраняются при улучшении; errors возвращаются в следующую итерацию. В описанной настройке10feature iterations и10random validation splits, mean accuracy/AUC feedback. Это supervised search с оценками и repair, не бесплатный semantic brainstorm. Paper содержит whitelist для generated code; это не наш typed relational AST validator. [Полный paper](https://papers.neurips.cc/paper_files/paper/2023/file/8c2df4c35cdbee764ebb9e9d0acd5197-Paper-Conference.pdf).

**FeatLLM, Han–Yoon–Arik–Pfister,2024.** Prompt содержит task/classes, descriptions/types и few training examples с ground-truth labels. LLM формирует class-specific rules; они становятся binary features, затем обучается простой linear predictor. Bagging и повторное извлечение rules дают ensemble; inference после этого не требует per-sample LLM call. В appendix diversity связана с temperature0.5, bagging и shuffle примеров. Отсутствие fine-tuning LLM не означает0fits всей системы или label-blind proposer. Threshold/membership rules не являются существующими005operators. [Авторский текстv2](https://arxiv.org/html/2404.09491v2).

**LLM-FE, Abhyankar–Shojaee–Reddy, arXivv2.** Task/feature descriptions, sample instances и evaluation function задают program search. Validation score обученного predictor и high-scoring Python programs возвращаются в memory/islands и следующие prompts; выбирается итоговый ensemble. В настройке указаны20LLM samples,3islands и3programs на prompt; local time/memory rejection не заменяет общий ledger. Формулировки algorithm/experiment нельзя автоматически свести к20native fits. OpenReview current publication PDF вернул browser challenge; здесь проверен именно доступный author arXivv2, а не приписан полный audit другой версии. [Полныйv2](https://arxiv.org/html/2503.14434v2).

Материальный нюанс: LLM-FE группирует programs по одинаковым validation scores как memory signature. Это heuristic diversity management. Одинаковый score не доказывает равенство feature values/AST и не является допустимым semantic dedup полного B/retrieval. Обратное также верно: разные textual programs могут быть exact aliases.

## Сопоставление с текущим typed016

| Граница | Текущий deterministic016 | Возможный LLM proposer, только proposal |
|---|---|---|
| Inputs | Вручную объявленные schema/context/templates/windows и frozenB | Тот же approved descriptor; any examples/Y/history отдельно перечисляются |
| Output | Existing005 definitions, eight legal bundles | Только существующий legal AST/bundle ID, не исполняемый Python/SQL |
| Feedback | Static I и seededR фиксируются до новых016scores | Outcome feedback означает отдельный adaptive search protocol |
| Legality | Types/grains/actions/windows, full physical closure3, B/retrieval aliases | Тот же validator; prose justification не заменяет proof |
| Cost | Calculation/oracle/fits/failures входят в bounded ledger | Дополнительно calls/tokens/latency/repair/screening и память feedback |
| Reproducibility | Contract/pool/allocation hashes и PRNG state | Сохранять raw responses и точные accepted programs; seed недостаточен |

Работы подтверждают осуществимость LLM feature engineering в своих tabular classification/regression setups. Они не устанавливают temporal correctness для raw recommendation events, fullY-outsideC или перенос benchmark gain на наши73positive selection queries. Наш вывод: natural-language domain prior может изменить распределение предложений; его полезность и стоимость требуют отдельной проверки.

## Information и feedback budget

Schema/action/unit descriptions без outcomes — target-free input. Task description «предсказывать purchase» сообщает смысл labels, но не observed queryY. Train examples сY делают proposer target-aware; train-only screening/learned critic требует объявленных fits/cost и availability, но не автоматически нового selection-date look. Validation metrics в prompt, ranking или memory добавляют development feedback. Известная автору008/009history остаётся disclosure, даже если numeric scores удалены из prompt.

Исторические feature values обязаны использовать strict past каждого anchor. Поздно выбранный AST остаётся retrospective development program, не притворяется существовавшим в старом anchor. Program/decision availability, dependencies и consumed looks фиксируются до reserved-target opening. LLM не выбирает label-conditioned Q/C или другой denominator.

Invalid response, duplicate или unsupported operator расходует заранее выделенную proposal opportunity; бесконечные repair/rephrase/reroll запрещены. Порча уже принятого source/output — integritySTOP, а не предложение, которое можно бесплатно заменить. FullB/retrieval/core/mask/support/coverage closure проверяется до materialization. Equal scores, correlation или persuasive explanation не заменяют canonical signatures.

## Одна capped future гипотеза

После завершения нынешнего016 предложить **feasibility hypothesis**: при одном fixed prompt из approved schema/operator/temporal descriptors LLM выдаст два разных законных3-column bundles из общей заранее закрытой eight-pool без observedY/quality feedback. Counter: semantic prior повторяет наиболее очевидные B/первыйbundle либо придумывает unsupported transformations, поэтому две opportunities не дают двух пригодных programs.

Предлагаемый cap отдельного будущего preflight:≤2single-response LLM calls, без repair/resampling,≤32literal synthetic rows для independent closure/formula checks,0native fits. Никаких raw пользовательских rows в prompt. Accept только если обе opportunities дают different legal nonalias bundles, exact3physical columns и independent literal/source-formula witnesses PASS; duplicate/invalid/missing response — consumed failure. Это проверяет producibility законных proposals, не quality superiority. Calls/service/money/CPU cap требуют отдельного разрешения; сегодня никакого не выдано.

Для comparator заранее сохранить два uniform seeded draws с возвращением из того же pool, теми же collision rules; он проверяет одинаковый opportunity accounting, но не равную стоимость LLM/random. Quality comparison остаётся отдельно deferred: до обучения понадобились бы exact matchedB/population/settings, equal fit opportunities, primary contrast и prospective calendar. Дополнительные4fits здесь не предлагаются как allowance.

Artifact должен сохранить model/provider/version, prompt bytes/history/order, sampling settings, returned bytes/errors, validator verdicts, AST/closure/pool hashes и actual cost. Это позволяет replay выбранных programs; новый stochastic вызов не обязан вернуть те же bytes даже при temperature0. Два proposals/draws не доказывают learned strategy, cross-dataset meta-knowledge, экономию human-hours или speedup относительно уже batched005.


## Source-audit appendix —15Oct2026, proposer inputs и скрытые calls

Исходный текст сохранён. [CAAFE paper, appendixD](https://papers.neurips.cc/paper_files/paper/2023/file/8c2df4c35cdbee764ebb9e9d0acd5197-Paper-Conference.pdf) явно показывает Class samples вместе с training feature samples. Поэтому10rows нельзя трактовать как гарантированно label-free descriptor; training labels могут быть непосредственно видны proposer, отдельно от validation-score feedback.

[FeatLLM§3.2](https://arxiv.org/html/2404.09491v2) использует LLM также для parsing natural-language rules в Python code, затем exec для преобразования данных. Это дополнительная call stage, которую краткое описание046 не выделяло; rule-generation calls нельзя считать полным API ledger метода. Downstream predictor точнее описан как nonnegative linear class logits с softmax, обученные cross-entropy, не обычная linear regression. Предложенный typedAST preflight046 не воспроизводит эти stages и не заимствует их budgets.

LLM-FE v2 сообщает20LLM samples и3programs per prompt; это не достаточное основание утверждать точное число запросов/native fits или полный observed CPU.30s/2GB в appendix — авторские local evaluation limits, не независимо измеренный whole-search bound. Эти уточнения не меняют нынешний016 и не выдают новых calls/fits.
