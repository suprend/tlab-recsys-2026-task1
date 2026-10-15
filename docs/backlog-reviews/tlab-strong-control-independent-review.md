# Independent review: historical 019 control consumer

Verdict: **ACCEPT** for the exact three frozen paths in `tlab-strong-control-freeze.json`. This is a read-only consumer of the one reviewed historical control, not a generic acceptance authority or fit permission.

Reviewed the whole consumer, tests and interface. The external acceptance SHA is anchored to the previously independently accepted actual receipt; it is not derived from newly supplied mutable bytes. The consumer reconstructs the exact304-pin closure, checks the successful zero-fit recovery and original failed history, binds winner/checkpoint/native parameters and distinguishes trained iterations from scoring prefix. Bounded receipt reads, local path confinement, guard callbacks and final failure/acceptance checks remain intact. It does not invoke a planner, environment subprocess, model load, label evaluation or fit.

Validation: eight author tests plus four independently added cases passed (12 unique tests,0.906s, ResourceWarning promoted to error). Independent cases covered a late failed marker during streaming, late acceptance mutation, the first streaming-hash interruption boundary and an escaping symlink. The actual historical small-receipt/closure gate reached the first streaming hash, where an intentional sentinel stopped it: no large database, Parquet, model or score bytes were streamed and full control authentication was not claimed. Exact actual frozen source hashes matched after review.

Limitations: future callers must charge complete304-file byte authentication within their own measured budget and supervision. Receipt authentication preserves the prior proof limits and does not recover fit weights from CBM. Public fresh-clone regeneration/bootstrap is still a separate unfinished requirement. No real source oracle, model training, heldout labels or new acceptance was run by this review.

Evidence: `tlab-review-strong-control.py`, `tlab-strong-control-independent-review.log`.
