# Source-import owner v8 — narrow repair rereview accepted

**The reported code defects are repaired within this read-only, pure/mocked scope. No remaining actionable defect was found in the reviewed repair paths.** This accepts the v8 code repair gate only; it does not authorize an application child, fresh-process harness, actual archive/hash/import/native SQL, source acceptance or downstream work.

Exact freeze: `source-import-owner-freeze-v8.json`; original draft root `tlab-source-import-owner-v8-draft`. Owner SHA `5df50bb2577b4515c5d80a5eaf4a6f2bf18abe344039d1cd22a51a872e1c7653`, tests SHA `c76118630198f3d818e1e7e3588d1e39537ca91a14080c309829cd504acbbfdb`, docs SHA `6b3c0c87bb90f7cc06cea8d6dc25afe751083914b6f3fba8aad889fa2fb54a97`. All three original files matched the freeze at capture and final validation. Snapshot `tlab-source-import-owner-rereview-v8-snapshot`; kernel v2 remains the previously frozen context.

## Repair conclusions

- **Pinned executable bytes:** `load_kernel(check,expected_sha=...)` reads a bounded source snapshot, verifies its original SHA and compiles those exact bytes with `dont_inherit=True`; normal SourceFileLoader/cache execution is gone. Both production call sites supply the original kernel fingerprint. The original conflicting-pyc test passes on Python3.12.14 `-I -B`. Additional unchanged supplemental cases confirm that source mutation after the authenticated snapshot does not change the executed bytes, and a snapshot guard failure prevents execution.
- **Strict metadata:** recursive duplicate-object-member rejection operates before vocabulary checks and consumption. The original SHA-matched top-level/nested duplicate probe passes; this repair does not replace raw-byte authority with a fresh self-hash.
- **Known failure admission:** original owner/kernel/cleanup/descendant failure markers gate worker consumption and persistent budget callbacks. The original full-valid-profile probe now observes no `worker.consumed.json` and zero import calls. The once-claim is not refilled or overwritten. Unauthenticated/duplicate worker requests no longer write a failure marker into someone else's original owner attempt.
- **Unknown usage and primary errors:** a central in-memory ledger records unknown cost before marker persistence. Group-observation errors, terminal guard failure, cleanup failure and marker-write failure retain unknown usage even after later successful cleanup. Original deadline/OSError stays primary, with persistence/cleanup diagnostics as notes. Reaped vanished groups and prelaunch failures remain known; forced termination of a still-living owned group is conservatively classified as **unverified** descendant cost, without asserting an observed descendant.
- **Poll/signal race:** cleanup refreshes leader state before group signals, but poll and signal cannot be atomic. The v8 conservative policy records unknown cost before every forced living-group signal. The preserved v7 post-poll/pre-signal race now passes and cannot be reclassified known merely because the leader was subsequently reaped and the group disappeared.
- **CPU20 safe denial:** public validation now rejects20 and starts at21; allocation feasibility is checked before the original claim is consumed. The old resource arithmetic fixture still correctly rejects an internally constructed20s budget; it does not imply that20 remains an accepted request.

## Original evidence and explicit adaptations

Original v1 findings/red bodies and v5/v6/v7 failures remain preserved. V5 was not accepted after the cleanup-marker-write failure; v6 was not accepted after adjacent observation/leader-exit failures; v7 was not accepted after the narrower poll→signal witness. Green results for earlier cases did not conceal later failures.

The three authority assertions were adapted only for module location, the new mandatory `expected_sha` API argument and rejection-class tuple `(RuntimeError,ValueError)`. Their desired outcomes remain pinned source code, rejected duplicate metadata, and `(consumed,import_calls)==(False,0)`. Original resource and root cleanup bodies changed only module location. An external result-persistence redirect prevented their hardcoded v5/v6 output names from overwriting original red JSON.

The extra stale-Popen fixture originally asserted the old cache value specifically at signal time. Its **original file was preserved**. A separate semantic copy permits `(None,0)` there, while retaining `returncode is None` at the original guard exception and all unknown-cost/group-cleanup assertions. The same semantic body remains red on v6 and is green on v8; this permits a valid cache refresh rather than weakening the safety outcome. The supplemental post-poll race body required only a different owner-path argument.

Replay scripts, diffs and logs are in `tlab-source-import-owner-rereview-v8-probes/`; the v6 differential red is `tlab-source-import-owner-rereview-v6-probes/cached-semantic-v6-red.log`. Root's original v5 result and the original v6 stale-cache result still contain `unknown_owned_process_usage=false`, independently checked after the successful v8 replay.

## Executed verification

All runs used target Python3.12.14 with `-I -B`, temporary synthetic files and mocked process/signal/resource seams:

| Check | Result | Evidence under v8 probe directory |
|---|---|---|
|53 author methods | PASS,0.212s | `author53.log` |
|3 original authority safety assertions | PASS,0.035s | `authority.log` |
|Original terminal-guard/descendant safety assertion | PASS | `resource.log` |
|Root cleanup failure + failed marker persistence | PASS; original deadline retained, unknown=true | `root-cleanup.log`, `root-cleanup-result.json` |
|2 adjacent group-observation/leader-exit assertions | PASS; primary errors retained, unknown=true | `adjacent.log`, `adjacent-result.json` |
|Stale-cache semantic differential | v6 RED → v8 PASS; cache None at original guard, refreshed before signal | `cached-semantic.log`, `cached-semantic-v7-result.json` |
|Post-cleanup-poll/pre-signal race | PASS,1method/0.005s | `cleanup-gap.log`, `cleanup-gap-result.json` |
|2 authenticated-source-snapshot supplemental cases | PASS,0.002s | `source-snapshot2.log` |
|Final freeze/result/original-red retention validation | PASS | `final-validation.json` |

Thus nine targeted safety cases plus two source-snapshot cases passed alongside the53 author methods. A second independent resource reviewer inspected the v7/v8 delta read-only and found no actionable defect in this narrow repair scope; my check verified actual files, returned results, original assertions and final pins.

Two reviewer harness diagnostics are preserved in `reviewer-wrapper-diagnostics.txt`: a zsh readonly variable typo after an already-completed expected-red v6 fixture, and an initial final-inventory path mismatch for a successful supplemental result. The real result was located, checked against the v8 owner path and copied byte-exact; the external redirect was corrected, and final validation passed. Neither diagnostic was represented as a successful safety test, and no safety assertion was changed to hide a failure. Author's initial v7 note-phrase test failure likewise remains at the path recorded in its freeze.

## Limits and next gate

No actual archive read/hash/import/decompression, DB/SQL/model/Q/Y/C/F, native fit, application owner/private-worker CLI child, real process group, fresh-process harness, shared-file/Git edit or new execution grant occurred. Code/metadata/tiny synthetic bytes alone were read or hashed. This review does not demonstrate actual blocked-native interruption, Darwin signal/reap behavior, complete runtime containment, full-source CPU/RSS/disk sufficiency, crash durability, unseen owner-exit cost or source acceptance.

The next step is separate review of a bounded fresh-process harness and its exact request. Real source execution still requires its own original authority/resource/disk plan and external full-lifetime/source handoff. Frozen B/W and current heldout policy remain unchanged.
