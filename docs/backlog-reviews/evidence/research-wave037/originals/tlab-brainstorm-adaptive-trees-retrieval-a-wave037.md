# Wave037 B FIRST — adaptive prefixes are selection, not an optimum guarantee

**Disposition:** zero new IDs; refine TLAB019 and own wave013 and prior checkpoint/selection-bias work. Incorporates Root's updated adaptive requirement; the three-checkpoint proposal is superseded/unrun. No current018/015 change or grant.

**Mechanism/benefit.** Historical300 was a frozen finite grid/resource boundary, not evidence of convergence. The proposed independent exploratory branch trains B/W fully to1200 with fixed depth6/L2=30/lr=.05/CPU2/seed2026, then separately selects each arm's prefix from1…1200 by full-Y conditional NDCG20 on22–23; train8–20, no25–31.1200 is the new resource ceiling. Staged prediction supports growing prefixes, with explicit RawFormulaVal scores, not default class labels.[1] Shrinking afterward can reduce saved-model/inference work; full1200 training is still paid.

**Prediction/limits.** With ε=1e−12 and k*=min{k:S(k)≥max_j S(j)−ε}, selected validation score must be≥S(300)−ε. This is an internal selector invariant, not predicted future improvement. Use that run’s300 prefix; equality to an old300 fit is unverified. Both B and W may improve, or B may improve more. Falling train Logloss can accompany falling ranking NDCG. Report all2400 dependent prefix metrics and selected tree counts;73 positive queries are not2400 independent observations. Optimizing a noisy reused validation criterion creates selection optimism; an ordinary CI computed after selection does not restore independence.[2]

All73 full-Y-positive queries remain in the metric, including off-C-only and empty-C cases. Native shortlist-only NDCG cannot supply their full-Y IDCG. Preserve Q/C, product-ID tie order and exact denominator; no positive insertion or outcome-based source-cohort changes.

**Nearest minimal UNRUN falsifier.** Three score values s,s+.75ε,s+1.5ε must select checkpoint2 under the global tolerance band. Incremental “replace only when improvement>ε” can choose3 and is not equivalent. Check this selector identity without native execution; no fixture ran.

**Rolling temporal CV.** A future forward-fold study could expose unstable peak locations/contrast signs across time. It must refit each arm, keep train-label maturity plus fit availability before validation, and freeze calendar/support/selection rules before feedback. Shared users, overlapping training windows and changing train size limit independence/comparability; CV reused for tuning remains development. It is optional, not a gate for this branch/report. No new source/fold authorization is implied.

**Full cost/negative outcome.** Charge source authentication/preparation, two complete1200-tree fits, all staged predictions/ranking/2400 looks, scalar curves/saved prefixes, streaming/copy memory, hashes, shrink/reload verification and failures. Each additional fold adds two fits and up to2400 looks plus preparation; no free reused feedback. No later-prefix gain, unstable peaks or uncertainty means inconclusive/limited selection benefit, not automatic ceiling expansion. Opened final is never new validation.

[1] [CatBoost staged_predict](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_staged_predict).
[2] [Cawley–Talbot2010](https://jmlr.org/papers/v11/cawley10a.html).
