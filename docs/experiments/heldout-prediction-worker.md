# Fixed independent heldout prediction worker

This prediction_oracle adapter uses heldout_prediction_audit's own explicit Q/C/B45/chosen3 numeric projection and native replay. It does not call inference_data, prediction producer or006 metrics. It binds accepted source and the unaccepted seven-day prediction manifest/receipt, exact0/3 model order and model refs, then loads each day separately. W=B reuses one saved B artifact and one actual replay call per nonempty day; otherwise exactly two. The immutable core checks complete300/300 native state/parameters, thread2/raw prefix and all keys/scores/rank ties. Models are loaded through CatBoostClassifier.load_model only, never fit. Its private_replayed_scores field is removed before aggregate evidence; labels_loaded=false.

NPZ transport is independently checked BEFORE np.load: exactly seven unique .npy members, standard1.0/2.0 bounded4096-byte header, scalar little-endian dtype and exact1D originalQ/C shape, fortran_order=false, header+payload byte equality. Arrays are query_ids U64, user_ids/anchors int64, calendar_maturity bool, group int32, items int64 and scores float64. Anchors use exact integer microseconds since the UTC epoch. Object/pickle/structured/huge/truncated/duplicate members and nonfinite scores fail closed. Metadata/model names are taken from the bound descriptor, not NPZ fields.

Synthetic tests cover all-seven W=B and chosenI1 with fake-native replay, empty dates, IDs beyond2^53, exact microsecond anchors/thread/prefix, huge declared header shape and truncated payload before allocation, wrong dtypes/object/nonfinite/duplicate ZIP, native tree drift, changed source destinations and late model bytes after fake prediction. No real CBM or native prediction is performed.

## Fixed CLI and lifecycle

The only runtime argv grammar is `--context <owner-issued path> --issued-context-sha256 <original raw SHA>`. This is not a runnable permission example: no actual request or allowance is granted here. The entry captures monotonic time before project imports, parses those exact verified raw context bytes, verifies bounded original request/code snapshots and its fixed entry/core before importing project code. The owner must pin this entry, its immutable core, heldout_worker_context/execution/contract and all imported current code in its exact original closure. Existing namespace initializers must be pinned too. Arbitrary user-selected scripts/roles cannot be substituted.

Accepted `begin_role` authenticates the owner-held request/globalclaim/slot/launch/gates/proposal, consumes the child execution once before paid streams, installs its fence/monitor and rejects descendants. The adapter then verifies retained original pins, compares loaded/installed packages against uv.lock, and uses `retain_pins` before each nested manifest/output/model ref is hashed/used. Retained nested pins are included in helper final repins. Actual owner/authority authentication is external; a freshly hashed self-authored package cannot issue approval.

Every watched DuckDB connection is private, thread2, with2GB engine memory and2GB maximum scratch spill; source attachment is READ_ONLY. Daily Parquet inputs are exposed as views from exactly derived owner/day paths, not pandas or whole-period wide tables. The helper's original absoluteCPU/deadline/RSS fence/monitor and outer parent's job accounting remain authoritative; engine memory_limit is not a hardRSS guarantee. This implementation gives no new budget. Scratch, connections and model references close before evidence persistence/finish; primary calculation errors survive secondary cleanup failures. The external parent must still reap/charge the complete process tail and reject unknown/failed receipts.

The wrapper writes only the allocated `evidence.json` exclusively. It has exactly ten fields: version1, scope=`unaccepted_reserved_<fixedrole>_evidence`, run_id, original context ref, execution_consumed ref, decision_lock ref, choice ref, exact original input-ref map, aggregate-only core result and measured environment. Helper finish writes an unaccepted common role receipt and checks source/code/authority/output pins and known failure markers after persistence. Failed/same-context roles cannot refill/retry. No training import, Pool or fit API is used.

## Verification and limitations

Only synthetic fixtures are allowed during review. Tests use3 raw events and public definitions; actual independent cores run against tiny temporary databases/Parquet/NPZ. Issuer/lifecycle unit fixtures are visibly fake and do not grant authority. Native model objects/prediction are replaced by explicit fakes; actual native predictions/fits are zero. Complete outer-owner/process integration and actual resource sufficiency remain separate gates; unit success is not source/model/report acceptance. Original accepted cores/shared helper remain unchanged.

Public synthetic command (after code publication):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -W error::ResourceWarning -m unittest tests.test_heldout_prediction_worker -v
```

Draft audit: initial prediction tests exposed a synthetic seal timestamp before the fixture lock; fixture clocks were corrected, original red log retained. Bootstrap probes initially compared unresolved macOS /var paths to /private/var resolved paths; fixture normalization was corrected. An imported unittest fixture class initially caused additional inherited discovery; imports now use module aliases and final distinct counts exclude it. No failed run was relabeled as passed.
