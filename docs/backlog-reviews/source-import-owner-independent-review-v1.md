# Source-import outer owner v1 — independent review: changes requested

Reviewed the exact owner freeze `source-import-owner-freeze-v1.json`, kernel-v2 freeze `tlab-source-import-freeze-v2.json`, and all named owner code/tests/docs. **Do not accept this owner v1 or launch its private CLI yet.** One P1 and three P2 defects below are supported by bounded independent probes; a P3 request-range caveat follows. No actual source execution allowance or acceptance is issued.

## Findings

### [P1] Execute authenticated kernel bytes instead of unpinned cached bytecode

Correctness/authority; original `run_source_import.py:140`, lines140–141, called at277/310.

`spec_from_file_location(...).loader.exec_module(...)` uses the normal source loader and may execute a timestamp/size-valid `scripts/__pycache__/source_import.cpython-312.pyc`. That executable file is outside `CODE` and all retained fingerprints. A successful SHA check of `scripts/source_import.py` therefore does not establish the kernel that `load_kernel` executes.

Confirmed using the actual locked **Python3.12.14 with `-I -B`**: an18-byte source containing `marker = 'PINNED'` passed `repin`; a same-size cache with the source's integer mtime caused `load_kernel(...).marker == 'OTHER!'`. `-B` stopped cache writes but did not disable reading the prepared cache. This is also the parent's pre-worker import path, before the worker fence. No source/native work was needed to demonstrate the code-closure failure. Ordinary timestamp-resolution/same-size stale cache is sufficient in principle; no concurrent writer is required by the reproduction.

Load/compile the exact authenticated source snapshot, or otherwise prevent bytecode cache from supplying executable code. Merely adding `-B` or retaining the source SHA does not fix this. Preserve the original cache probe as a regression.

Evidence: `source-import-owner-v1-bytecode-result.json`; intended-safety assertion in `test_intended_safety_v2.py`; expected-red log `python312-intended-safety-v2-red.log`.

### [P2] Retain unknown descendant cost before a terminal guard can skip its observation

Correctness/resource evidence; original `run_source_import.py:213`, lines213–216; failure-report consequence at237.

After the direct worker exits, the code calls `budget.guard(final=True)` before testing whether the owned group still contains descendants. If this guard raises, the descendant marker is skipped. `finally` can then successfully kill the remaining group and reap the leader. That cleanup does not recover CPU of an orphaned/unreaped descendant; nevertheless `fail()` derives unknown usage only from marker existence and persists `unknown_owned_process_usage=false`.

A fake-handle mechanical probe produced: exited leader, surviving same-group descendant, final deadline failure, successful group cleanup, no descendant marker, and false unknown-usage flag. The attempt correctly **fails**; this is inaccurate failure/resource evidence, not false completion. Observe/persist unknown descendant usage before throwing terminal budget errors, and preserve it through successful cleanup. Preserve the original deadline/exception as primary.

Evidence: `tlab-source-owner-resource-independent-probe.py`; observation log `source-import-owner-v1-resource-probe.txt`; intended safety red `source-import-owner-v1-resource-red.txt` (expected exit1).

### [P2] Reject an already failed attempt before worker consumption or import admission

Requirements/lifecycle; original `run_source_import.py:274`, lines274–278; existing late check at296.

A valid issued request/claim/context and original-parent association with an existing `report.failed.json` still permit the worker to create `worker.consumed.json`, start its budget and reach `kernel.import_archive`. Only the terminal path checks the failed-owner marker. A persisted terminal failure must prevent new paid work, rather than merely prevent its later promotion.

The corrected bounded probe uses a **full synthetic typed9 profile accepted by the actual frozen kernel `validate_profile`**, fake fresh-worker entry time/parent/counters/budget, and an import stub that raises before source access. It observed `(worker_consumed_exists, import_calls) == (True,1)` versus required `(False,0)`. Original exploratory fixtures and initial red logs remain preserved; the v2 probe removes the partial-profile confound. This establishes late rejection/work admission after known failure. It does **not** establish false successful completion, a natural standalone retry after the parent exits, or actual archive reads.

Check original owner/kernel/unknown-cleanup failure markers before consuming the worker context and before paid work, with terminal checks retained. The once-claim must remain consumed; no retry or overwrite follows.

Evidence: `tlab-source-owner-authority-probes/test_intended_safety_v2.py`; target3.12 red log `source-import-owner-v1-authority-red.txt`.

### [P2] Reject duplicate object members in authority and evidence JSON

Requirements/strict metadata; original `run_source_import.py:66`, lines66–67.

`json.loads` discards duplicate members before exact-vocabulary checks. A raw snapshot with its correct expected SHA, `{"version":0,"version":1,"nested":{"cpu_seconds":7200,"cpu_seconds":20}}`, is accepted as version1/CPU20. External approval and downstream readers should not interpret contradictory authority bytes through a last-wins convention when this owner promises strict metadata.

Use a recursively duplicate-rejecting object-pairs decoder for request, claim, context, receipt and evidence; retain bounded same-byte SHA checks. The probe confirms parser acceptance, **not a SHA bypass or source acceptance**. Both top-level and nested duplicates must fail before consumption.

Evidence: raw `tlab-source-owner-authority-probes/duplicate/duplicate.json`; target3.12 expected-red log above.

## Smaller safe-denial caveat

**P3**, original lines102–103 and119–120: the documented/validated CPU20s endpoint cannot launch a worker in any process with positive SELF CPU. `int(20−SELF−15−2)` is then below3, so allocation fails after the once-claim has been consumed. The fake0.1s counter reproduces `No remaining bounded worker CPU allowance`. Align the accepted lower bound with the allocation rule or explicitly reject infeasible plans before consuming the attempt. This is a usability/safe-denial issue, not an overrun or acceptance failure.

## Boundaries that were checked without a supported additional defect

- Original request SHA is required before claim creation; output/claim namespaces and execution ID are fixed, symlink components refused, and same-ID attempts remain consumed. A fresh self-hash does not provide external authorization; the docs correctly assign that decision to the invoking reviewer. The direct entry uses isolated flags and rejects `scripts/__init__.py`; the pyc finding remains a separate executable-closure gap.
- Profile validation delegates to the pinned kernel, with immutable observed-production identity and separate synthetic scope. The kernel-v2 `validated_csv` field and `validated.csv` physical output are handled in the worker and exact parent output closure. No stale v1 evidence-shape omission was found.
- Owner CPU is SELF plus actual reaped CHILDREN. Receipt CPU is bounded by actual reaped CPU rather than added a second time. Worker allocation subtracts initial owner cost and reserves; absolute RLIMIT_CPU is installed/read back. No supported double-counting defect was found.
- Worker peak RSS is checked during work, and success compares actual reaped worker peak plus parent peak conservatively with job cap. Parent polling independently checks wall/log bounds. Static code and fake checks do not prove live interruption of blocked native SQL, signal delivery, actual group containment or Darwin reaping.
- Code/request/claim/context/consumed/receipt/reaped/evidence/output/log pins are retained and rechecked after persistence. Failed operations preserve primary exceptions and partials; completion explicitly remains pending external source acceptance and unseen owner-exit acceptance. The failure-accounting ordering defect above must still be repaired.
- Canonical CSV incurs a new write, native read and repeated hash passes. These callbacks use the original budget; documentation correctly counts compressed snapshot/raw CSV/canonical CSV/DB/WAL/spill separately.8GiB engine spill is not a total disk limit. No full-source disk peak, throughput or total job sufficiency was measured.

## Scope, executed checks and preserved failures

Named-file review, no Git baseline; these findings apply to owner v1, not an established regression. Snapshot `source-import-owner-review-v1-snapshot.json` captures exact owner3/kernel3/environment2 files and original line mapping. Owner code SHA is `9b2859db8d3679aa3a030be7c6c1708ba53e6bee376d93d15c79949774a86a77`; kernel v2 code SHA is `7d7ed34b336294bd18d822b9798a7b644f45dc72f8c1f6edeb6d518b55284236`. All8 original inputs still matched at final check; `source-import-owner-review-v1-freshness.json` preserves the result.

One independent reviewer covered authority/correctness, another resource/lifecycle, and I inspected their concrete triggers against the complete frozen code and callers. Their notes are `tlab-source-owner-authority-independent-note.md` and `tlab-source-owner-resource-independent-note.md`.

Executed evidence:

-31 author fake/metadata methods passed on system Python,0.111s; then the same31 passed on target Python3.12.14 with `-I -B`,0.119s. Target log `source-import-owner-v1-author-tests.txt`. These checks launch no application child and run no native SQL.
- Three intended-safety assertions are **red** against v1 on Python3.12.14,0.012s: cached code, preexisting failure admission and duplicate metadata. The original partial-profile/clock exploratory results are preserved; only the full-profile v2 failure is used for the marker finding.
- One fake-resource intended-safety assertion is **red**: unknown descendant usage becomes falsely known after final guard failure/cleanup. It proves the ordering with mocked OS handles, not a real descendant experiment.
- Frozen-file metadata hashes and final freshness check passed. Only bounded code/metadata/synthetic bytes were hashed; no actual archive stream was read or hashed.

No actual REES46 archive/import/decompression/SQL, DB/model/Q/Y/C/F access, native fit, owner/private-worker CLI launch, fresh-process harness or shared/Git edit occurred. The advertised code-review skill links `docs/agents/coordination.md` and `docs/agents/verification.md` were absent at their referenced paths; target project root AGENTS/CONTEXT were also absent. Supplied user instructions, exact parent task and frozen experiment docs provided the applicable requirements. This missing guidance did not prevent the bounded review.

**Next admissible step:** repair the findings in a new frozen draft, rerun these unchanged independent safety assertions plus focused author regressions, and obtain a narrow rereview. Only then review a bounded fresh-process harness separately. Real archive/hash/import/native execution still requires its separately reviewed original request, resource/disk plan, full exit accounting and source handoff; no such grant follows here.
