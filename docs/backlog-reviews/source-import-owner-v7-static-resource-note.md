# Independent narrow v7 resource-accounting rereview

No new actionable defect found in the requested v6-to-v7 repair under the inspected failure states. This is a limited static pass, not full lifecycle or execution acceptance.

Scope: `tlab-source-import-owner-rereview-v7-snapshot`, freeze `source-import-owner-freeze-v7.json`, including the v6-to-v7 diff, modified supervisor, relevant failure-report code, regression tests and resource documentation. Original owner path is `tlab-source-import-owner-v7-draft/scripts/run_source_import.py`; SHA256 `5747b24547506284aa259acb4581c41c9d9905ffd5b44f5e0a72ff70a36a5c61`, 32979 bytes. All three frozen files still match manifest sizes/hashes. No mutable draft was changed or approved.

## Static trace of requested repair

- Lines 210–221 centralize uncertainty in `unknown_usage` before attempting marker persistence. The original error receives the in-memory flag when available, so a failed marker write cannot erase uncertainty.
- Lines 222–228 mark non-ProcessLookup group-observation errors as unknown before propagating them. Successful later cleanup cannot clear the ledger.
- Lines 234–235 call `process.poll()` before the cleanup group signal. This addresses the original cached-returncode fixture where the leader's OS exit precedes cleanup while Python's cached returncode remains `None`: a refreshed exited leader with a living group is marked unknown before termination.
- Lines 256–261 observe the exited leader's group before the terminal guard, retain the ledger, and pass an already-captured terminal error to marker persistence. Marker errors become notes when a deadline error already exists, retaining its priority.
- Lines 265–279 propagate ledger uncertainty back to the primary error even when cleanup returns successfully; cleanup errors also retain unknown usage. This closes the reported v6 seams for observation error and leader exit before the cleanup poll.
- Failure before `Popen` returns leaves `process=None`; cleanup returns without inventing unknown usage. A known reaped nonzero exit whose group is gone does not set the ledger. The corresponding tests at lines 268–276 assert these distinctions.
- `fail()` line 290 accepts either the in-memory error flag or an existing failure marker. The modified error paths therefore no longer depend solely on marker persistence.

I inspected the new tests for group-observation error and refreshed leader state (lines 278–303). The parent coordinator owns execution of the 51 author methods and original/root/adjacent/cached semantic probes; those checks were not duplicated here, and their results are not independently claimed by this note.

## Limits

The cleanup poll, group observation and signal are separate operations. This narrow static result is not a general proof against an unobserved forbidden descendant or a leader exit that races after cleanup's poll and before signalling. No new finding is asserted from that unexecuted boundary: the current kernel has no subprocess creation path, and actual process-tree behavior remains outside the fake/static evidence.

Actual Darwin process-group termination, reaping, CPU-limit delivery, sampled-RSS enforcement and interruption of blocked native SQL still require separately authorized fresh-process evidence. The owner's pending status and required external full-lifetime/source acceptance remain necessary.

Only frozen code/test/doc reads and snapshot integrity hashing were performed. No owner/worker CLI, actual child, signal, archive/source hash stream, SQL, native operation, data/model work or further delegation occurred. Original v6 red scripts/logs and the cached-state precision witness remain unchanged.
