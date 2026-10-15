# Wave028 FIRST — full-Y loss alignment

**Disposition:** zero new IDs; refine TLAB006/TLAB008 and own wave008 coverage-oracle argument. Optional future research; no current recipe, cohort, CI, tolerance, or gate changes.

**Mechanism.** Let m=|Yq|, h=|Yq∩Cq| and D(k)=Σ[j=1..min(20,k)]1/log₂(j+1). For h>0, NDCGfull=rq·NDCGC, rq=D(h)/D(m). Thus a hypothetical loss whose pair coefficients are linear in ΔNDCGC can use rq to reproduce full-IDCG coefficients. This is an algebraic surrogate-weight adaptation, not a quality claim. Current B/W Logloss has no IDCG normalization; existing PairLogit uses 1/(p·n), not ΔNDCG. Clipping, sampling, and per-query renormalization require separate inspection.[1]

**Prediction/counterexample.** Fix C={a,b}, a positive, b observed nonpositive. Query A has fullY={a}; B has fullY={a,z}, z outside C. Moving a from rank2 to rank1 gives equal shortlist improvements δ=1−1/log₂3, but full improvements δ and δ/(1+1/log₂3). Shortlist normalization relatively overweights B by 1+1/log₂3. Conversely, if every informative query has equal rq, matched global weight normalization removes the relative allocation difference. No weighting retrieves z: the full metric ceiling remains D(h)/D(m). Off-C targets are never negatives.

**Nearest finite UNRUN experiment.** A four-query literal specification: A/B above; C with fullY={z}; D with empty mature fullY. Each has the same two-item C. Compare two fixed rank orders, then analytically compare pair coefficients under shortlist versus full normalization. C has constant-zero full NDCG and no positive-negative ranking pairs; D has undefined conditional metric. Preserve both in their original evaluation domains.[2] Any dropped C, fabricated positive, or undefined-ratio weight fails the control.

**Strong control/task1 benefit.** A later authorized trained contrast must keep Q/C/features, mature labels, pair-support masks, seeds, iterations and pair enumeration identical; alter only the declared coefficient multiplier, with a common global mass convention. Keep zero-pair groups identically handled. Comparing a new listwise loss against current Logloss would confound support and objective. This prevents automatic feature selection from miscrediting coverage-dependent query weighting as feature discovery. No prediction feature or query selection may depend on rq; full label windows must mature before fit.

**Cost/negative outcome.** Literal scope: 4 Q, 8 C rows, 4 target rows, 16 returned positions, 2 eligible pairs, zero fits. Future preparation costs O(Σ(|Y|+|C|)) membership work plus existing O(Σh(|C|−h)) pairs and O(Q) weight state; both fits, full source/authentication, checkpoints, scoring and failed attempts are charged. No grant. A failed identity falsifies implementation; no prospective gain or harm leaves this deferred, without retuning current final.

[1] [Canonical loss/support contract](/Users/mdpospelov/tlab-recsys-2026/docs/experiments/boosting-baselines.md:9).
[2] [Primary evaluator implementation](/Users/mdpospelov/tlab-recsys-2026/scripts/ranking_metrics.py:113).
