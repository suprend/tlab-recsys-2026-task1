# Source-import owner v6 — narrow rereview: changes still requested

Exact freeze `source-import-owner-freeze-v6.json`; code SHA `7c8189ed72b88f0d481da8dbeb0ee99c48c4ec7173087635c56d8bc7da69945f`. Snapshot and v1→v6 diff: `tlab-source-import-owner-rereview-v6-snapshot/`. V1–5 and original red evidence were preserved. No real process/source/native work occurred.

The original four findings are repaired in the exercised scope:

- Source-cache probe, duplicate JSON probe and preexisting-failure probe all PASS on Python3.12.14 `-I -B`,3tests/0.012s. Adaptations are explicitly limited to module path, new mandatory `expected_sha` argument and accepted rejection class `(RuntimeError,ValueError)`; observable assertions are unchanged. `tlab-source-import-owner-rereview-v6-probes/authority.log` and `authority-adaptation.diff` preserve this.
- Original final-guard/descendant probe PASS with module path only: unknown usage remains true after successful cleanup. `tlab-source-import-owner-rereview-v6-probes/resource.log`.
- Root's v5 cleanup+marker-write-failure body PASS with only its module path changed. An external persistence redirect protected the hardcoded original v5 result JSON. Primary `TimeoutError('original deadline')` is retained, unknown usage is true, and persistence/cleanup notes remain. `tlab-source-import-owner-rereview-v6-probes/root-cleanup-result.json`, log and `root-body-adaptation.diff`.

Static review confirms `load_kernel` compiles the same bounded bytes whose original SHA it checked, and both production call sites supply the original kernel fingerprint. `object_pairs_hook` rejects duplicate members recursively. Failed owner/kernel/unknown-cleanup markers gate worker consumption and persistent budget checks. CPU minimum21 plus a pre-claim feasibility check replaces the impossible20s accepted endpoint.

**One adjacent P2 failure-accounting defect remains:** `tlab-source-import-owner-v6-draft/scripts/run_source_import.py:253` sets the in-memory unknown flag only if `cleanup()` raises. A failed exited-group observation followed by successful cleanup, or an earlier budget exception followed by leader exit and successful cleanup of surviving descendants, can still record `unknown_owned_process_usage=false`. The injected primary error remains primary; the operation fails rather than falsely completes.

Two bounded fake-handle cases preserve this red: `tlab-source-owner-resource-adjacent-v6-probe.py`, `source-import-owner-v6-adjacent-red.json`, `tlab-source-owner-resource-adjacent-v6-red.log`, review `tlab-source-owner-resource-adjacent-v6-review.md`. The first case injects `OSError` into the initial post-reap group observation; the second covers the guard→cleanup ordering. Author/root received these cases for a separate v7 freeze. This rereview does not accept v6.

Only code/metadata/synthetic fixtures and mocked launch/signal/counter seams were used. No actual archive/hash stream, application child CLI, native SQL, DB/model/labels or fresh-process harness was opened. Actual containment, blocked-native interruption, full source budget/disk sufficiency, external owner-exit acceptance and source handoff remain unproved and unauthorized. Current coordination/verification instructions were read and are now present; earlier missing-file observations remain historical.
