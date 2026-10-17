# R2 — crossed metric/oracle audit

Reviewed test-coverage and feature-automation FIRST reports with their pinned bytes; rechecked the relevant frozen oracle/test seams (12 exact paths/ranges in R2 pins). FIRST remains immutable. **New confirmed actionable defects: 0.** No peer clean result is treated as proof of runtime correctness.

## Independence and precision

The source-oracle dependency identified by test coverage is real: `tests/oracles/feature_program_audit.py:188,221–224` reuses producer plan/schema composition. Independent vocabulary/value formulas (`48–128`) and all-Q preservation (`218`) narrow the gap; they do not independently establish physical F57 order. An independently literal ordered57 tuple plus same-type cross-grain column swap would discriminate this coverage gap. No current wrong order was demonstrated.

Feature/model independence is stronger at the arithmetic seam: `tests/oracles/feature_program_model_audit.py:127–196,238–275,283–410` separately reconstructs metrics, user draws, weights and ordered matrices. Inputs are float32, IDs int64, groups int32, relevance int8; expected query weights are float64 (`209–231,250`). This proves expected input mass/witnesses, not original native training weights; that limitation is explicit (`956`). Base order comes from authenticated names; literal matrix tests remain necessary alongside historical-loader equality.

Heldout prediction oracle independently rebuilds group numbering/projection and requires saved/native **float64** scores (`heldout_prediction_audit.py:87–140,149–183,210`). Exact complete ranking equality supplements numerical tolerance. Existing tests distinguish >2^53 keys, NULL/masks, omitted empty-C Q, float32 native output and near-tie rank changes (`test_heldout_prediction_audit.py:47–53,88–110`). Metric oracle independently computes full-Y denominators and repeated-user contributions; its bootstrap test uses literal multiplicity formulas (`test_heldout_metric_audit.py:27–44`). Shared Python RNG specifies draws; it is not shared production metric arithmetic.

## Minimal combined nonlinear literal witness — proposed, UNRUN

Use K20, M=2^60, canonical C IDs M…M+20 for query A1/user A. All21 scores are float64 zero; Y={M+19,M+100}, with the second target outside C. Correct top20 ends M+19: Recall1/2 and NDCG `a=(1/log2(21))/(1+1/log2(3))`. Now change only score(M+20) to float64 `1e-50`: correct target rank21, hence0. Premature truncation or float32 score rounding incorrectly retains the hit. Exact ID ties, complete source-score keys and full-Y IDCG are independently observable.

Add A2/same user with empty C/Y={z}; B1/user B with two candidates ranked as two hits and full Y of size3; C1/user C with mature empty Y; Z1 censored with Y=None. Total:5 Q,23 C,6 mature target pairs. B1 NDCG is `b=(1+d)/(1+d+1/2)`, d=1/log2(3).

For the zero-score variant, independently expected Recall values are conditional query7/18, conditional user11/24, target micro1/2, all-query-zero7/24, all-user-zero11/36. NDCG counterparts are `(a+b)/3`, `(a/2+b)/2`, `(a+b)/4`, `(a/2+b)/3`; no pooled NDCG substitution. Censored Z enters no mature denominator. Removing A2 or C1 changes these golds.

Against an all-miss paired model with identical Q/Y, enumerate27 ordered draws of mature users A/B/C. CCC is conditional `None`, all-zero0; AAB query-macro is `(2a+b)/5`, user-macro `(a+b)/3`. No redraw or independent model draw is allowed. If reused for accounting, candidate-row weights are float64 1/21 and1/2; empty groups have no invented row weight.

Existing tests already cover the component invariants; this combined cutoff/precision witness is optional integration coverage, not a new defect, hypothesis ID, admission or mandatory gate. Static inspection/hash/readback only; no project imports, tests, SQL, native/model/data operations or numerical execution. Cost UNKNOWN. R2 frozen; STOP.
