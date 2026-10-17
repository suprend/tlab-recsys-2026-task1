# Wave088 candidates FIRST — retraining changes the comparison

**SOURCE-only; NEW0 / REFINE2 / proposed MERGE2 / ADMIT0.** Independent A: no088B/C or helpers read/contacted. Due02:15→next03:00UTC17Oct, original45-minute cadence retained. Individual research-start timestamp UNKNOWN; clock observed02:18:16UTC. Current Q=fixed-clock/48h eligibility, binary24h fullY; C0=P200+R20 union/no-refill. No impressions. Seven fixes/89 methods and tiny QYC/F270/Prepared246 are engineering evidence. Historical CIcross0/adaptive1189/403 remain unchanged; science/native CLOSED, remainderUNKNOWN.

## 1. Cross training policy with evaluation policy before claiming feature utility

**Dedup:** REFINE/MERGE TLAB-004/006/007/016/019, HYP-004/053/061–062; extends073/084/086 ceilings and087 frozen-score competition, without a new algorithm/ID.

**Mechanism/prediction.** A positive087 knockout can disappear after retraining because the ranker learns different item comparisons. Prospectively freeze C1 as084’s purchase-freshness cutoff-tie variant, retaining quotas/no-refill; if final unions coincide, stop. Report actual unique cardinalities: equal quotas do not ensure equal sizes. Freeze B41 and W44 feature recipes, learner, hyperparameters, seed and300 trees;1189/403 are not transferred choices. This tests fixed recipes, not feature-search productivity.

Let M[f,t,e] denote fullY positive-query macro NDCG@20 for feature bundle f, training candidate policy t and evaluation candidate policy e. Four fresh models, each evaluated on both policies, give eight cells. For each f:

`M[f,1,1]−M[f,0,0] = (M[f,0,1]−M[f,0,0]) + (M[f,1,1]−M[f,0,1])`.

First term is the inference-policy contrast with one frozen scorer; second is retraining at fixed evaluation C1. Also report the reverse path and their interaction. W−B at each identical(t,e) is recipe-specific feature utility. Retraining changes positive support, negatives, informative groups and weights; its term cannot be called a negative-only effect. For087-style list restriction, compute each model’s scores once on C0∪C1, requiring list-independent features and deterministic ties. If features depend on C, report an inference-policy contrast including rescoring;087’s monotonic guarantee does not apply.

**Counterhypothesis:** recovered candidates remain unrankable; changed training support dominates; W helps only one policy; a tiny positive cohort leaves uncertainty unresolved. No current bottleneck, source superiority, exposure or causal-lift conclusion follows.

**Nearest test, UNRUN:** four literal queries × four supplied scorers × two lists =32 metric evaluations; eight aggregate cells, two path identities and four feature contrasts;0fits/data. Independently verify fullY denominators, off-C misses, empty-C positives and separate empty-Y convention. Proposed≤5CPU-seconds/10wall/128MiB; measured cost/adequacyUNKNOWN. Identity failure rejects the checker; agreement accepts bookkeeping only.

## 2. A negative-only bridge is a separate estimand

**Dedup:** REFINE/MERGE existing TLAB-008/013/016/019 training-negative controls, not another retrieval hypothesis.

For matured TRAIN queries only, fix positive rows S=Y∩C0∩C1 and their weights. Swap N0=C0\Y versus N1=C1\Y while preserving each query’s total negative weight and feature values; negatives split that mass uniformly. Predeclare one common training cohort with both negative sets nonempty; disclose excluded queries. Evaluate on the original unfiltered evaluation cohort/fullY. Do not insert off-C positives or remove later purchases. Preserve the pinned objective: PairLogit requires explicit pair weights/normalization rather than substituting object weights. This diagnostic risk differs from native policy training.

**Prediction:** two B-only bridge fits can change rankings on one identical evaluation C despite identical positive rows/masses. **Counterhypothesis:** both negative sets convey equivalent information; optimizer variation dominates. A difference describes this controlled training intervention, not dislike/exposure or how much of native-policy gain it explains. No difference rejects only this finite mechanism witness.

**Nearest test, UNRUN:** three train groups with common-positive/negative-change, no-common-positive and empty-negative cases; two alternative weighted lists each, six mass checks;0fits. Same proposed tiny cap; accept only exact preserved masses/cohort accounting, otherwise reject.

**Conditional future work, not admitted:** one separately reserved development slice,≤200 train/100 evaluation Q,≤220 native-C rows/Q,≤440 union rows/Q,≤6000 fullY pairs (abort, never truncate). Proposal1:4fits×300iterations;≤176000 union-score values,800 query-list evaluations. Proposal2 adds2B fits×300 and≤88000 scores/400 evaluations. Combined ceilings≤2250CPU-seconds/2700wall/6GiB RSS/2GiB scratch/512MiB physical authenticated reads, including preparation/failures/cleanup; insufficiency means defer. All cost/adequacy UNKNOWN; no grant or human-budget request. Accept a future readout only after independent cell/row/weight/score/cost reconciliation; otherwise reject as invalid. Report uncertainty using at most1000 paired-user resamples of the eight-cell vector for predeclared contrasts; insufficient positive support means inconclusive, not a winner.

**Primary evidence:** [Shi et al.,2023 §2.1–3](https://arxiv.org/html/2302.03472v2) explicitly parameterize negative distribution in BPR’s objective; its HNS theorem does not establish our boosting result. [Zhou et al.,2023 §4.2–4.4](https://aclanthology.org/2023.findings-acl.332.pdf) cross negative generators/reranking sources and show matching alone need not win; passage results do not transfer numerically. [CatBoost PairLogit docs](https://catboost.ai/docs/en/concepts/loss-functions-ranking?lang=en) distinguish pair/object weights. [Yi et al.,2019 abstract](https://research.google/pubs/sampling-bias-corrected-neural-modeling-for-large-corpus-item-recommendations/) concerns in-batch two-tower sampling; logQ is not a deterministic-policy support repair.

Task1 utility: separate a candidate-policy comparison, retraining adaptation and fixed-recipe feature benefit before paying for retrieval complexity. REJECT new mandatory IDs, claims of measured gain or reopening frozen final; STOP after SHA/readback freeze.
