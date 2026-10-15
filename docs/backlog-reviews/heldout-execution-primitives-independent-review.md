# Heldout execution primitives independent review — changes requested

Root read all exact three v1 files identified by the freeze, all author methods
and the described unfinished outer-owner obligations. Seven additional unique
probes ran without workers/data/models/targets or approvals. All three original
SHA values remained identical after review and were preserved separately. The
initial read-only command guessed repository locations instead of following the
temporary freeze paths and exited1 with file-not-found; the subsequent exact-path
read succeeded. This invocation error performed no mutation or semantic test.

P1: terminal output/authority/marker admission occurs too early. `finish` repins
output, authority and plan before both finalizing and success persistence. A
writer hook that alters one output during finalizing, or one target authority
during success persistence, leaves changed bytes and still returns the verified
pending-lifetime boundary. Independently, a final guard that creates a known
failure marker runs after the last marker check and also returns success. These
are three repros of one incomplete terminal validation boundary. Recheck all
original output/authority/plan refs after persistence, then run the terminal
guard before the final marker comparison; no unchecked callback should follow
the final admission checks. Preserve the original failure and consumed state if
any check fails. This does not promise atomic protection from arbitrary concurrent
filesystem writers; external lifetime acceptance still closes the remaining tail.

P2: metadata `read` accepts exponent-overflow nonfinite JSON. `parse_constant`
rejects literal Infinity/NaN but the valid numeric token1e999 is parsed as float
infinity. A direct `read` probe returns it successfully, contrary to the bounded
nonfinite-JSON rejection requirement. Current `record_gate` canonicalization
happens to reject such a value later, but the reusable reader should fail closed
itself before future outer-owner code consumes metadata. Use a finite parse-float
or recursive finite validation and add this exact regression; retain normal
finite scientific notation support.

Nineteen author methods independently PASS .356s. Seven extra probes: three
PASS (lost target receipt preserves targets-may-have-opened/unknown-active state;
forbidden descendant flag is rejected; boolean approval version is rejected),
four expected-rejection FAIL reproducing the two findings above. Original
harness/logs remain untouched: tlab-heldout-execution-independent.py,
tlab-heldout-execution-independent-v1.log,
tlab-heldout-execution-authors-independent-v1.log. Exact v1 snapshots are under
tlab-heldout-execution-primitives-v1-root-review.

The fixed role order/entry vocabulary, original CPU/wall ceilings, deep-copied
issued slot/context/launch, typed zero-fit/label states, exact output coverage,
exclusive child-consumption association, reaped CPU/RSS checks, missing-receipt
unknown state and explicit unfinished semantic/native/opening gates are otherwise
coherent at this narrow seam. This is not acceptance of an executable owner,
worker capability, actual raw-source formulas, inference or resource sufficiency.
No runtime grant, actual reserved target or model output was introduced.
