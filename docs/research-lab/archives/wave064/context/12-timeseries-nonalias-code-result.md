# Timeseries compiler canary: accepted synthetic CODE PASS

The [tested original](evidence/timeseries-nonalias-code/tested-original.py) passed
one unittest without skips on 16 October2026. The
[actual-output review](evidence/timeseries-nonalias-code/actual-output-review.md)
found no discrepancy; [Root accepted and closed the episode](evidence/timeseries-nonalias-code/root-acceptance.json).
The child returned0 and was known reaped; the
[outer terminal witness](evidence/timeseries-nonalias-code/root-terminal-witness.json)
records closed exit0. The once namespace is consumed: this packet does not rerun it.

The successful path covers two isolated four-view histories at Oct8 UTC midnight,
with identical user/item/category/query and supplied complete source coverage and
mature-query metadata. Both histories match independent literal gold: recent-only
retrieval, all41 ordered float32 coordinates/types/NULL masks (**39 actual compiler
coordinates plus2 explicitly copied label-free SQL projections**) and all eight
typed bundles. The2 histories/18 compiler calls are fixed source-defined counts,
not a separate SQL-call instrumentation trace. Within this canary there were
0 ML fits/predictions and no model, real-data or Y input.

The [raw result](evidence/timeseries-nonalias-code/result.json) and
[unittest log](evidence/timeseries-nonalias-code/stderr.txt) report:

| Observation | Recorded scope/value |
|---|---|
| unittest |1 test,0 skips,0.859s, OK|
| child Popen→known exit wall |1.1756635s|
| reaped-child CPU |1.005867s|
| supervisor SELF CPU |0.075278s snapshot|
| child peak RSS |147816448 bytes, recorded Darwin units|

These scopes are not additive whole-lifetime/whole-tree accounting or a hard RSS
guarantee. DuckDB threads2/memory64MB/spill0B are engine settings. Timeout/abort
cleanup was not exercised. The consumed native50CPU/65wall allowance remains
closed and was not reused; scientific CPU remainder remains UNKNOWN.

Coverage and maturity are fixture premises. Interior midpoints do not test exact-T,
lower boundaries, duplicate peers or cohort sampling. No full model loader,
ordinary CLI, binner, tsfresh bank, multi-anchor or predictive-utility claim follows.
Analytical bank differences remain separate from this executed compiler check.
No production feature, dependency, model or mandatory gate changed.

The [canonical test candidate](../../tests/test_timeseries_nonalias_canary.py)
differs from the executed original only by deleting six bytes `UNRUN ` at the
start of its module docstring. Its executable AST is identical; that cosmetic
variant was not rerun. The [preparation contract](evidence/timeseries-nonalias-code/preparation-contract.md)
and [static review](evidence/timeseries-nonalias-code/static-review.md) retain
their original pre-execution UNRUN wording. [Pins](evidence/timeseries-nonalias-code/actual-output-pins.json)
and the [archive map](evidence/timeseries-nonalias-code/archive-map.json) bind
exact originals and intentionally omitted external metadata. This additive
12-file integration proposal remains outside the current main433 Git slice;
installation/publication is separate and creates no new runtime authority.
