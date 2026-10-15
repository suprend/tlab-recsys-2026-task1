# Round047 — переносимость empirical evidence в temporal purchase ranking

**Source-only audit, без WIP/data/MLexecution/LLM calls или новых budgets.** Цель — отделить проверенные результаты пяти работ от вдохновения для bounded016. Loops разобраны в046 и не пересказываются. Source-fact audit043–046 остаётся в силе. Ни один рассмотренный benchmark не воспроизводит одновременно наш strict-asof raw event bag, repeated daily Q, fixed retrievedC и полный purchaseY, включая товары внеC.

## Primary evidence-transfer matrix

| Работа и проверенный primary scope | Что измерено/с чем сравнивается | Что допустимо перенести |
|---|---|---|
| [CAAFE, NeurIPS2023](https://papers.neurips.cc/paper_files/paper/2023/file/8c2df4c35cdbee764ebb9e9d0acd5197-Paper-Conference.pdf):14tabular datasets;5random50/50train/test repetitions | Abstract сообщает улучшение11/14 и mean ROC AUC.798→.822. Downstream LR/RF/TabPFN, features выбраны сTabPFN | Evidence полезности contextual proposals в этих classification setups; не prediction покупки и не NDCGgain |
| [FeatLLMv2](https://arxiv.org/html/2404.09491v2):13binary/multiclass datasets, few-shot random labeled training samples | AUC tables для4/8/16shots и дополнительных32/64; среди baselines LogReg/XGBoost/RF/TabPFN/STUNT/TabLLM. Дваhigh-dimensional datasets имеют exclusions | Feasibility rule-based representation при малом labelled sample; не эквивалент73positive queries среди4000Q |
| [LLM-FEv2](https://arxiv.org/html/2503.14434v2):19classification/10regression datasets;80/20train/test;5splits, inner validation изtrain | Accuracy/N-RMSE; XGBoost main baseline, сравнения сAutoFeat/OpenFE/LLM methods. Regression table не сравнивает со всемиLLM baselines из-за отсутствия implementations | Evidence внутри этих tabular splits/model choices; нельзя перенести mean rank или «outperforms» на полный recommendation protocol |
| [ExploreKit2016](https://people.eecs.berkeley.edu/~dawnsong/papers/icdm-2016.pdf):25OpenML classification datasets;stratified random66%train, inner3folds | C4.5/SVM/RF сWeka defaults; MLFull/MLFast противIG variants. Abstract «20%error reduction» имеет специальную AUC-based formula | Learned feature-ranking mechanism inspiration; не20percentage points accuracy и не сравнение сwell-tunedCPUCatBoost |
| [OpenFE2023](https://proceedings.mlr.press/v202/zhang23ay/zhang23ay.pdf):10benchmarks собщимsingletrain/val/testsplit,10experiment repetitions;classification/regression | AUC/accuracy/RMSE, Base/FCTree/SAFE/AutoFeat/AutoCross/FETCH/NN. KaggleIEEE/BNP private leaderboard comparisons отдельно | Incremental usefulness/pruning evidence; ни temporal constraint, ни наша opportunity/cost fairness не доказаны |

FeatLLM «10% on average» из abstract не следует использовать как ожидаемый relative gain016: нужно указывать конкретный dataset/shot/baseline/metric. Число ансамблей, labeled examples и validation folds не равно числу positive purchase queries. Exact universal train/test fraction FeatLLM этим чтением не установлена;50/50или80/20 из других papers ему не приписывается.

ExploreKit§V определяет reduction как `(AUC_final−AUC_initial)/(1−AUC_initial)`. Поэтому небольшой absolute AUC change при высокомinitialAUC даёт большой relative reduction; это не уменьшение числа ошибочных классификаций по фиксированному threshold. Default classifiers также не устанавливают, что они сильнее нашего frozen tunedB.

В OpenFE Microsoft явно указан как **Regression**, primary metricRMSE; происхождение из ranking dataset само не делает этот benchmark query-macro NDCG. Kaggle headline99.3%/99.6% означает долю teams, обойдённых конкретной pipeline на leaderboard, а не относительное улучшение prediction quality или победу над всеми компонентами winning ensemble. В IEEE сравнение shared expert features использует один baselineXGBoost; авторы отдельно отмечают, что полный winner ensemble не раскрыт.

## Почему snapshot evidence не даёт temporal/source proof

Табличная строка сготовыми columns скрывает способ их получения. Random row split не удостоверяет availability каждого event/metadata aggregate. Если dailyqueries одного пользователя распределить случайно, train может содержать более поздние labels/context, чем testquery; «train-only fit» ещё не доказывает past-only каждого featurevalue. Это наш protocol inference, не обвинение papers в нарушении их собственных задач.

OpenFE§6 прямо признаёт, что метод не умеет обеспечивать time-series constraint вычисления новых features изpast. Следовательно, поддержка GroupBy/types и even fraud benchmark не являются готовой заменой005temporal compiler/source oracle. Правильный layer transfer — proposer может предложить программу; наши typed/grain/window/availability validators всё равно определяют допустимость.

FullY denominator/IDCG зависит от всех target purchases, включая out-ofC. AUC на rows выбранного tabular sample не штрафует отсутствующий retrieved item таким же способом. Repeated-query dependence требует общего user cluster при парном resampling; published split standard deviations илиWelch tests оценивают другой объект. Exposure/stock/propensities отсутствуют унас: zeroY labels не являются известными отрицательными показами, accuracy/AUC gains не становятся causal recommendation lift.

Простой conceptual counterexample: в100binaryrows сдвумяpositives constant-negative classifier имеет98%accuracy. Constant ranking scores внутриC лишь включаютIDtiepolicy; качество top20 определяется местомpositives иretrieval misses. Между98%accuracy иconditionalfullY NDCG нет однозначного преобразования. Это аналитический пример, не выполненный benchmark.

## Cost evidence нельзя переносить вместе сheadline

CAAFE appendixF сообщает среднее4:43min/dataset, dominated code generation, сtoken-cost figure; это исторический experiment time, неactualCPU нашего job. FeatLLM Table5: Adult16shots, oneA100 default, API-dependent runtime;860.094s training/0.006ms per-sample inference и30APIqueries относятся кэтомуreportedcomparison. Per-sample inference не включает feature-discovery history или наш collection/source proof.

ExploreKit использует20cores/64GB,15iterations идо3days/dataset. OpenFE appendixD: featuregeneration40coreXeon/512GB, tuning/training наV100; reported runtime tables не являются двухпоточным Mac CPU ledger. LLM-FE local30s/2GB rejection иreported Pareto analysis не доказывают total bound сcalls/failedattempts/oracles. Неизмеренные totals остаютсяunknown, а не0; сегодняшние цены/APIlatency не выводятся изстарыхpapers.

## Минимальный следующий эксперимент

Новый quality experiment пока не обоснован одним переносом headline: current016 сначала должен завершить своёmatchedB сравнение. Для будущего LLM branch достаточно уже предложенного0460-fit typed-feasibility preflight; второго pilot или дополнительных calls здесь не добавляется. Только если такой отдельный reviewed stage подтвердит legalclosure/source semantics иполныйcost accounting, можно отдельно обсуждать matched temporal quality trial сfixedQ/C/fullY инеиспользованной evaluation boundary.

Честная финальная формулировка: «Работы подтверждают механизмы иtabular empirical feasibility. Мы проверяем ограниченную temporal relational adaptation отдельно; ихaccuracy/AUC/RMSE, leaderboard ranks иhardware timings не предсказывают величину либо знак нашегоNDCGcontrast». Negative016 не опровергает всеAutoFE/LLM методы; positive016 не воспроизводит целые published algorithms ине доказывает универсальный transfer.
