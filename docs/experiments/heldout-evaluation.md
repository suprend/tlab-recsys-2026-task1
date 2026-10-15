# Gated fullY reporting core

This additive core performs no file/model load, native prediction, fit, approval
issuance or automatic retry. Its measured caller authenticates the complete
whole-decision/source/all-prediction snapshots and explicit target intent, owns
private readers/connection, consumed contexts and complete resource lifetime.
Code tests use only synthetic tables and score arrays. No actual reserved target
has been opened by implementation or tests.

`evaluate_windows` validates the already-authenticated B/W choice, seven-date
source/prediction inventory and external prediction acceptance before providers
run. The target intent must bind exact lock/inventory digests, strictly later
physical opening, both fixed reporting windows and no adaptation. Schema
validation is not an independent issuance or capability; caller-authored trusted
snapshots do not authenticate themselves.

Providers are explicit: `load_day_population(daySource)` supplies all Q triples,
calendar flags and exact keyed C group/items from Q/C artifacts, independently
of model scores/features. `load_saved_scores(predDescriptor)` supplies keyed
float64 raw score arrays. All seven dates and both models load, snapshot and
validate before the first source/target operation. Counts, midnight anchors,
int64 users/products, int32 groups, canonical distinct keys, per-Q220 cap,
all-current-Q calendar maturity and finite scores are checked. Saved keys must
match every C key; W=B requires identical scores. Retained copies decouple prior
days from later provider reuse. No user/query is selected using targets.

On a caller-owned two-thread private DuckDB connection, the core exclusively
creates `heldout_target_queries`, proves its exact equality to retained all-date
Q, then creates `heldout_full_targets` from `heldout_raw_events`: distinct
purchase products for the same user at anchor≤event_time<anchor+24h, excluding
NULL products. Exact retained Q equality is checked inside the target operation
immediately before its JOIN, after the stage, after target loading, and after
the last terminal guard. No callback follows the final comparison. A stage
wrapper that substitutes a user before the JOIN or drops Q after it fails; the
original attempt remains consumed. C is absent from this SQL. Duplicate purchase rows collapse only
for binary relevance; purchases outside C and positive emptyC queries remain
misses. All current25–31 horizons are mature under declared Nov1 coverage and
delay0. Existing temp target names reject accidental same-connection retry;
a new connection does not grant a new external attempt.

The two predeclared outputs are `confirmation25_reporting_only` and
`final26_31_frozen`, using the same saved B/W. K20 ties are raw-score descending,
exact product-ID ascending, with no rounding. Public006 `evaluate` supplies all
four estimands; public006 `paired_user_bootstrap` supplies W−B NDCG with200
replicates/seed2026 and undefined draws retained. Canonical anchor/query order
keeps mature-user cluster order identical across estimands. User clustering
preserves within-user queries; it does not model common date shocks or turn
query-macro into user-macro. Support explicitly includes full target pairs,
retrieved targets and positive emptyC. No heldout Recall threshold or selected
headline window is introduced.

Return `periods` is aggregate-only. `private_targets` and `private_rankings`
contain private keys/labels and must stay ignored run artifacts; the core prints
nothing. The owner may export its temporary fullY relation and private cache for
proof, then publish only aggregate results. Independent source-derived fullY/
metric/bootstrap verification and external full-lifetime acceptance are still
mandatory. Reused006 arithmetic is production logic, not its own independent
expected oracle. Cooperative guards surround stages/rows/estimands; the outer
owner must supervise long SQL/bootstrap calls and account failure/cleanup/exit
tail. A failed call after Y access leaves the original label reservation consumed
and never authorizes adaptation, a refit or an unreported repeat.

Twenty meaningful synthetic tests use at most10 raw events, six Q and seven
C per model. Literal gold covers exact anchor/end boundaries, duplicate purchase
collapse, outC targets, positive emptyC, zeroY/emptyQ, >2^53 keys, W=B, query/user
macro differences and all200 paired multiplicity draws. Admission/provider/type/
key/maturity/precision/clock/adaptation faults reject before Y; last-day corruption
still prevents all target operations, staged Q omission/substitution and late
terminal mutation are rejected, all21
provider calls precede target creation, and post-Y failure is preserved. These
are code/interface checks, not actual heldout results or execution authority.
