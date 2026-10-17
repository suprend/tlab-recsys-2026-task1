# R2 — crossed review of model-selection P2

**Confirm P2, with narrow scope.** The historical strong-control producer and its two oracles accept a score-vector discrepancy that changes deterministic ranking and therefore reported NDCG. This is a logically insufficient artifact-parity predicate, not observed native corruption or evidence that historical accepted outputs are wrong. The new ordinary CLI is protected.

Scope: frozen HEAD `c538de4097322715fccac494e2b2becc3279e8e1`; shared manifest `7e2e871f148beac5b9fce3aa23970b370db0c8fdc9eac89958fb6342a4d2a41a`. Read peer `audit_model_selection_r1-FIRST.md`, pins and freeze; both report/pins SHA match that freeze. Relevant source slices are listed in R2 pins. Original root is `/Users/mdpospelov/tlab-recsys-2026/`.

## Independent source trace

* `scripts/strong_baseline.py:383–389` predicts a prefix from the full model, copy/shrink/saves/loads the selected prefix, then checks only tree count plus `allclose(scores,replay,rtol=0,atol=1e-12)`. Lines 390–396 rank/evaluate/save **scores**, never replay. `train_baselines.py:328` orders by group, descending raw score, then item ID; there is no near-score tie band. `ranking_metrics.py:124–133` uses that exact ordering for DCG/IDCG. The historical winner selection uses conditional query NDCG (`strong_baseline.py:227–233`), so rank changes can affect the actual selection quantity.
* `tests/oracles/strong_output_audit.py:315–316` and `strong_recovery_audit.py:397–398` compare full/prefix vectors numerically, then call `scored(pred,...)` only. Their `scored` implementations independently use the same lexicographic order (`:226–231` / `:305–310`), then their own `metric_values`/`summarize` compute top20 NDCG (`:77–94` / `:78–95`). Neither compares rankings or metrics of `pp`.
* Both NPZ gates (`strong_output_audit.py:232–238`; recovery `:311–317`) check exact keys, finite scores and tolerance to `pred`; NPZ ranking is not independently compared. Checksums still detect an unresealed file mutation. This finding assumes otherwise valid metadata/pins; it is not a checksum bypass.

## Stronger minimal witness: no exact tie

One mature Q; groups `[0,0]`, items `[1,2]`, fullY `{1}`. Let full-prefix scores be `[5e-13,0]`, replay scores `[0,5e-13]`. Both vectors are finite, contain no score ties, and every absolute difference is `5e-13 < 1e-12`. All cited numerical parity predicates accept them, with identical other metadata.

Full ranking is `(1,2)` and NDCG@20 is 1. Replay ranking is `(2,1)` and NDCG@20 is `1/log2(3)≈0.63093`; AP/MRR change from 1 to 1/2, while Recall@20 stays 1. The ID tie-break never determines either result. Thus top20 contains both products but the validation metric still changes. This is an arithmetic counterexample inferred from the actual predicates and metric calls; no code was executed to reproduce it.

## Practical boundary and remedy

Keep P2: a localized completeness defect in the historical acceptance checks, potentially material for near ties, without observed frequency or a demonstrated CBM roundtrip that produces it. Do not infer wrong current B/W/final results or elevate to P1. Historical contracts remain distinct.

`train_development.py:130–138` first checks numeric tolerance and then requires equality of all three full/selected/reloaded rankings. Its existing regression `tests/test_train_development.py:308–326` targets this mechanism. Adaptive oracle also checks exact full-prefix/selected/saved ranks (`tests/oracles/adaptive_tree_selection_audit.py:174–175`).

Suggested independent bounded check: supplied-vector, native-free negative fixtures through historical producer/oracle parity seams; intact vectors must pass, the no-tie swap and NPZ-only swap must fail without extra fit. Apply exact-ranking parity while retaining numeric tolerance. Runtime occurrence remains a separate question.

Only static reads/searches and stdlib JSON/hash packaging/readback ran. No tests, project imports/functions, prediction, native/model loading, fit, SQL or data reads. Own FIRST remains immutable. STOP after R2 freeze.
