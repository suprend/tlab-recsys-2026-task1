# Wave093 B FIRST — candidate-only selection cannot identify the fullY winner

**SOURCE-only; NEW0 / REFINE1 / proposed MERGE1 / ADMIT0.** Independent author B; no current093 peers/helpers read or contacted before freeze. Research/research-campaign applied. Original due06:00UTC/09:00MSK17Oct and next06:45UTC/09:45MSK unchanged. All experiments **UNRUN**, cost/adequacy **UNKNOWN**; science/native allocations CLOSED, remainderUNKNOWN. Historical final CIcross0 and adaptive1189/403 remain unchanged.

## One refusal, with a finite distinguishing witness

**Dedup.** Refine existing HYP-002/046, TLAB-006/016/019 and wave028's full-IDCG coefficient distinction; merge with039 native-selector and round065 importance boundaries. This is an information-boundary application to automatic feature selection, not a new loss, retrieval ceiling, pipeline defect or HYP. Wave088 already covers policy×feature×retraining; do not duplicate it with another trained grid.

**Actual contract.** `candidate_pilot.py:37–107` builds popular/recent C from events/Q and deduplicates without refill; fullY joins afterwards for coverage. `train_baselines.py:277–320` supplies candidate-row labels and weights1/|Cq|, retaining fullY separately. `feature_programs.py:98–159` generates eight symbolic bundles without learned utility scoring. The frozen016 selector uses external fullY NDCG20 plus Recall guard, then whole-bundle tie rules: [selection contract](/Users/mdpospelov/tlab-recsys-2026/docs/experiments/feature-program-selection.md). No current learner or selection failure is alleged.

**Mechanism.** A generic selector given only candidate features, in-C labels, groups and existing weights cannot always reproduce this external selector: different off-C fullY can leave all its inputs unchanged while reversing feature-arm preference. This is stronger than saying native loss differs numerically. It rejects an exact drop-in replacement without additional fullY information, while permitting a native proxy as an explicitly different procedure.

**Primary source.** Tagged [CatBoost v1.2.10 core.py](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/python-package/catboost/core.py), retrieved lines4224–4400, describes `select_features` as loss-based elimination, documents full training per step and optional final fitting. It supports ByTags group selection: atomic bundles are therefore feasible in principle, not an API impossibility. A custom objective is rejected there; whether a particular fullY-aware custom metric could drive native elimination remains **UNKNOWN**, not ruled out. [Tagged weighted Logloss](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/docs/en/concepts/loss-functions-classification.md), lines6–17, depends on supplied row labels/weights. Our primary [evaluator source](/Users/mdpospelov/tlab-recsys-2026/scripts/ranking_metrics.py:113) instead uses full target count for IDCG.

**Literal prediction, hand reasoning only.** Five mature queries have distinct users. q1/q2 each have C={a,b}, in-C positive a. ArmA orders a,b on q1 and b,a on q2; ArmB reverses both. q3 has two nonpositive candidates and fullY={z} outside C; q4 has two candidates and emptyY; q5 has emptyC and fullY={z}. Remaining scores/orders are identical across arms. IDs are query-scoped roles; z is never inserted.

WorldX has Y1={a,z}, Y2={a}; WorldY swaps that extra off-C target. All candidate inputs/scores/weights are identical between worlds. Put d=1/log2(3). The external conditional macro difference A−B is

`X: (1−d)(1/(1+d)−1)/4 < 0; Y: −X > 0`.

Both arms have Recall20=3/8 in each world, so the Recall guard cannot resolve the reversal. Off-C-only and positive empty-C queries remain zero within the four-positive cohort; emptyY remains in the separate zero convention. Candidate-only deterministic selection must return the same choice in both worlds. Neither world describes impressions, inventory, dislike or actual current support.

**Counterhypothesis/limit.** Actual candidate-only and fullY choices may coincide; equal per-query IDCG scaling can preserve an ordering. An external fullY-aware evaluator can distinguish these worlds, as016 already does. This witness establishes no actual superiority or feature-search productivity.

**Nearest finite experiment, UNRUN.** Two supplied arms×two label worlds×five Q =20 query evaluations, four aggregate cells. Each world has5Q/8C rows/5 fullY pairs; physically share16 arm-score values. Across cells count32 returned positions and report four existing estimands per cell. Zero fits, model/API calls, training updates or real data; retain all controls. Accept bookkeeping only if in-C inputs remain identical, the two signs reverse, Recall ties and cohorts match. Otherwise reject the witness/checker. No empirical gain is accepted.

**Budget/benefit.** A future separately authorized literal checker could propose≤5CPU-seconds/10wall/128MiB including input, arithmetic, verification and failures; adequacyUNKNOWN, no grant. Native RFE would require a separate complete fit/feedback ledger, not reuse four016 slots. Avoid paying for an alleged exact replacement that lacks the decision's information; preserve the already sufficient external selector and focus original task1 on auditable generation and matched fullY evaluation.
