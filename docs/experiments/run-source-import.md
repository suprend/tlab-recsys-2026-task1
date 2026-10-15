# One original typed9 source-import owner — review pending

`scripts/run_source_import.py` wraps the narrow import kernel in one dedicated owner and one private worker. No download, historical DB reuse, EDA, Q/Y/C/F, model, fit or source acceptance is included. Initial support is locked Python3.12/DuckDB on Darwinarm64; Windows needs a separate lifecycle adapter. No actual REES46 archive hash/import has run. Independent code review and a tiny fresh-process pass remain required.

## Original reviewed request

Proposed interface, not an actual execution authorization:

```sh
.venv/bin/python -I -B scripts/run_source_import.py \
  --request artifacts/reproduction/import-request.json \
  --expected-request-sha <independently-reviewed-original-request-sha>
```

The SHA acknowledges the exact original request reviewed separately for source, code, destinations and resources. Hashing a caller-written request does not create independent execution approval. The invoking reviewer/supervisor owns this acknowledgment and pinned interpreter/entry point. No `approved=true` template grants work.

Request exact keys: `version`, `scope`, `execution_id`, `archive`, `profile`, `output_directory`, `resources`, `fingerprints`. Version1, scope `externally_reviewed_typed9_source_import`; ID is bounded lowercase. Archive is an existing normalized project-relative regular file with no symlink components. Profile uses the exact frozen kernel vocabulary. Production observed source SHA/bytes/rows cannot be rewritten for another input. This is project-observed identity, not a publisher-signed checksum. Full raw bytes are counted independently of gzip's modulo2³² ISIZE.

Output is exactly `artifacts/source-import-runs/<execution_id>`; exclusive claim is `artifacts/source-import-owner/claims/<execution_id>.json`. Fingerprints contain exact owner/kernel/uv.lock/pyproject SHAs. The original external request fixes ID and output. Same ID cannot repeat after failure even with changed metadata; a new ID/SHA is a distinct request requiring a new explicit external decision.

Resources: integer CPU21..7200s and wall20..14400s. Code maxima do not grant those allowances: the reviewed request sets actual values. Other fields are fixed: parent RSS1GiB/worker7GiB/job8GiB, threads2, engine memory2GB/spill8GiB, parent launch reserve15CPU seconds, final reserve2CPU seconds, cleanup reserve10wall seconds, log1MiB. These are prospective ceilings, not measured full-archive throughput or hard RSS allocation guarantees.

## One-shot paid lifecycle

Only bounded metadata/path and initial allocation-feasibility checks precede the consumed claim. An infeasible original plan is rejected before consumption. Hashes, copies, decompression, parsing, native import, checkpoint/close, output checks, persistence and failures all consume the original budget. Fresh owner/worker reject prior child usage. Total CPU is absolute SELF plus reaped CHILDREN, never worker receipt sums or wall×threads.

New run directories are0700. Wrapper metadata/log files and kernel snapshot/CSV spools are0600; native DB/WAL outputs remain private through their0700 directory. No claim about their individual mode is needed. Existing/partial outputs and plausible old DB metadata are never reused or overwritten. Owner consumes the claim before authenticating code/environment and paid archive work. Kernel reads a bounded source snapshot, checks its original requested SHA and compiles/executes those exact bytes. Cached bytecode is never a kernel input. Unexpected scripts package initialization is rejected. Private child uses the pinned direct script with isolated Python flags, actual original parent PID binding and an exclusive consumed context.

Worker installs/readbacks Unix CPU limits before native work. Persistent sampled-RSS/deadline monitoring terminates it on breach, including blocked native SQL. Parent independently enforces the original absolute deadline/log bound, terminates/kills the isolated group and explicitly reaps. Group-observation errors are recorded as unknown cost. Cleanup refreshes the leader state and records any surviving group before signalling it, including an exit that follows an earlier guard failure. A fresh leader poll cannot close the exit-before-signal race. Before any forced signal to a living group, descendant cost is conservatively marked unverified even if direct reap and group cleanup later succeed. This is not a claim that a descendant definitely existed. Failure before launch and already reaped exits with no remaining group retain known usage. An exited leader’s surviving group is observed before terminal budget errors propagate; its unknown-cost marker survives successful cleanup while the original budget error remains primary. Surviving descendants or unverifiable cleanup mean unknown usage and failure. Sampling/ru_maxrss are not hard memory allocation guarantees.

Only private compressed snapshot, raw decompressed spool, canonical validated CSV, new events DB and aggregate evidence are generated. The canonical CSV has its own mandatory SHA/bytes and is the native reader input. All copies and repeated hashes are paid. Disk planning must count all three input copies, DB/WAL and spill together; the8GiB engine spill setting is not a total disk bound. Original request/claim/context/code/data/output pins remain retained and are rechecked after persistence. Parent compares worker receipt CPU/peak against actual reaped lifetime and uses conservative parent-plus-child peak RSS. Retained spill bytes/files are observed after kernel cleanup; physical spill peak is not measured.

## Evidence limits

Worker records installed+loaded DuckDB against lock, actual Python/OS/architecture, CPU-fence readback, fixed engine settings, zero fit/label creation and original kernel/output refs. Owner records actual child exit0/reap and an original-lifetime resource snapshot before report persistence. Guarded terminal repins still consume the same original budget; their complete cost and exit tail require the external supervisor receipt.

Status: `completed_source_import_pending_external_source_acceptance`; source acceptance is false and full owner exit acceptance is required. A process cannot attest its own unseen exit tail. Separate external review/supervision must inspect final owner exit0/full lifetime and source evidence before handoff. New DB bytes need not equal historical DB. Marketplace completeness, availability delays, downstream features/models are outside this prefix.

Worker failure persistence begins only after authenticating its original owner/context and successfully consuming that context. Rejected unauthenticated or duplicate worker invocations cannot poison an existing owner with a failure marker. Failure preserves original consumed claim, partial work, primary exception and failed report. Cleanup errors become notes. Unknown process/descendant usage is retained in memory before attempting failure-marker persistence, so a disk-write error cannot turn unknown cost into known cost. Failure before process launch and known reaped exits do not invent unknown usage. No automatic retry, fallback output, overwrite or downstream execution occurs.

## Actual bounded evidence

53 author methods PASS with synthetic byte files, mocked counters/process handles and fake child writer. They cover claim-before-hash, changed request/code/output/no retry, symlinks/existing root, exact limits/code closure, duplicate JSON-key rejection, persistent known-failure refusal, absolute CPU/deadline, private parent binding, fixed outputs, actual reaped-cost checks, late source/report mutation, forbidden labels/fits, cleanup/unknown descendants, log bounds, CPU-fence readback and retained spill.

These unit tests launch no process, import no archive and run no native SQL. Separately reviewed four-row fresh-process harness, actual source request and independent source handoff remain required. The broader018 Q/Y/C/F/bootstrap/retraining work remains unfinished.
