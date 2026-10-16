# Optional TLAB-012 source CODE prototype — V1, UNRUN

The three prospective files are new, additive and TMP-only. Existing projection
kernel, source importer, project documentation and queue are unchanged. No CLI,
controller, pilot, model, gate or execution authority is added.

`extract_itemcf_snapshot(open_source, queries, *, b, source, limits, check)` owns
the returned fresh read-only connection, validates the fixed typed9 schema, and
uses actual fixed-`events` parameterized DuckDB SELECTs for capped view history
and complete global view audiences. The opener must supply the caller's
authenticated immutable source; this function cannot prove that a supplied
connection is fresh/read-only or that the descriptor matches content. The
read-only fixture opener tests the intended adapter when separately authorized.

The batch preserves exact Q/C order and empty-C queries. NULL products precede
distinct/cap21, ties use last-time/hash/signed-ID order, and postings contain all
non-NULL eligible users with exact C-union-H keys and known-empty tuples. A member
overflow or other failure returns no partial result and closes the connection.
The kernel remains responsible for candidate exclusion/refill, own subtraction
and feature arithmetic.

The conservative preflight is `2*N`: N=42,448,764 yields 84,897,528 and refuses the
former 30m descriptor limit before any opener/check. This describes this two-pass
full-source plan, not measured physical scanning or impossibility of a future
separately authenticated pruned plan. Descriptor/authentication/content
completeness are distinct. Logical work/member bounds and cooperative checks do
not cap native SQL CPU/RSS/sort/spill or interrupt blocked native calls. Caller
external supervision is still required; no new resource allocation is implied.

Four prepared methods cover the literal 36-event→extractor→existing-kernel case
(2Q+3C=41 input rows, mean 3/260, max 3/13, refill21, empty query/key), pre-opener
source refusal, literal signed-decimal hash ties and member-overflow cleanup.
They have NOT been imported or run. The fixture engine's 128MB memory setting is
not a process RSS bound. Root's prior approximately 151MB DuckDB-unit observation
is not a measurement of this candidate, and 64MiB is not promised.

Static validation: both Python files AST-parse and compile; four unittest methods
are present; production imports only stdlib plus existing `LimitExceeded`; all
three target paths were absent. These checks do not validate native SQL APIs or
the fixture's runtime assertions. Readback/source SHA pins and exact publication
transport are in `/tmp/tlab-itemcf-extraction-manifest-v1.json` (SHA
4903fb8c1b2fdc768d5800112f6a38177783d67bcf8f6ab5d91202c723aff43e).

Only the final stdlib AST/hash preparation body was timed: 0.006178 CPU seconds,
0.006274 wall seconds, ru_maxrss 21,872,640 native macOS byte units. This is not a
whole-process or total-author cost measurement; earlier source reads/writes and
tool overhead are not included. Actual DuckDB imports/SQL/test execution,
real data/models/Y, network, helpers, project/Git writes and runtime grants: 0.

Ready for Root's independent source reviews. Any finite synthetic CODE execution
and eventual sole-coordinator installation remain separate decisions. A fixture
pass would establish its semantics only, not full-source completeness, 100Q
feasibility or recommendation benefit.
