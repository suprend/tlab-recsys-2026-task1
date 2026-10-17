# Independent coverage statistics: SOURCE proposal, UNRUN

This note describes only `oracle_stats.py`. Its sole substantive analysis source is
`/tmp/tlab-hyp061-q6000-seal-proposal-v1/NEXTSTAGE-PLAN-v2.md`, SHA256
`b8896d7f7ee7a12593cdfdfe4f7f3fc4a58bddbd9e3f7312b96de895a104565f`.
The author did not read primary-consumer/estimands/project implementation,
actual Q/C/Y/JSONL/results or peers102, and did not import or execute this module,
run tests, use a database, use the network, or touch Git/canonical files.
This is an independent implementation proposal, not analysis admission or a
claim that any actual cohort has been evaluated. The parent author owns I/O,
authentication, cardinality/lineage checks and tiny literal checks.

## API and accepted input

`calculate(records, draws=2000, seed=61061, check=lambda: None)` uses only Python
standard-library `hashlib`, `math` and `random`; it has no I/O, clock, environment,
database or project dependencies. `check()` is a cooperative cancellation/budget
hook; exceptions propagate. It is called initially/finally, at least every 32
input rows, at every bootstrap draw and every 256 sample/user-vector steps.
There is no executable entry point and no retrieval/graph/candidate rebuilding.

`records` must be an exact list of zero through 6000 exact dicts. Each dict must
contain the following keys (additional record metadata is ignored):

- `query_id`: exact ASCII `str`, unique in the list. ASCII sorting supplies the
  global point and within-user query-reduction order. Empty strings are accepted;
  production query-ID shape is the caller's responsibility.
- `user_id`: exact `int`, including signed values; bool is rejected.
- `targets`: exact `set` of exact int item IDs; all fullY targets, including off-C.
- `prior`: exact `set` of exact int item IDs from the already authenticated sealed
  all-past pair relation. The function does not infer or filter this relation.
- `arms`: exact dict with exactly `C0`, `count`, `cos`, `matched_popular`,
  `matched_count`, `matched_cos`, each an exact `frozenset` of exact int IDs.

`draws` is a positive exact int and `seed` is an exact int. Defaults are the
prespecified 2000/61061; configurable values support caller-owned tiny fixtures,
and the caller must require the prespecified values for actual analysis.
Input objects are never mutated. Wrong types/caps/duplicate queries raise
`TypeError` or `ValueError`; there is no truncation or repair.

## Point definitions and reduction

The slice names, in order, are `full`, `new`, `repeat`, where targets are Y,
Y minus prior, and Y intersect prior. Each slice has its own positive-query count
and target mass. Full-C hits use the complete provided candidate set, with no
Recall@20 truncation. Empty-target recall is undefined. Oracle NDCG@20 uses
`D(min(20,hits))/D(min(20,target_mass))`, where
`D(n)=sum(1/log2(rank+1), rank=1..n)`, over the slice's positive queries.
It describes accessibility, not achieved ranking quality.

All point sums, including arm Recall/oracle sums and paired Recall difference
sums, are accumulated directly in global ascending ASCII query-ID order using
ordinary binary64 `+=`. They are not reconstructed from per-user aggregates.
Separate per-user vectors, used only by bootstrap, accumulate their queries in
that same ASCII query-ID order. Full/new/repeat vectors include paired per-query
Recall differences, so contrasts do not subtract separately rounded arm means.
Bootstrap user vectors are reduced by ascending signed numeric user ID with
explicit binary64 `+=` (no implementation-dependent float `sum`). Zero-fullY user
vectors are exactly zero and may be skipped in bootstrap numeric reduction.

The four Recall contrasts, in order, are `cos-C0`, `count-C0`, `cos-count`,
`matched_cos-matched_popular`. Each contrast uses the same positive queries
within its slice. In particular, an empty source or k=0 row with positive targets
stays in the denominator; equal matched sets contribute zero.

## Exact return shape

The top-level result is exactly `{"summary": PUBLIC, "_bootstrap": PRIVATE}`.
`None` means NA; JSON writers should emit it as `null`, never NaN or a string.
PUBLIC has these keys:

- `schema`: `"tlab.hyp061.independent-coverage-stats.v1"`.
- `frame`: `queries`, `users`, `positive_queries`, `zero_target_queries`,
  `target_mass`, all exact ints. `users` includes every distinct fixed-frame user.
- `slices[full|new|repeat]`: `{positive_queries: int, target_mass: int}`.
- `arms[ARM][SLICE]`: exactly `hits` (int), `macro_recall` (float/None),
  `micro_recall` (float/None), `hit_any` (int),
  `hit_any_over_positive_queries` (float/None),
  `hit_any_over_all_queries` (float/None), `oracle_ndcg20` (float/None).
  Macro/positive hit-any/oracle use the slice's positive-query count; micro uses
  its target mass. All-Q hit-any uses the entire fixed query count, including
  empty-target rows (6000 for actual analysis); an empty overall frame gives NA.
  No arm bootstrap or confidence interval is introduced.
- `contrasts[CONTRAST][SLICE]`: exactly `estimate` (float/None),
  `ci95` (two-float `[lower, upper]` or None), `defined_draws` (int),
  `undefined_draws` (int), `interval_basis` (string described below).
- `bootstrap`: `draws`, `seed`,
  `frame="all-distinct-query-users-including-zero-target-users"`,
  `sampling="M-users-with-replacement-shared-across-arms-and-slices"`,
  `interval="95-percent-percentile-type7"`,
  `primary={contrast:"cos-C0", slice:"full"}`.
- `continuation`: `passed` (bool), `decision` (`propose_optional_continuation`,
  `reject_current_cosine_continuation`, or `inconclusive`), `reason`,
  `native_cos_ge_0_005`, `native_cos_lower95_gt_0`, `matched_cos_gt_0`.
  The last three fields are bool/None; thresholds are respectively >= .005,
  primary lower bound > 0, and full matched-cosine point > 0. No IDs appear in
  PUBLIC.

PRIVATE is intended solely for caller-owned equivalence checks, never the safe
aggregate report. It contains:

- `query_ids`: ascending ASCII query IDs;
- `user_ids`: ascending signed numeric user IDs, including zero-target users;
- `draw_denominators[SLICE]`: list of `draws` exact int positive-query counts;
- `draw_contrasts[CONTRAST][SLICE]`: 12 lists, each of length `draws`, of float/None
  estimates in RNG draw order;
- `multiplicity_sha256`: list of `draws` lowercase SHA256 hex digests;
- `multiplicity_encoding`:
  `"ascending-signed-user-ID uint32 big-endian counts"`.

Every multiplicity digest hashes the concatenation of M unsigned four-byte
big-endian multiplicities in `user_ids` order, with no separator, prefix or
suffix. A frame of M=0 hashes empty bytes. This stores no M-by-draw matrix; IDs
and digests must remain private. Per-draw multiplicities sum to M.

## Shared cluster bootstrap and NA policy

One local `random.Random(seed)` is initialized once. For every draw, exactly M
successive `randrange(M)` calls select M users with replacement from the full
sorted user frame. The same multiplicities apply to all arms, contrasts, target
slices and all day/query rows belonging to each selected user. Each user's
previously ordered vector is multiplied by its multiplicity; resulting vectors
are reduced in ascending signed user-ID order. Every draw recomputes each
slice's positive-query denominator, giving a query-macro ratio rather than a
user-macro mean. There is no redraw, unique-membership replacement, or zero
substitution. For an empty frame there are no RNG calls and all draws are NA.

Percentiles sort the defined values, use zero-based h=(n-1)p, and linearly
interpolate between floor(h)/ceil(h) at p=.025/.975 (type 7). The sole primary
interval is `cos-C0/full`: its `interval_basis` is `all-draws-required`, and any
undefined primary draw sets its entire `ci95` to None. All eleven secondary
contrast/slice intervals state `conditional-on-defined`, carry explicit defined
and undefined counts, and are computed from defined draws only; no defined
draws means NA.

`passed` is true only when all three prospective conditions hold; otherwise it is
false, including undefined cases. If full N+=0, continuation is `inconclusive`
with `reason=N_PLUS_ZERO`. Otherwise, any undefined primary draw gives
`inconclusive` with `reason=UNDEFINED_PRIMARY_DRAWS`. With a fully defined primary
interval, `passed=true` gives `propose_optional_continuation` /
`reason=ALL_PROSPECTIVE_CRITERIA_MET`. A false result with primary upper 95% <= 0
gives `reject_current_cosine_continuation` / `reason=PRIMARY_UPPER95_NONPOSITIVE`.
All other false results give `inconclusive` /
`reason=PROSPECTIVE_CRITERION_NOT_MET`. These are reporting labels for the same
thresholds and NA rules; the primary is never switched to count.

## Source status

No actual data, project imports, runtime or tests were accessed during authorship.
Only source writing and permitted source metadata checks are within this helper's
scope. Parent integration, independent review and separately authorized runtime
checks remain required; no measurement, continuation decision or promotion is
claimed here.
