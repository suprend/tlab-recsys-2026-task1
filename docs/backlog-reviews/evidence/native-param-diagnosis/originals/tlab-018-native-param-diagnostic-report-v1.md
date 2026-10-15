# One-shot native parameter diagnosis — reproduced and minimised

The separate Root diagnostic grant was consumed exactly once. The original018
EXIT1, partial Q/C/B45/extra exports and V6 failed_unknown_cleanup/unknown=true
receipt remain unchanged; no retry or new source-to-score episode was attempted.

The exact fixed B CBM was hashed before/after, loaded once and queried for its
parameters once. Exact protected `_same` and `verify_model` AST bodies reproduced
ValueError: `Native effective parameter differs`. Native metadata has300trees,
exact B41 feature order and no categorical/text/embedding inputs. No predict,
fit, source DB, Y,439, child process or project modification occurred.

Only two scalar values differ:

| Parameter | Expected | Loaded | Absolute difference |
| --- | ---: | ---: | ---: |
| bayesian_matrix_reg |0.10000000149011612|0.1000000015|9.883885376815726e-12|
| learning_rate |0.05000000074505806|0.05000000075|4.941942688407863e-12|

The saved-only loop reproduces the same error at the complete verifier, full
parameter dictionary and minimum single Bayesian float pair. Its last seam is
load-bearing: original `_same` receives just those two scalar inputs and their
original parameter path. Protected source uses absolute1e-12 for that path;
learning_rate already has a separate relative tolerance. No tolerance or code
was changed, and no float32/formatting hypothesis probe has run yet.

Full external reaped native process: expectedRED exit1, .26wall, .19user+.04sys
rounded, maximum RSS97,058,816B. Conservative rounding upperCPU.25/wall.27,
within15CPU30wall512MiB. Saved pure loop exit0: .03wall/.02CPU rounded, native0.
Body telemetry remains separate from complete-exit measurements. Script CPU15
hard fence and alarm30 were installed before native imports; RSS checks use
observed SELF peak, no hard-RSS containment claim.

Ranked falsifiable hypotheses were sent to Root before additional probes:
1. CBM loaded-parameter decimal serialization rounds accepted in-memory values.
   Prediction: matching float32 bits and native-format rounding explains both
   differences, without parameter/schema/model drift.
2. Absolute1e-12 at non-learning float leaves is narrower than stable serialized
   representation differences. Prediction: one narrowly specified representation
   check addresses the minimum RED, while meaningful parameter/schema mutations
   still fail. This is a candidate mechanism, not permission to relax the lock.
3. Handoff parameters reflect training memory rather than reloaded CBM metadata.
   Prediction: historical metadata agrees with expected values while loaded
   snapshots differ only in these representational leaves.
4. Wrong artifact/environment or true parameter drift. Prediction: hash/version,
   fixed setting, feature order or float32 bits differ. Exact matching CBM bytes
   and other metadata currently make this lower-ranked.

Root must decide the next limited pure discriminating checks and review any TMP
proposal. Current original28CODE, accepted core/parity and all frozen scientific
limits remain unchanged. The saved capture permits zero-new-LOAD regression
work. No repaired runtime or heldout result is claimed.
