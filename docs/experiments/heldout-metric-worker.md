# Fixed independent heldout metric worker

This metric_oracle adapter reads produced targets only after original prediction/target gates, prospective policy and actual producer intent/stage clocks are validated. It uses original proposal identity.source_inputs.source for its read-only raw source. All seven saved score/all-Q/C domains are loaded and checked against accepted source first. It independently reconstructs raw fullY through heldout_metric_audit and checks four estimands, every fixed200 paired-user draw and all produced report values; production evaluator/006 are absent.

It verifies actual_target_intent.opened_at equals producer target-stage UTC, strictly after both prediction/target seals, and producer fullY UTC/monotonic are nondecreasing from admission. Its own target-stage UTC/monotonic are captured before produced positive-target Parquet is opened. A connection proxy separately captures the actual independent raw fullY SQL start; these are separate observed events, not fabricated equal timestamps. Calendar maturity and strict no-adaptation remain the accepted policy.

Produced full-targets.parquet has exactly positive(query_id VARCHAR,product_id BIGINT) keys, unique/nonNULL/within the core's2million safety cap; zero-target queries are restored from accepted all-Q. Every private JSONL row is compared to independent core rankings in period/side/Q order, exact int64 IDs, sorted targets, top20 items and mature=true, with no extra/omitted rows. Private targets/rankings are stripped before evidence; only aggregate counts/periods/clocks remain. labels_loaded=true, native_prediction_count=0.

Synthetic fixtures author period/ranking artifacts using the already accepted independent core, so these are transport/lifecycle tests, not a fresh independent proof of its arithmetic. Tests check healthy all-seven fullY, outside-C synthetic target, private field stripping, wrong target chronology before SQL, sealed score-key drift, freshly resealed wrong raw target and private ranking ID corruption. No actual reservedY is opened.

## Fixed CLI and lifecycle

The only runtime argv grammar is `--context <owner-issued path> --issued-context-sha256 <original raw SHA>`. This is not a runnable permission example: no actual request or allowance is granted here. The entry captures monotonic time before project imports, parses those exact verified raw context bytes, verifies bounded original request/code snapshots and its fixed entry/core before importing project code. The owner must pin this entry, its immutable core, heldout_worker_context/execution/contract and all imported current code in its exact original closure. Existing namespace initializers must be pinned too. Arbitrary user-selected scripts/roles cannot be substituted.

Accepted `begin_role` authenticates the owner-held request/globalclaim/slot/launch/gates/proposal, consumes the child execution once before paid streams, installs its fence/monitor and rejects descendants. The adapter then verifies retained original pins, compares loaded/installed packages against uv.lock, and uses `retain_pins` before each nested manifest/output/model ref is hashed/used. Retained nested pins are included in helper final repins. Actual owner/authority authentication is external; a freshly hashed self-authored package cannot issue approval.

Every watched DuckDB connection is private, thread2, with2GB engine memory and2GB maximum scratch spill; source attachment is READ_ONLY. Daily Parquet inputs are exposed as views from exactly derived owner/day paths, not pandas or whole-period wide tables. The helper's original absoluteCPU/deadline/RSS fence/monitor and outer parent's job accounting remain authoritative; engine memory_limit is not a hardRSS guarantee. This implementation gives no new budget. Scratch, connections and model references close before evidence persistence/finish; primary calculation errors survive secondary cleanup failures. The external parent must still reap/charge the complete process tail and reject unknown/failed receipts.

The wrapper writes only the allocated `evidence.json` exclusively. It has exactly ten fields: version1, scope=`unaccepted_reserved_<fixedrole>_evidence`, run_id, original context ref, execution_consumed ref, decision_lock ref, choice ref, exact original input-ref map, aggregate-only core result and measured environment. Helper finish writes an unaccepted common role receipt and checks source/code/authority/output pins and known failure markers after persistence. Failed/same-context roles cannot refill/retry. No training import, Pool or fit API is used.

## Verification and limitations

Only synthetic fixtures are allowed during review. Tests use3 raw events and public definitions; actual independent cores run against tiny temporary databases/Parquet/NPZ. Issuer/lifecycle unit fixtures are visibly fake and do not grant authority. Native model objects/prediction are replaced by explicit fakes; actual native predictions/fits are zero. Complete outer-owner/process integration and actual resource sufficiency remain separate gates; unit success is not source/model/report acceptance. Original accepted cores/shared helper remain unchanged.

Public synthetic command (after code publication):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -W error::ResourceWarning -m unittest tests.test_heldout_metric_worker -v
```

Draft audit: initial prediction tests exposed a synthetic seal timestamp before the fixture lock; fixture clocks were corrected, original red log retained. Bootstrap probes initially compared unresolved macOS /var paths to /private/var resolved paths; fixture normalization was corrected. An imported unittest fixture class initially caused additional inherited discovery; imports now use module aliases and final distinct counts exclude it. No failed run was relabeled as passed.
