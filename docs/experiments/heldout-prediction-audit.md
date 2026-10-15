# Independent frozen prediction audit core

This additive daily observer reconstructs its numeric matrix independently of
production inference_data and heldout_predictions. It imports neither module,
production feature compiler, nor any target code. Code tests use tiny synthetic
DuckDB relations and fake native objects only. No actual source/CBM/native output,
queryY, fitted model or execution approval is opened by these tests.

The caller must first authenticate the complete decision lock, exact accepted
new-date source, model438 choice, original context/code/environment and all saved
prediction bytes. It supplies a private two-thread bounded DuckDB connection with
`heldout_prediction_queries`, `heldout_prediction_candidates`,
`heldout_prediction_base_features`, and chosen3-only
`heldout_prediction_extra_features` for W≠B. It supplies the accepted day counts,
B/W model specs, exact saved keyed arrays and `load_model(ref)` returning an
already byte-authenticated native object. `audit_day` has no CLI, file/model
opener, training, Pool, Y, approval writer or budget issuer. Caller-provided
snapshots do not authenticate themselves. Seven daily successes still require
one complete all-date independent seal and full owner lifetime acceptance.

Saved data has exactly artifact/model/feature_names, all-Q triples, calendar,
int32 group, int64 items and float64 finite scores. Queries are canonical unique
triples without targets; daily users/anchors, calendar maturity, typed shapes,
per-Q220 cap and complete group/key order are checked before native loading.
W=B requires the exact same model and artifact ref. Missing empty-C queries may
not be dropped. All source counts are bounded at2000Q/440000C per day.

The observer reads explicit query columns, independently assigns sorted query
groups, compares C versus B/extras using both EXCEPT ALL directions, and checks
B45 physical column order, typed metadata, F/Q user/anchor equality and strictpast
last-user-event timestamp. Source `_group` columns cannot shadow its numbering.
It checks retained staged Q before matrix SQL, after loading and after the final
guard. Existing temp names fail accidental same-connection retry; this does not
grant a repeat on another connection. Completeness and raw feature formulas are
the separate source oracle's scope, not proved again by numeric conversion.

The41 B inputs are39 physical numeric columns plus independently derived last
user event age in seconds and NULL mask. Extra keyed3 physical columns produce
44 W inputs, preserving NULL→float32NaN and known-empty zeros. Python exact integer
transport keeps query/product IDs out of a floating matrix. Row chunks≤65536 and
estimated allocation≤2GiB are enforced; actual outer RSS/CPU/wall supervision is
still necessary. W's superset is constructed once, B uses its first41 columns.
Age uses datetime subtraction; this study's event times are integer-second UTC.
No additional arm union, feature source calculation or model fit is performed.

Loaded native tree count300, feature names, all-effective parameters and empty
categorical/text/embedding index sets are checked before and after replay. Fixed
CPU Logloss300/depth6/L2=30/seed2026/settings and300-trained/300-scored/26000population
are verified. Only learning-rate serialization has its explicit1e-8 relative
boundary tolerance. Native replay uses RawFormulaVal, prefix0:300, thread2, and
skips predict for empty C. W=B reuses exactly one replay vector/call. A bounded
witness covers the whole W44 matrix before/after either replay, including extras
reachable through B's NumPy base view. This does not prove arbitrary native
internals; actual byte-authenticated model replay is the evidence boundary.

Every saved raw score is compared to independent float64 replay with1e-12
absolute/relative tolerance. Complete candidate order is checked separately using
raw-score descending/exact-product-ID ascending, so a near-tie perturbation
inside numeric tolerance that changes order fails. Every saved Q/calendar/key
matches the independent matrix domain. Return private_replayed_scores remains
ignored evidence; aggregate counts alone may be published. Original resource,
context-consumption, semantic/byte pins and process reaping/exit tail remain the
measured caller's obligations. Successful daily code return is not acceptance.

Twenty synthetic methods use three Q, three C, three B rows and three extras.
Literal gold checks all41/44 cells, NULL/age/masks, IDs above2^53 and raw vectors;
zeroC retains all Q, and W=B reuses one artifact/replay. Fault tests cover helper
shadowing, extra-key omission, F-user/future-time mismatch, floating IDs, float32
overflow, saved key/score/empty-Q corruption, near-tie order, embedding state,
reduced native precision, mutations of B or W-extra matrix values, target-bearing
saved Q rejected before loading, guard/consumed-connection behavior, and no file
or production matrix/scoring imports. These tests do not establish actual native
throughput, resource sufficiency, complete all-date output proof or heldout quality.
