# Heldout prediction core — independent review v2

**CHANGES REQUESTED — one material P1.** Scope only pure structural/core code,
not executable owner/budget/source acceptance/model-native replay/Y capability.
Reviewed all three v2 paths in `<temporary>/tlab-heldout-predictions-freeze-v2.json`,
accepted `inference_data`/`heldout_contract` interfaces and all author tests.
Source79a35bb01b71866141503e8409f91739141dc532c4c0d0c1d202d52182e794b0,
test04dab781e2a5638c255d68d5dffaeef94d398938ef54d467de9ec93057602e4f,
docce970986016914c5b5d82d45ac8a674df7d9a6dbdde5accbb6f95ec90f26af16
were identical before/after (`<temporary>/tlab-heldout-predictions-review-pins.json`).
Root's v1→v2 embedding guard correction is included; v1 was never accepted here.
No repository edit/Git, actual source/Q/Y/CBM/model, native predict/Pool or fit.

## P1 — post-predict score identity is not the validated input identity

`score_day` validates InferenceData at line129, calls prediction at131, then only
rechecks the model/raw score vector. Lines136–137 copy **current mutable** data
queries/maturity/group/items. A predictor holding the loader's data reference can
change these between validation and copying. W=B skips the B/W cross-check and
returns an apparently successful result with altered score association.

Independent fake-model probes reproduced four accepted invalid transitions:

1. Change item2^60+1 to2^60+2: still typed, unique and correctly sorted, but the
   scores now identify a different candidate. Re-running only structural
   validation after predict would **not** reject this case.
2. Replace the second item with the first: duplicate output candidate keys.
3. Move a row into group2 while there are only two queries: orphan group.
4. Append a synthetic target set to a query tuple: returned FrozenScores now
   violates the explicit triple-only/no-target output contract.

These are injected boundary faults, **not a claim actual CatBoost mutates these
objects**. Like the existing author's model-state mutation fault, they test
whether successful returned core output satisfies the advertised invariants
when live state changes during a callback. The bug is relevant independently of
model-byte authenticity or source-formula proof.

Minimum repair: retain exact deep Q triples/calendar/group/items snapshot before
prediction; after native call, resource guards and model verification revalidate
live data **and compare exactly with the pre-call identity**; construct returned
output from the retained snapshot. The same rule applies to emptyC and W=B paths.
Root accepted finding and proposed additionally a bounded-chunk float32 x
pre/post byte witness without a second whole-matrix copy; this is not tested or
accepted until a new freeze. It proves witnessed input stability, not arbitrary
native internal behavior or actual training weights.

## Evidence and accepted core limits

Author v2 suite:18 unique synthetic tests PASS .031s, exit0 under
ResourceWarning-as-error. Independent source
`<temporary>/tlab-heldout-predictions-own-probes.py`, raw red log
`<temporary>/tlab-heldout-predictions-own-probes.log`, machine results
`<temporary>/tlab-heldout-predictions-own-probe-results.json`:6 test methods/.009s,
4 failed assertions (group/target cases share a subtested method),0 errors.
Passing controls independently cover embedding rejection before data/predict,
strict boolean user rejection, narrow LR-only tolerance, and returned arrays/
queries owning copies after successful return. The failed tests are preserved,
not counted as passing. Actual row arrays are small fake fixtures; no file/data
loader or native model was opened. Code-only hashes are the sole fingerprints
read.

Unchanged core design otherwise coherent:

- Caller-authenticated lock/choice/source boundary is explicit. Pure refs and
  supplied callbacks are not source/model acceptance; a custom loader remains
  trusted caller code and must be included in the future owner's code closure.
- Complete7-day inventory/date/count/maturity and canonical Q triples/int64
  items/int32 groups/float32 x are checked, allQ/emptyC retained. Model tree300,
  ordered B41/B44, numeric cat/text/embedding checks, exact effective parameter
  snapshot and declared .05 float32 LR boundary precede and follow prediction.
- Native call fixes RawFormulaVal/start0/end300/thread2. W=B uses one call and
  the exact same result object; emptyC skips predict. Returned copies are
  separate from original loader arrays after construction.
- No owner claims, source truth proof, CBM bytes, write/seal, resource lifetime
  or target unlock are implemented or implied. Outer supervisor must interrupt
  native calls and charge unknown/failed calls, close/fsync/exit tail. Independent
  source/native output replay and all7 prediction seals remain prerequisites to
  any query-level reservedY. No new allocation or heldout metrics were opened.

Hold v2 unchanged until Root publishes repaired exact source/tests/doc. Targeted
rereview should use a new copy of the original harness changing only its
freeze-file path, preserve test bodies/red history, then add independent finite
x mutation evidence. No full suite/actual/native work is needed for this core
repair.
