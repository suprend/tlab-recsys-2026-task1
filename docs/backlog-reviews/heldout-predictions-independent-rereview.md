# Heldout prediction core v3 — targeted independent rereview

**CODE ACCEPT, structural/core scope only.** No actual heldout/source/model output,
execution owner/budget/claim, native replay, prediction seal or Y capability is
accepted. Exact final three-path freeze:

- scripts/heldout_predictions.py
  e1b06b2aac68c59379d15298c39101ec02b6a176c26b13d4671f8e445de2851b
- tests/test_heldout_predictions.py
  4b3579c32a453cb6cf67260222ff3374836f5fe3e85df69b9b261da3232b2bd8
- docs/experiments/heldout-predictions.md
  82aefcedc06e48c7f6b7db3c2d65e112a2a53c505a0ca86d654ff7f47aec9845

All three hashes verified before/after. Source/tests/doc read; no repo mutation,
Git, actual data/Q/Y/source DB/CBM/Pool/native predict/fit. Original initial review
`<temporary>/tlab-heldout-predictions-independent-review.md`, v2 fault source/log/results
remain unchanged. The v1 embedding issue is already repaired in reviewed v2/v3.

## Original P1 closed

v3 retains exact Q triples, calendar, group/items and preparation before native
invocation, plus a guarded bounded-chunk x byte witness. Post-call model check and
full structural data validation precede exact identity/preparation comparison
and the second x witness. FrozenScores uses the retained identity snapshot.
Thus returned score keys cannot silently become the mutated live data identity.

Unchanged original four fault cases all reject: valid sorted int64 substitution
(which structural validation alone misses), duplicate item, out-of-domain group,
and appended synthetic target tuple. Controls still preserve output-owned copies,
strict user types/narrow LR tolerance and numeric embedding rejection. New finite
x mutation, preparation change and calendar change also reject before success.
No assertion requires a claim actual CatBoost mutates inputs; these are injected
callback-boundary invariants, and the witnesses do not recover native internals
or actual historical training weights.

## Validation

-20 author unique methods PASS .036s, ResourceWarning-as-error.
-6 original independent methods replayed with **identical test bodies**. New
  harness copy changes only freeze-v2 path to freeze-v3; it is imported rather
  than executing its original main, preserving the original results file.
-4 fresh independent methods: finite float32 mutation, preparation mutation,
  calendar mutation, and literal SHA of strided2×2 float32 bytes/empty matrix/
  guard cancellation. No second dense matrix or large test arrays.
-Combined independent10 methods PASS .015s,0failures/0errors. Total30 unique
  methods; subcases are not inflated into extra test counts.

Sources/results:
`<temporary>/tlab-heldout-predictions-own-probes-v3-original-replay.py`,
`<temporary>/tlab-heldout-predictions-v3-rereview-probes.py`,
`<temporary>/tlab-heldout-predictions-own-probes-v3.log`,
`<temporary>/tlab-heldout-predictions-own-probe-results-v3.json`.
Expected original v2 red remains
`<temporary>/tlab-heldout-predictions-own-probes.log`.

AST comparison preserves FrozenScores, native comparison/model validation,
source-day validation and existing structural validation definitions. Added
matrix witness processes slices of at most65536rows, guarded before each chunk
and at completion; contiguous inputs need no matrix duplicate, strided inputs
make only the current bounded contiguous chunk. Empty x hashes empty bytes.
score_day changes are the disclosed snapshot/postcheck/output association repair;
forecast policy/caller loaders/raw300prefix/thread2/W=B reuse are unchanged.

## Continuing accepted limits

The caller still authenticates exact lock/choice/source/model/code bytes and
supplies the measured supervisor, native objects and reviewed loader. This pure
core does not prove callback-source association or source formulas independently,
open models itself, own file cleanup/fsync/exit tail, interrupt native calls,
issue resource allowance or create a target relation. Its returned containers
remain caller-owned before artifact sealing; copied snapshots are not an
external immutable seal. Complete7-date source proof, separately verified native
output replay, successful full lifetime and accepted all-date prediction seal
must precede any reserved query-level Y. Actual W/budgets remain external gates.

The requested repair is satisfied at the final exact v3 bytes. No broader suite
or actual runtime was needed or run for this rereview.
