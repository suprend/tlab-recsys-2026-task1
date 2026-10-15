# Independent fixed-procedure feature-program model output observer

`tests/oracles/feature_program_model_audit.py` implements the prospective 016
zero-fit output observer contract and its owner-attempt amendment. Code review
and exact external execution approval are prerequisites; this module grants no
fit, source-regeneration, heldout or promotion authority.

The entry requires `--context` and the controller's original
`--issued-context-sha256`. It parses the same bounded raw bytes whose digest was
verified, confines paths to the specified checkout, and authenticates the exact
execution approval, global four-fit/four-look/one-observer claim, pre-preparation
owner-attempt claim, immutable producer report and all four original worker
slot/context/consumed/launch receipts. Accepted historical source and 019 control
consumers authenticate lineage; their planners/loaders/metrics do not define
expected model arrays, scores or the decision. This consumes their historical
reviewed records, rather than providing a generic fresh-clone bootstrap.

Expected arrays come from independent SQL over accepted Q/C/manual F and the
selected columns of accepted F57. Queries are selected by bottom SHA before Y is
opened, then assigned stable query order. Full Y retains targets outside C and
queries with empty C. Group and item IDs stay exact integers; only the immutable
B41 and one approved three-column physical arm enter float32 model inputs.
The observer checks B41/Q/C/Y preservation, typed three-column closure, finite
inputs except allowed NaN, recency/missing masks, preallocation bounds, query
row mass and the agreed canonical little-endian matrix witnesses. No compiler
or production model-data loader computes these expected values. Prior B41 and
selected-source formula proofs remain prerequisites and are reused.

Successful arms must bind exactly full CBM, numeric full JSON, scoring-prefix
CBM and a typed score NPZ. The observer loads saved models and predicts with two
threads, performs zero fits, verifies native fixed parameters (including the
explicit declared .05 to effective float32 learning-rate conversion), numeric
feature order/no CTR, full trained iterations and scoring prefix separately.
Saved scores, prefix replay and complete-model prefix replay must agree within
absolute 1e-12 **and** produce identical complete per-query deterministic
rankings, including product-ID tie breaks. A small score tolerance alone cannot
excuse a ranking change. Recognized resource-failed original arms remain paid,
preserved and ineligible; unknown/integrity/API failures stop. Successful workers
must satisfy issued limits; all workers must satisfy the conservative parent
plus worker 8GiB peak ceiling.

Full-Y Recall, NDCG, AP and reciprocal rank are independently recomputed for
conditional query macro, all-query zero, conditional user macro and all-user
zero estimands. The already frozen chooser uses the inclusive B Recall minus
.002 guard, the band within 1e-12 of the global maximum conditional query NDCG,
then fewer added physical columns and lexical candidate ID. The observer checks
the recorded winner against its own result. Only afterwards it reports NDCG W−B
for each four estimands using the same 200 paired-user draws, seed 2026.
Undefined draws are retained, never redrawn. This descriptive post-selection
bootstrap does not correct selection bias, guarantee power or model shared
shocks across the two development evaluation dates.

The fresh observer uses absolute process CPU including imports, a deadline
inside the original owner's clock, at most 600 CPU seconds, two SQL threads,
7GiB process RSS, zero subprocesses and SQL interruption from a monitor. Shared
source + owner SELF + reaped CHILDREN is sampled and charged once, with unknown
cost rejected. SQL uses a bounded small chosen-Q table; no whole-phase wide
feature CTAS. Final input/output pins and SQL close precede the resource sample.
Small authority rechecks, evidence fsync and process exit tail remain charged by
the supervising parent's reaped counter. Exit zero, absent known-failed markers
and the final external lifetime receipt are required beyond the evidence file.
Terminal failures preserve their primary exception and write a failed receipt
where possible. Aggregate output includes no query, user or item identifiers.

The matrix witness and reviewed worker code/receipts support expected input
values and row mass. **Native fit weights cannot be recovered from a CBM.** The
observer does not claim a new exhaustive proof of prior manual feature formulas,
heldout quality, cross-dataset generalization or an independently reproduced
training execution.

The scoped synthetic suite uses at most 11 total Q/C/Y/F/F57 input rows per SQL
fixture, mocked saved-model APIs and tiny receipt files. It covers four estimands
with literal gold values, full-Y misses/empty C, IDs above 2^53, label-independent
sampling, optional query-column shadowing, canonical NaN witnesses, exact tie
order, microsecond ages, native learning-rate serialization, a score-tolerant
ranking change, fresh-resealed launch tampering, paid resource failure, original
issuer bytes, terminal close/late-marker failures and primary-error preservation.
No actual accepted source, CBM, Pool or native fit is opened by these tests.

## v2 review corrections

The observer exclusively creates `observer/execution.consumed.json` after cheap
issuer/approval/global-claim/launch validation and before the first paid input
pin stream. Its exact same-byte SHA is retained as `execution_consumed` in the
evidence and final authority pins. File and parent directory are fsynced before
paid work. The parent-issued one-call claim alone was insufficient to consume a
child execution after lost receipt; a second entry with the same issuer now
fails before streaming. Failure does not grant an automatic observer retry.

Successful immutable producer reports additionally require `active_slot:null`,
`unknown_live_fit:false`, `unknown_metric_looks:false`. Own `evidence.failed.json`
is checked before success persistence, during repinning and at terminal return.
A stale or late own failed marker prevents verified exit even when the parent
would independently reject it. The original c2e6 version and independent failed
regressions remain archived; expected arrays/metrics/model math are unchanged.
