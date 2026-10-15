# Label-blind inference narrow rereview — CODE ACCEPT

Exact frozen SHA before/after unchanged:
- scripts/inference_data.py `3ed9e1c2d06d77302d1d39dbe2604fb7d778e18a4dcb583d3eb7ddd30236f8dd`;
- tests/test_inference_data.py `fe6bf6a78d0dad50556f1390012beed569c2e2a1451ff85c3b584dae00b44f88`;
- docs/experiments/label-blind-inference.md `9f3283186ec03c67051e2a1b8faedf68a41b6dde66ac39b1c0f27a17669009f3`.

Original P1 is closed. The chosen-Q table explicitly projects query_id/user_id/anchor/label_is_mature before computing its own index. Re-running my original valid Q+optional BIGINT `_group=0` fixture now returns groups[0,1] and exact pairs[(a,9007199254740993),(b,42)], with all three Q including emptyC retained. The original silent association of b's candidate to a no longer occurs.

Own four tiny tests PASS: original alias regression with BASE41+extra3, exact BIGINT/NaN/no y output; five reserved clock/key names rejected in BASE before SQL; poisoned external outcome-file mutation leaves arrays unchanged and label_paths argument is rejected; all-false maturity retains all Q/C. Each fixture uses at most8 input rows. Author10tests were not repeated because the original defect and new boundary were independently covered. No real source/heldout/model/Pool/predict/fit execution.

The reserved-name guard now applies to every expected model name, closing the prior maturity-prefix observation. Its exact set contains clock/key metadata, not every possible outcome alias such as literal y or target. The API has no Y input/output, but physical names/types alone cannot prove feature semantics: caller must still supply frozen final B41+selected3 feature names and externally accepted source/calendar provenance. This accepted physical-boundary scope does not authorize source use, scoring or heldout decisions.

Evidence `tlab-labelblind-inference-independent-rereview.py`, `tlab-labelblind-inference-independent-rereview-results.json`. Measured after fixture/import setup: SELF0.102338s, wall0.091698s, peakRSS123568128bytes. Original8c4 report/helper/results are retained; no production edits were made by the reviewer.
