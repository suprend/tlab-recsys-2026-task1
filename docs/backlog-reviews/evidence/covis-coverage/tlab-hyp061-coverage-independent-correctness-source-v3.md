# HYP-061 coverage consumer V3 — independent targeted SOURCE re-review

**SOURCE PASS for the reviewed correction and unchanged estimands; no new supported correctness finding.** My V1 target-window P2 is closed by the actual V3 source and retained synthetic evidence. This does not admit runtime, bind actual inputs, accept Q6000/Y/outputs or close the separately disclosed diagnostic/resource limitations. Root remains sole owner of those decisions.

## Target-window P2: closed

[coverage.py:208](/tmp/tlab-hyp061-coverage-proposal-v3/coverage.py:208) now requires `start <= stamp < start + timedelta(hours=24)` and preserves `same == (stamp == start)`. This matches frozen clock-48h's 24-hour target, included anchor and excluded right endpoint; 48-hour eligibility is no longer confused with target duration. The rejected V1 line and my original CHANGES REQUESTED report remain unchanged historical evidence.

[test_coverage.py:180](/tmp/tlab-hyp061-coverage-proposal-v3/test_coverage.py:180) contains **seven literal subcases** with explicit timestamps/flags and independent expectations: accept anchor with true same-second and t+24h−1 microsecond; reject exact t+24h, t+30h, t+48h, pre-anchor and anchor with false same-second. Accepted cases assert the target is added; rejected cases require `FullY window witness`. The apostrophe-containing fixture path also exercises quoting. These tests were inspected as text, not rerun by this reviewer.

## Actual delta, native boundary and preserved BEFORE_Y

The actual V1→V3 production diff was reconstructed as text and equals the production portion of `V1-to-V3.diff` exactly. Only `read_labels` changes: the endpoint correction and the requested native allowlist boundary. V3 production is **byte-identical V2**; V2→V3 changes only allowed-path comparison ordering in the integration test and synthetic runner8 CPU/16 wall limits. Consumer120CPU/180wall,1GiB cooperative RSS,512MB engine/two threads/no spill and output16MiB remain unchanged; adequacy remains UNKNOWN.

At [coverage.py:184](/tmp/tlab-hyp061-coverage-proposal-v3/coverage.py:184), the closed BEFORE_Y marker is still authenticated first. Before importing DuckDB, paths are required to be exactly three distinct resolved existing literal `labels.parquet` files, without glob characters. After connection creation, source lines193–195 install the exact list with apostrophes doubled, set `enable_external_access=false`, then `lock_configuration=true`, **before** the first native label relation at197. All original pre-Y stream validation, opaque label hashing, exclusive marker write/close/hash and late closure are otherwise byte-preserved from V1. This is a native relation allowlist, not an OS sandbox or physical-IO exclusion proof.

The unmocked invented integration records actual current native settings before each relation. V3 compares sorted allowed lists rather than assuming DuckDB preserves input order; exact multiplicity/cardinality remains checked, so missing/extra/duplicate paths do not become acceptable. It separately checks `(external_access, lock) == (False, True)`, requires re-enabling external access and reading an undeclared fourth valid Parquet to fail, and confirms all three declared files still work. The earlier V2 attempt failed precisely on ordering of returned `allowed_paths`; source/production behavior did not change to make that fixture assertion pass.

## Estimands and decision policy: unchanged

`estimands.py` is byte-identical across V1/V2/V3 at SHA `3aa8e4b2d49e275de399e27e5190437d0a9818977ebcb5de2a88f3954fac6a49`; `test_estimands.py` remains `b612737c5a2bc90dbadabd9083330335ea94c9806fd9332ad5d65ba4a776053c`. The authoritative plan still hashes to `b8896d7f7ee7a12593cdfdfe4f7f3fc4a58bddbd9e3f7312b96de895a104565f`. No source change affects six arms, complete fullY/off-C targets, same-Q+ full-C query-macro contrasts, new/repeat denominators, all-distinct-user frame, all-day multiplicity, shared2000 draws/seed61061/Random.randrange, ASCII-query and ascending-user reductions, type7, undefined-primary interval handling or the continuation condition `Δcos−C0≥.005 && lower95>0 && Δmatched_cos>0`. Count is still secondary; no normalization, causal or generalization claim is added.

## Synthetic evidence and historical failures

The sole V3 raw log reports15/15 PASS,0 failures/errors/skips on DuckDB1.5.6. Its exact tested-source manifest matches the current files; outer terminal reports exit0/reaped/no retry,4.592914 child CPU seconds,4.607396041 wall seconds and175538176B peak RSS. I checked these existing observations and source hashes only; **no test or native SQL was executed during this review**. Combined four author suite attempts report16.250314 child CPU/16.614496624 wall seconds; inner and outer measurements are not added twice.

The earlier V1 exact-decimal gold failure and V2 allowed-list-order failure remain in nested evidence with immutable source snapshots, logs and terminal receipts. V1's final14PASS is not relabelled V3, and V2's failed15-method attempt remains failed. The one-off metadata-writer SyntaxErrors also remain explicitly preserved; they are not runtime or production fixes.

## Remaining limits / disposition

The previously disclosed P3 is retained: receipt construction/`guard.telemetry()` can mask an earlier exception. It fails closed but can lose primary diagnostic fidelity; this targeted pass does not claim to fix it or demand a new framework. Root requested disclosure/deferment separately. No hard aggregate resource containment, physical IO bound, complete arbitrary-fault coverage or actual-data correctness follows from SOURCE/synthetic PASS.

Current consumer is22141 bytes, SHA `3f7d1ae6a226ea512965098009cc7f24eee80456ec6a938fb1621ae484c9a03e`; V3 freeze SHA `c36804a8c94679e8d64ab91697104a3fabf710d1c1a1e7a1111eae4edccef052`. Frozen review UTC: 2026-10-17T11:29:28.174420+00:00. All exact inspected snapshot hashes were rechecked immediately before this report. No real seal, DB, Q/C/Y, producer outputs, models, active peer brainstorm or actual-review output was opened. No project/consumer import, SQL, tests, model calls, canonical/Git/network mutation or helper dispatch occurred. Root may combine this scoped correction review with the independent resource review, then decide concrete binding/admission after Q6000 acceptance. **STOP after frozen readback.**
