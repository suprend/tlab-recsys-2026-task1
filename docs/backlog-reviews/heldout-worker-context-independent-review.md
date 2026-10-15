# Shared reserved worker context/lifecycle review — changes requested

Root read the entire frozen helper, lifecycle delta, all21new/25existing author
methods and both complete documents. All six freezeSHA/whitespace values match
after review and are preserved separately. Earlier reads of the unfinished
helper are not counted as review of frozen code; frozen terminal/environment
changes were reread. No actual data/model/target operation was performed.

P1: the newly persisted receipt is absent from terminal original-byte checks.
`finish` ignores the original ref returned by `exclusive(receipt)`. It repins
inputs and allocated outputs after persistence, but the receipt is neither in
those maps nor independently checked. An exclusive-writer hook writes the
original receipt, then changes process_cpu_seconds from1.0 to0.5; finish still
returns a successful in-memory original receipt while the disk body differs.
Retain exclusive's original returned SHA and guard-verify those same receipt
bytes after persistence/final streams before success. Avoid self-hashing inside
the receipt body. Preserve failed marker and original exception on rejection.
This is a receipt association defect, not an atomic filesystem guarantee.

Adapter integration obligation (independently identified by C11): nested new-day
Parquet/NPZ/fullY refs introduced after initial plan are verified by explicit
mapping, but optional verify_pins(mapping) does not retain them for terminal
repins. Add an explicit retain_pins(mapping) seam that validates/normalizes and
rejects conflicts, copies the original refs BEFORE paid hashing, then includes
them in later original-pin verification. Terminal/failed roles must reject this
operation. This is a narrowly agreed lifecycle addition before adapters; no new
formula, model, authority scope or budget is implied. Root did not claim an
additional independent repro of C11's finding.

Forty-six scoped author methods PASS .998s, including one tiny isolated Unix
CPU-fence setup/readback child. Four unique independent methods: three PASS
(caller outputs/evidence mutation cannot replace retained snapshots; failed role
cannot reset; changed consumed-record bytes reject), one expected-rejection FAIL
reproducing receipt association. Original harness/logs are untouched:
tlab-worker-context-independent.py/v1.log and root-authors-v1.log. Six exact
snapshots live under tlab-worker-context-v1-independent.

Fixed role/context/slot/launch/proposal identity, immutable gate subset, original
claim/start/deadline, type/count guards, exclusive admission before paid streams,
lock-byte environment snapshot, persistent expiry/SQL interrupt, CPU-fence
readback and original-failure preservation are otherwise coherent at this seam.
Lifecycle v4 changes are narrowly prospective authorities + target_policy naming;
existing finalization/resource logic remains unchanged. Successful counters
precede child persistence/repin/interpreter tail, correctly requiring actual
parent reaping and full external acceptance. The fence probe does not prove
hardcap precision, native throughput, memory safety or actual resource sufficiency.

No outer-owner/adapter/semantic-output acceptance, original439large hash stream,
CBM load, native inference, fit, reserved Q/C/Y or execution approval occurs in
this review. The actual reporting request remains closed until all new seams
and one complete tiny process lifecycle are independently reviewed.
