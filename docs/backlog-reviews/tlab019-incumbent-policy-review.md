# TLAB019: independent incumbent/pipeline policy amendment

Вердикт: **ACCEPT направление amendment как prospective pipeline selection; до009metrics зафиксировать retention predicate и точные manifest bindings.** Это review правила, не execution/code/fit approval. Fits/scans/production edits отсутствуют. [Исходный019critic](tlab019-prospective-plan-review.md) сохранён неизменным: SHA256 `7dca2d10e1bf6a961921a9a6834b06ead2bc92014fac8f33b61c1cff2ca8c754`. Его blanket population interpretation здесь уточняется открыто; HYP105/106reserved.

## Что меняет incumbent

Корректный eligible incumbent зависит от финально принятого feature schema: unchanged008Logloss50/6000 при rejected009block либо уже существующий accepted009Logloss50/6000 при retainedblock. Новый fit incumbent не нужен и не разрешён. К нему добавляются максимум12checkpoint choices из четырёх новых GridCfits: depth4/6×L2 3/30, LR.05, max300trees,50/150/300, fixedactualNewton10/AnyImprovement/random_strength1/boost_from_averageFalse/Plain/bootstrapNo и остальные pinned effective parameters008.

Поэтому полный выбор включает **feature decision, training population, hyperparameters и checkpoint**. Если incumbent выигрывает, выбранный pipeline6000; если новый winner обучен26000, pipeline26000; при declaredgatefallback новый winner тоже6000. Это допустимая заранее объявленная conditional policy, а не скрытый post-score population rescue. Она не доказывает отдельный эффект количества trainqueries или superiority objective.

Один resource/cardinalitygate выбирает population **всех четырёх новых fits**, а не последующего winner/016безусловно. После PASS нельзя переключать часть новых arms на6000 при неудаче fit. Semantic/lineage/API failures останавливают работу; resource/cardinality failure разрешает только объявленный6000fallback с собственным validation и без повтора26000gate. Incumbent остаётся ранее существующим6000pipeline при любом исходе gate.

## Retention009 нельзя оставить подразумеваемым

«Accepted009model» означает проверенный artifact/исполнение, а не автоматически полезный block. До009metrics нужен единый retention predicate относительно unchanged008 на тех жеselectionQ/C/fullY. Консервативное предложение: retain только при прошедших source/cost/model gates, Recall≥0.5792133072407045 и NDCG≥008NDCG−1e−12; иначе finalschema остаётсяbase. Это point-estimate screening rule, не statistical noninferiority/promotion и не дополнительный fit.

Если coordinator выбирает другую retention policy, её следует записать до результатов с явным объяснением. Нельзя сохранить слабый metadata block, исключить более сильный008из допустимого final-schema control и затем объявить преимущество automation над «хорошо настроенным manual» без раскрытия этого ограничения. Retained model должен иметь accepted immutable score/model/input pins; пересобрать его после019results не разрешается.

## Winner и matched016

Среди **feasible incumbent и новых completed-fit checkpoints** выбирается максимум external conditional macro-query full-Y NDCG20. Recallguard общий, от pinnedold008: `.5812133072407045−.002=.5792133072407045`. Его artifact/evaluator/Q/C/fullY identity связывается, не только copied number. Nonefeasible включаяincumbent→STOP, без refill/ослабленияguard. При rejectedblock и корректном008incumbent Recallguard обязан проходить; обратное требует lineage/estimand расследования, не нового threshold.

Для tolerance tie использовать стабильное правило: сначала M=maxNDCG, затем один tie-set `score≥M−1e−12`, внутри меньшеtrees, меньшедepth, incumbent preference толькоесли предыдущиеcriteriaравны, configID. Попарный approximate comparator может дать зависимость от порядка; единый tie-set устраняет эту неоднозначность. Нельзя предпочесть population по цене, если это не входит в опубликованный tie rule.

После winnerfreeze **все I/R arms016** получают один exacttrainQ/C/Y/hash, rowweights, chosenfeatures/encoder/input order, objective/effectiveparams/trees/seed. Incumbentwinner означает точные прежние6000Q, не произвольную новую6000sample. Newwinner26000 означает те же26000дляобеихstrategies. Candidate bundles остаются ровно3новыеphysicalcolumns с supports/flags/coverage closure;2I+2R/onebundleattempt/no replacements сохраняются. Базовый B не получает дополнительный refit для016. Так проверяется incremental feature generation/calculation на выбранном pipeline; population selection нельзя приписывать intelligence strategy.

## Cost и survivorship

12новыхlooks — не вся история: отдельно уже просмотренный008incumbent/screening,009singleablation/retention decision и прежние007looks. Уже сохранённый score можно переиспользовать после exactmetriclineagecheck; replay/scoring/audit всёравно оплачиваются. Incumbent reuse не создаёт новый fit budget.

Gate/prep/Pool/cardinality/oracles/всеfailedfits/checkpoint scoring/serialization входят в proposed019≤60actualCPUminutes;016сохраняет отдельный existing≤2CPUh ledger без автопринятия нового общего бюджета. CPU — measureduser+system всех процессов без doublecount, неwall×threads. Уже потраченные008/009costs остаются видимыми в общей истории, но не «переобучаются» внутри019.

Если cap/ошибка оставили меньше четырёх завершённых fits, выбирать допустимо только по заранее разрешённому available-candidates rule, сохранив ledger failed/unattempted configs. Это boundedattempted search, не completegrid и не evidence, что incumbent объективно лучше всех отсутствующих models. Failed partial checkpoints не eligible без прежнего отдельного правила. Incumbentwinner честно называется reusedcontrol послеboundedsearch, а не зановоtrainedstrongmodel.

Selection73positivequeries ограничивает precision; bootstrap после selection не устраняет adaptivity. Confirmation/final закрыты; actualwinner/decision availability и positivecompute gap остаются самостоятельными gates. Amendment фиксируется до009metrics; executioncode, exactapproval и новые четыре fits ещё не приняты этим review.


## Canonical decision after review — before009ablation metrics

Выбранstrictpredicate: всеsource/cost/encodedselected6000cardinality/noCTR/effectiveparam/keygatesPASS, Recall≥.5792133072407045 иNDCG>.41444755081727774+1e−12→retain009wholeblock. Tolerance tie→base41. RawпредложениеNDCG≥base−epsвыше неявляетсядействующимправилом. Этоscreeningcontrolselection,неCI/practicaltrueeffectproof. [Critic012/019](../research-lab/round-012-review.md) и [canonicalbacklog](../backlog.md) сохраняютmatchedwinnerpopulation/eligibleincumbent,4newfits/12looks/no refit/failurecosts.
