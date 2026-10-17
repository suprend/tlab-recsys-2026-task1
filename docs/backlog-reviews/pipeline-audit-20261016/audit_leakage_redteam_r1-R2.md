# R2 crossed review — zero-query calendar day

**Confirm peer P2, with a smaller proposed witness and an execution limitation.** `audit_anchors_targets_r1-FIRST.md` and its pins match its frozen hashes. Claimed original lines are correct. This is a collection-completion defect, not demonstrated leakage or corruption of accepted October outputs. FIRST remains unchanged.

## Source trace

Original paths are relative to `/Users/mdpospelov/tlab-recsys-2026`, frozen HEAD `c538de4097322715fccac494e2b2becc3279e8e1`.

`anchor_pilot.create_queries` appends one population record for every declared day, including `eligible_users=sampled_queries=0` (`scripts/anchor_pilot.py:191–195`). `create_labels` creates typed empty Y (`:254–258`) but computes `daily_outcomes` by grouping **actual Q** (`:259–276`); zero-Q dates therefore disappear. `build_pilot` carries both reports (`:291–295`), and `run` exports empty typed Q/Y without requiring positive counts (`:349–357`). The existing empty-source test explicitly expects `daily_outcomes=[]` (`tests/test_anchor_pilot.py:176–181`); this is read source, not a test run.

Candidate construction initializes typed C even with no anchor rows (`scripts/candidate_pilot.py:50–56`), accepts zero unique counts (`:100–106`), skips catalog scanning with no Q (`:112–114`), and exports empty C (`:253–260`). F deliberately materializes a typed zero-row batch (`scripts/manual_features.py:162–164,229–244`); the runner records zero `selected_queries` and exports F (`:376–384`). External acceptance verifies hashes/lineage, without a positive-population requirement (`scripts/heuristic_baselines.py:206–270`).

Yet `aggregate_collection` derives `expected_daily` only from `ar['daily_outcomes']` (`scripts/development_collection.py:346–349`). All-zero selected F passes its query-count comparison (`:352–353`). The collector then compares this incomplete observed-date list with the phase calendar and raises at `:363–364`, before physical aggregation. The peer's two-event witness is sufficient; its second purchase is unnecessary to trigger failure.

## Smallest proposed actual-producer integration witness — UNRUN

Reuse `DevelopmentRuntimeTests`' real producer/approval/resume fixture (`tests/test_development_collection.py:106–203`), preserving typed schema and `ingest_metadata`. Phase `[2019-10-08,2019-10-10)`, `shard_days=1`, train label cutoff/fit cutoff Oct10, availability Oct11; source coverage explicitly `[Oct1,Nov1)`, 48h eligibility, 168h retrieval, 24h `[anchor,end)` labels, zero delay. Recompute plan/approval pins after replacing the source with **one** row: `(Oct08 12:00 UTC, view, product10, user1, category100)`.

The declared seven-day lookback is covered, and the last target ends Oct10, so protocol/phase maturity validators permit it (`scripts/protocol_manifest.py:105–110,125–127`; `development_collection.py:75–80`). Day08 has Q/Y/C/F=0; day09 has one Q, one recent C/F and Y=0. Thus the actual child reports entail observed calendar `[Oct09]` versus expected `[Oct08,Oct09]`. This is valid empty eligibility under an explicitly complete synthetic source, not an inferred coverage interval from observed extrema. Add the peer's second purchase only to cover off-C Y separately.

All-empty phase: use the same valid declared source/schema with zero events. Both child populations retain the two dates; all relations are empty, outcomes `[]`, and aggregation rejects `[] != [Oct08,Oct09]`. Collection completion should preserve explicit zero counts; downstream model training may legitimately reject absent training support.

A genuinely absent shard must still reject independently: fewer state entries fails `development_collection.py:331–332` (and `run_phase:517–518`); missing anchor/C/F descriptors fails `:337–338`; absent cached files fail hash verification. A repair must establish exact calendar from validated protocols/population, reconcile outcome rows to those dates, and retain those structural rejection paths. Fabricating outcome rows in a unit fixture alone misses the integration defect.

**No imports, tests, SQL, real data, native code or models executed.** Static/text/hash checks only; actual integration remains proposed, cost UNKNOWN.
