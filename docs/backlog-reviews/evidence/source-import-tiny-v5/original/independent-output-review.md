# Independent output review — one actual source-import tiny V5 launch

No supported output defect was found in the frozen artifacts of the single actual tiny launch. The artifacts support this bounded synthetic/shared-runtime result; they do not issue real-source acceptance.

## Observed result

Root supplied explicit terminal evidence for exec session30552, chunk05c64d, exit0. Its original external receipt SHA is947b60b51389febc21e3877a15823cf4d9d9e7c047f31d83779baf4fc1fd31e9. The receipt, raw logs and complete fixed-root output closure match their recorded pins.

- Exactly3 owner attempts are recorded in order: positive0, duplicate1, wrong-SHA1; all are reaped with known usage. Exactly2 worker contexts and2 claims exist. Only4 synthetic rows were imported positively;8 is the declared bound across the two source attempts, and the wrong-SHA attempt stops before decompression/native DB admission. Real source rows0, fit attempts0, labelsfalse, source acceptancefalse.
- The positive worker's six mandatory outputs and all18 owner-report fingerprints match current physical bytes. The217-byte original fixture is identical to both private compressed snapshots. The positive raw470-byte and canonical554-byte CSV spools independently contain the exact intended four nine-field rows, including duplicate multiplicity2, integer2**60+1, Decimal cents/zero/negative values and quoted/comma/space metadata. Persisted native schema and aggregate evidence agree. The actual pinned V5 driver's post-reap native literal proof reports exact typed9. I did not re-query the DB; its536576-byte physical file SHAee45ce5ed1b66824f69f2dbabb0421bcb16a9a739f1da5c3d22f8e3fbbb67a60 matches every retained reference.
- Duplicate log ends with `ValueError: Existing import output cannot be reused`; no third claim/context was admitted. Wrong-SHA worker log ends with `ValueError: Original compressed SHA/size differs`, its kernel failed marker isValueError, the complete compressed snapshot matches the original fixture, and no raw CSV/canonical CSV/DB/evidence or completed worker/owner receipt exists there. The owner's top-level failed marker is retained and unaccepted; the later owner guard reports the existing worker failure, with a FileExistsError persistence note. Its early failure snapshot is not treated as full-owner CPU evidence; the driver's actual reap delta supplies that boundary.
- The shared canonical V6 supervisor records normal driver exit0, no errors/signals/terminal survivors and no unknown active work. Its generic `worker_ledger_verified=false` is correctly separate from the harness's caller-owned exact-three-case ledger verification. The six observed processes are driver+3owners+2workers. These are recorded observations, not an arbitrary-descendant containment guarantee.

## Resource reconciliation

Original limits remain200CPU/240wall for the harness,70seconds including cleanup for each owner wait, and original60CPU/60wall source-owner requests with fixed2threads/2GBengine/8GiBspill. All request, context, claim and report associations/pins agree.

Positive worker receipt CPU0.250275≤actual reaped worker0.273227≤owner observation0.346846≤full owner exit0.356081. The three full-owner exit deltas sum0.535666; driver observation0.631188≤outer actual inclusive driver reap0.641841≤supervisor observed0.702585. External `/usr/bin/time -l` raw log records1.10wall/0.55user/0.15system; allowing conservative rounding gives CPU upper0.72, consistent with the internal totals. Supervisor's declared-tail conservative upper2.70262 remains under200.

Sampled aggregate job peak196149248bytes is below8GiB. External maximum RSS107954176bytes is a single-process maximum and is explicitly not an aggregate peak. Parent/worker recorded peaks and all log sizes are within original limits. This does not establish hard aggregate memory or full-source capacity. External root receipt supplies the actual harness exit tail, which the in-process supervisor accurately leaves unmeasured.

## Scope and freshness

Read-only scope: `/tmp/tlab source import integration 20261015`, original root operation and external receipt, candidate freeze/code/plan/canonical-helper bytes, and original stdout/stderr-time logs. Frozen48regular files total1062427bytes plus the expected trusted `.venv` symlink are captured in `/tmp/tlab-source-import-tiny-v5-independent-output-review-inputs/`. Recursive original-byte reference checks, all18 positive fingerprints, six kernel output pins,10 external artifact pins, exact limits/negative reasons and resource comparisons passed205 bounded checks. No test/application rerun or native/database backend was invoked.

Terminal hash comparison and fixed-root file inventory match capture; the `.venv` target is unchanged. Root clarified that external receipt `execution_plan_sha256` identifies `/tmp/tlab-root-source-import-tiny-v5-operation.json` (SHAc1205487f1552a2f746063dcb20ebbaf2dd5bfc19108c09aa532b87f46a030bf). The historical candidate Markdown plan is separately pinned by the candidate freeze; there is no mismatched plan identity.

Checker/result: `/tmp/tlab-source-import-tiny-v5-independent-output-check.py` and `...-output-check-results.json`. Final ledger: `/tmp/tlab-source-import-tiny-v5-independent-output-review-results.json`.

This review read/hash-checked existing tiny files and parsed existing synthetic CSV spools only. No SQL, process observer, Popen, fit, real dataset/archive/model read, external call, fixed-root edit or project edit occurred. The explicit exec terminal event is trusted root-supplied session context, corroborated by its pinned external receipt; the output reviewer did not rerun that event. Root retains final handoff decisions. Real-source import, disk capacity, model/generalization and broader native lifecycle acceptance remain unproven here.
