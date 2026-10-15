# Metadata/price ablation: независимая приёмка и отказ от блока

15 октября 2026. **ACCEPT исполнения/результатов; REJECT всего metadata/price блока для дальнейшего контроля.** Ровно одно разрешённое обучение Logloss50 на тех же6000train/4000selection запросах завершилось; project-wide claim потрачен, замен/refits нет. Новый блок имел56numeric+3nominal входа, исходный контроль —41numeric.

| Fixed development comparison | Conditional full-Y NDCG@20 | Recall@20 |
|---|---:|---:|
| Existing008 Logloss50/base41 |.41444755081727774|.5812133072407045|
| ONE009 Logloss50/base41+metadata18 |.40041404048762785|.5450097847358121|

Заранее закреплённое правило требовало NDCG>base+1e−12 и Recall≥.5792133072407045 после всех source/resource/model gates. Оба quality условия не выполнены; **дальше фиксируется base41**, eligible incumbent — existing008 Logloss50/6000. Данные metadata, source proofs и неудачная гипотеза сохраняются. Это не доказательство бесполезности price/brand в целом и не разрешение подбирать этот блок дальше.

Независимый [oracle source](tlab009-model-oracle-accepted-source.md) не вызывает production loaders/metric functions. ПрямойSQL из уже принятых Parquet собирает собственные56float32+3UTF8bytes массива для всех817149selection пар; savedCBM воспроизводит каждый raw score с absolute1e−12 и точными keys/order. Старый008CBM отдельно воспроизводит свои scores из независимо собранных41колонок. Числа из report не задают expected feature values. Metadata source176pin acceptance уже проверила все110mдобавочных значений; здесь не заявляется повтор source formula verification.

Свои fullY96targets/73positiveQ, четыре estimands, все200paireduser-bootstrap samples/interval и policy decision совпали (для scalar metrics/samples math.isclose absolute1e−12/relative1e−9; raw scores строго rtol0/atol1e−12). ΔNDCG=−.01403351032964989; percentile interval [−.06338086509402815,.04292473944032154] — development screening conditional on observed dates/fittedmodels, без confirmatory/causal/generalisation claim. Bootstrap3995mature users/seed2026/undefineddraws0 проверен.

Training population independently counted:6000Q/1227213rows/114fullYpositiveQ/92informative/101retrievedpositive, expected query-normalised rowmass6000. ActualTRAINencoded cardinalities ID501/code120/brand1265≤4096. Saved50trees/feature order/effectiveparameters подтвердились; JSON255FloatFeature+45OneHotFeature splits,0CTR. Веса доказываются acceptedfitcode/report плюс independently computed expected population/mass; изCBM сами фактически переданные trainingweights не восстанавливаются. Producer exact BASEONLY/mixed-prefix equivalence assertions прошли, а independentold008selection replay дополнительно проверяет model-boundary assembly.

| Resource receipt | Wall,s | Actual CPU,s | PeakRSS,bytes | Native fits |
|---|---:|---:|---:|---:|
| ONE009 fresh producer parent |87.824675|101.181955|2984067072|1|
| Initial failed independent observer |2.622693|3.335586|1443610624|0|
| Corrected independent replay parent |3.574777|4.585806|1750974464|0|

Combinedindependent7.921392CPU seconds входят в900cap; production+bothobservations109.103347CPU seconds, без выдуманного остатка общей квоты. [Aggregate evidence](tlab009-model-output-aggregate.json) сохраняет receipts/metrics/samples/pureparameterchecks. [Initial observer failure](tlab009-model-oracle-initial-failure.md) и [independent static critic](tlab009-model-oracle-review.md) сохранены. Final process exit0 после close, parent terminal ledger, exact3outputpaths/hashes, nofailedmarker и comparison metadata отдельно проверены; statusfilealone не принят.

Машинная external acceptance scope reviewed_metadata_price_single_ablation выводится из192inputs+executionapproval+run/report+consumedclaim+3outputs и опубликованных независимыхproofs; ignoredrecord не меняет immutableproducerreport. Source/memory correctness не гарантирует ranking gain. Следующие019/016 наследуютbase41; их tuning/automation/holdout gates пока не завершены.
