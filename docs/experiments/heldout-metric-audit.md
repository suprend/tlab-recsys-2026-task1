# Independent reserved fullY and metric audit core

This additive observer core imports neither production006 ranking arithmetic,
production evaluation, nor any production target builder. Its own raw SQL groups
purchase products for each accepted Q over anchor≤time<anchor+24h. Its own index
permutation ranks finite raw scores descending and exact int64 product IDs
ascending. FullY includes out-of-C products and positive empty-C queries. This is
code-level independence, not an authenticated output or runtime grant.

The measured caller must separately authenticate all raw/Q/C/score/report/target
bytes, current code/environment, original consumed observer context and externally
approved target opening. It supplies a private bounded two-thread DuckDB connection
with typed `heldout_raw_events`. `audit_windows` has no CLI, file/model opener,
fit, native inference, approval writer, retry or budget issuance. It does not
independently derive Q/C populations from raw history: the separately accepted
source oracle owns that proof. Here every supplied accepted Q/C and saved score
is checked and every accepted query's fullY is reconstructed independently.

`days` contains exactly seven canonical25–31 UTC day dictionaries, each with
`anchor,queries,calendar_maturity,group,items,scores`. Q entries are exact
`(query_id,user_id,naive_UTC_anchor)` triples. Calendar is bool, C group is int32,
items int64, B/W saved scores float64. At most2000Q/440000C per day and220C per Q
are allowed; all current queries must be mature under declared Nov1 coverage.
Keys must be distinct canonical, all dates retained even when empty, daily users
unique, and all scores finite. Private copies prevent later caller array reuse.
`produced_targets` maps exactly every Q to an exact int64 set, including emptyY;
`produced_periods` is the aggregate evaluator report. Authentication is the
external caller's obligation, rather than something these Python objects prove.

The observer exclusively stages `heldout_metric_queries`, checks exact retained
Q immediately before its own raw JOIN and after loading, and again after the last
terminal guard. It reads distinct full targets in chunks of65536 with a2million
row safety cap. Existing oracle temp names reject accidental same-connection
retry; a fresh connection never grants a new external observer attempt. No callback
follows the terminal exact Q comparison. The source bytes must remain pinned
through full external owner lifetime; this core does not provide filesystem
atomicity or protect against arbitrary concurrent database writers.

Four metrics are independently calculated: Recall, NDCG, AP normalized by full
Y size, and reciprocal rank. Ideal DCG uses min(20,fullY size). EmptyY is undefined
conditionally and zero in all-query/all-user variants. Query macro weights each
eligible query; user macro first averages eligible queries within each user.
Positive-emptyC remains a miss. Both fixed windows—25 reporting-only and26–31
final—are always reconstructed with the same frozen scores.

The bootstrap uses the same explicitly required Python Random2026/choices
semantics and canonical first-appearance user order. It generates200 paired
user draws once per window, then independently expands whole sampled user
clusters for each estimand. It does not reuse production multiplicity/totals
helpers. Undefined conditional draws remain None; percentile interpolation uses
only defined draws. Every draw, interval, estimate, count, support field and metric
in both supplied reports is compared; exact keys/types/counts and finite floats
are required, with absolute/relative1e-12 tolerance for independent summation.
Tuple/list equivalence permits a JSON-loaded report. No heldout headline choice,
refit, score-dependent adaptation or additional resampling is performed.

Return periods contain aggregates; `private_targets/private_rankings` must remain
ignored private artifacts. The result is explicitly pending complete external
owner/byte/lifetime acceptance. Oracle arithmetic agreement cannot authenticate
source completeness, model bytes, execution resource sufficiency or original
physical target-opening chronology. The parent supervises long SQL and all
original CPU/RSS/wall/cleanup/persistence/exit-tail costs; cooperative checks do
not themselves impose a hard resource boundary.

Seventeen synthetic tests use at most10 raw rows, six Q and seven C per model.
Literal gold covers AP/full-Y denominator, product-ID ties above2^53, exact raw
horizon endpoints/duplicates/outC/emptyC and all200 bootstrap user draws with
unequal queries per user. Synthetic production-compatibility checks compare the
independent implementation to the core evaluator but do not count as an actual
output oracle. Faults cover wrong/outside-C labels, missing zeroY Q, float or
repeated IDs, target-bearing Q tuples, bad precision/calendar, altered saved
scores/draws, exact report shape and nonfinite values, same-connection retry,
no file API/production imports, guard interruption and late staged-Q mutation.
No actual reserved source, targets, native model or fit has been used.
