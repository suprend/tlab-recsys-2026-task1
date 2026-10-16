# Wave041 B FIRST — audit weight mass before changing loss

**Disposition/mechanism.** Zero new IDs; one optional training-only accounting diagnostic under TLAB013/019. Keep current full-C query-weighted Logloss. Existing HYP027 already covers inverse-inclusion negative sampling; TLAB008 covers BCE/PairLogit. Neither becomes necessary from imbalance counts alone.

Disclosed counts imply390 informative and25,610 all-negative nonempty groups. Of496 full-Y-positive queries,106 have no retrieved positive;25,504 have empty fullY. Those106 are retrieval misses, not permission to insert targets or relabel other candidate items. A candidate's mature purchase0 is not an impression/dislike observation.

**Prediction/countercontrol.** Let n_q=|Cq|, p_q=|Cq∩Yq| and P=Σp_q/n_q. Current ideal query mass is26,000; weighted prevalence is π=P/26,000, not496/26,000 and not automatically444/5,317,058. Same-row uniform weighting gives the latter fraction; compare both only as an accounting control.[1]

At the analytic reference constant prediction π, unnormalized weighted-BCE gradient is w(π−y). All-negative groups sum to25,610π; informative groups sum to390π−P=−25,610π. Thus98.5% of query weight in all-negative groups does not imply98.5% of gradient pressure. This is our algebraic reference, not a claim about the actual model initialization, gradients or quality. Per-leaf gradients, Hessians and fitted residuals remain unmeasured. With realized floating weights, use actual total mass and block sums; the identity still holds up to arithmetic error.[2]

**Nearest finite UNRUN audit.** On exactly the same mature train Q/C/fullY, independently reconstruct n_q,p_q, actual weight sums and P; partition zero-Y, off-C-only-positive and retrieved-positive groups. Check total26,000 groups,5,317,058 C rows,444 retrieved-positive rows and the106-miss decomposition, then the analytic gradient identity. Preserve complete fullY separately from in-C labels. A mismatch falsifies accounting/binding, not the loss. No native execution, curves or fixture now.

**Goal benefit/negative outcome.** Eliminate a misleading reason for sampling/class weights before spending fits. Agreement only validates accounting; it does not establish calibration, ranking optimality or superiority. PairLogit would change gradient-support domain; uncorrected negative sampling changes the objective. No loss change is justified here; any later comparison needs unchanged Q/C/features/fullY and separately reserved fits/feedback.

**Full cost.** Zero fits/checkpoint or validation-model looks; one future training-label-derived diagnostic readout, not free feedback. Charge authentication and projected reads of Q plus N=5,317,058 C rows and M full-target rows(M unknown), grouping/join/weight arithmetic, state/spill and complete report/readback/failures. Reuse accepted per-query summaries only if actually available/verified; no free full-matrix build. Current study, opened final, clocks and budgets remain unchanged; no new gate/grant.

[1] [Actual query-weight construction](/Users/mdpospelov/tlab-recsys-2026/scripts/train_baselines.py:274).
[2] [Weighted Logloss documentation](https://catboost.ai/docs/en/concepts/loss-functions-classification#Logloss).
