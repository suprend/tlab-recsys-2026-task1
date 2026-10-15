# Independent016 runner review v1 — changes requested

15 October2026. Reviewed exact four-path freeze the recorded four-path freeze below: source `61e977f739c1bc314e7d320cc0d77d71d1e40c85b7af4bb27b2f7c9602ee563f`, tests `25029cb44b2510cff9045a66d68d5e175357fda95b58b6adff653e13c397fcd6`, experiment doc `c418a3436979733fd30e08e57ffc0194887e76a7c945eb04b17cf30a0ed0102f`, observer contract `f5e43ce9ffe884327ce16a1e9c6e4c2cb6e8820882842068e73caaee44e301dd`. All four hashes matched after review. Full747-line source,325-line tests and both contracts read. No edits to project paths, source/label rows, heldout queries, native fits or new model-quality evaluation.

Verdict: **CHANGES REQUESTED**. Two independently reproduced terminal-integrity blockers and one audit-count defect. Root acknowledged all three; the original freeze remains unchanged for this record. Real execution/owner claims stay on HOLD.

## P1 — late failed marker for a previously successful worker is ignored

`_known_late_failure` only checks owner/observer markers. It does not enumerate the successful workers bound by child report references. A new `workers/I1/.../report.failed.json` after the producer output map was sealed is absent from that map; checking existing output hashes does not detect it. Independent owner/filesystem probe writes that marker inside the completed mocked observer and then allows the real parent finalization to proceed. The owner returns `model_outputs_verified_pending_external_acceptance` instead of refusing. This violates the stated rule that known failed results cannot be admitted.

Fix: retain bound successful-worker directories and relevant per-child cleanup log paths; check their known-failure markers after the observer and again at terminal admission. Preserve already known resource-failed arms as paid/ineligible, with their original failure files pinned; blanket rejection of all historical failed arms would contradict the prospective policy. Any newly appearing unpinned failure marker is a blocker.

Evidence [archived source](tlab016-runner-late-worker-probe-source.md) and the archived late-worker output:21 author tests PASS, independent22nd late-worker regression FAIL;22unique total,.513s, ResourceWarning=error. Native owner/filesystem is exercised; workers/observer are explicit fakes. No real model proof is claimed.

## P1 — observer request and terminal dynamic authority are not fully re-pinned

`_observer` retains the initial request SHA in context/evidence but never checks current request.json after the child finishes. Its end checks cover context, parsed evidence, once claim and launch, plus producer references at that point. Later parent input/output maps do not contain dynamic observer request; producer run/report also need their originally issued references retained through the owner terminal boundary, rather than fresh hashes that could bind different bytes.

Independent real `_observer` probe uses a tiny mocked child that writes correctly bound minimum evidence and then appends one byte to request.json. All existing checks pass and `_observer` returns success, although the returned request reference no longer authenticates actual bytes. This is an integrity/lineage failure even though no metric arithmetic was changed.

Fix: return/retain one exact observer authority closure from issued snapshots: request/context/once/launch/evidence and original producer manifest/report refs. Re-pin those exact digests after observer completion and at the final owner success boundary, before accepting pending success. Freshly hashing the changed file is not a replacement for the original issuer reference.

Evidence [archived source](tlab016-runner-request-repin-probe-source.md) and archived output: one unique regression FAIL,.040s. Real frozen `_observer`, native temporary JSON/claims; no OS model child, matrix or fit. The fixture's model evidence is explicitly synthetic and proves this parent binding defect only.

## P2 — a missing child receipt leaves false exact zero fit/look counts

The owner updates counters only after `_invoke_worker` returns. If a launched child entered fit and then exits without a readable bound receipt, parent failure keeps `fit_attempt_count=0` and no unknown-live flag. The analogous metric-look count can also be unknown. A synthetic missing-receipt probe writes a fit-start witness then raises from the invocation seam; failed owner still claims exact0. The global claims prevent replacement attempts and status is failed, so this is not a successful model promotion; it is false audit precision about paid/consumed work.

Fix: persist active slot and unknown-fit/unknown-look state before invocation, clear only after a bound terminal receipt. Maintain known completed lower bounds; use null/explicit unknown for exact totals on unresolved failure. Preserve consumed original slot and canonical actual CPU. This requests no retry, fit or additional budget.

Evidence [archived source](tlab016-runner-unknown-count-probe-source.md) and archived output: one unique regression FAIL,.030s. Native owner/failure persistence, explicitly fake child, no actual native fit.

## Checks that passed and proof limits

Author21 cases passed with warnings treated as errors. Published all4+B selector, inclusive Recall floor/global band/physical-complexity+lexical ties, fixed population/three-column arms, separate trained/prefix fields, raw/bag/fullY semantics, typed data transport, native query weights, no eval_set/early stopping, exact source/control closures, persisted one-owner/four-slot/one-observer claims and shared source-prefix+SELF+reapedCHILDREN accounting match the intended scope in the reviewed code. Normal cooperative resource failures remain paid/ineligible; unknown/integrity/API failure stops. Source/generic helpers and the native process-group supervisor are accepted dependencies, not independently rewritten by this review.

A separate zero-fit API compatibility check loaded only the already accepted019 control CBM, read its native parameters and ran `frozen_model_parameters`/`validate_native`: PASS,300trees/41features/depth6/L2=30/inherited300training+300prefix/2threads. No Q/Y, predictions or new quality look. Probe result [native API probe](tlab016-inherited-native-api-probe.json); process CPU.240504s, API body wall.002007s. This checks valid native parameter types and float32 LR compatibility, not four future models.

Full source formulas and actual output models were not replayed. Native actor/fault tests intentionally mock ML and prior authority where documented. Final code acceptance requires targeted independent re-review of the repaired exact freeze and the independent observer's separate Root review. Actual plan approval, four fits, exhaustive saved-output replay, external full-lifetime seal and whole-decision/heldout lock remain later gates.
