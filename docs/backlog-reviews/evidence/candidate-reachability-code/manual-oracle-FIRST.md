# Independent FIRST manual oracle — synthetic CODE canary

Frozen from source text before reading implementation, peers, tests or proposals. No imports, SQL, helper/test execution, production data, model work, Git or network writes occurred. Scope: ordinary engineering preparation for existing 022/036/040/043/047 CODE seam; no new ID, admission, gate or execution authority.

Use five isolated histories: N, P, NP, M-before and M-after (four logical fixtures; six row instances). Let t=2019-10-08T00:00:00Z, a=t−1h=2019-10-07T23:00:00Z and b=t−2h=2019-10-07T22:00:00Z. N is (a,view,NULL,7); P is (a,view,101,7) with valid filled category_id/code/brand/price/session. NP adds (b,purchase,202,8) to N. M-before copies P; M-after preserves time/type/user/product and NULLs those five metadata fields.

Keep declared source [2019-10-01,2019-11-01), eligibility 48h, seed 2026, popular200/recent20, 168h candidate windows and max_unique220. For one anchor explicitly set pilot [t,2019-10-09T00:00:00Z); max_users_per_day=2 includes every fixture user; unchanged original budgets satisfy validation. Seven-day diagnostic coverage is 604800/604800=1 from declared source overlap, regardless of event sparsity. Eligibility counts NULL-product rows; distinct products and recent exclude NULL products. Popularity counts distinct purchasing users and broadcasts its top products to every query.

Actual create_queries leaves maturity NULL. Only after sampling set TRUE as the declared synthetic premise: candidate validation rejects NULL. This fixture premise proves neither complete future labels nor a production negative. Query IDs are SHA256 of ASCII `query|2026|2019-10-08T00:00:00Z|<user>`; sampling uses the corresponding `sample|...` payload, but cap2 retains both users without depending on order.

Invalid seams: concatenating histories changes raw counts and spreads popular202; leaving the original three-day pilot produces additional Oct9 queries (Oct10 none); shortening source coverage to the few event hours violates the 168h lookback; lowering max_unique without matching source limits violates protocol/candidate validation. No labels or coverage_report are needed to assert C.

Direct parse_row uses nine string tokens, returns naive UTC-wall-clock datetime, signed64 integers, Decimal price and None for empty nullable tokens. It is not full gzip/archive/native-import validation. Nullable schema permission proves no actual October NULL incidence. Zero ML fits still incurs parsing/SQL/resources and grants no new execution permission.

## Compact literal expected appendix

All Q rows: anchor=t; history_coverage_7d=1.0; label_is_mature=TRUE only after declared assignment. Empty C means zero rows, never a fabricated NULL-product row. Candidate tuple columns are product, from_popular, from_recent, popularity_distinct_users, popular_source_rank, recent_source_rank, last_user_event_time. NULL is literal missing value.

| Isolated history | Q user | eligibility_events | history_events_7d | history_distinct_items_7d | history_active_days_7d | last_history_time | C tuples |
|---|---:|---:|---:|---:|---:|---|---|
| N | 7 | 1 | 1 | 0 | 1 | a | ∅ |
| P | 7 | 1 | 1 | 1 | 1 | a | (101,FALSE,TRUE,0,NULL,1,a) |
| NP | 7 | 1 | 1 | 0 | 1 | a | (202,TRUE,FALSE,1,1,NULL,NULL) |
| NP | 8 | 1 | 1 | 1 | 1 | b | (202,TRUE,TRUE,1,1,1,b) |
| M-before | 7 | 1 | 1 | 1 | 1 | a | (101,FALSE,TRUE,0,NULL,1,a) |
| M-after | 7 | 1 | 1 | 1 | 1 | a | (101,FALSE,TRUE,0,NULL,1,a) |

| Isolated history | eligible_users | sampled_queries | active_eligibility_keys | popular_count_keys | popular_source_items | recent_source_pairs | candidate_rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| N | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| P | 1 | 1 | 1 | 0 | 0 | 1 | 1 |
| NP | 2 | 2 | 2 | 1 | 1 | 1 | 2 |
| M-before | 1 | 1 | 1 | 0 | 0 | 1 | 1 |
| M-after | 1 | 1 | 1 | 0 | 0 | 1 | 1 |

All scans end exclusive at t. Eligibility=[2019-10-06T00:00:00Z,t); diagnostic/popular/recent=[2019-10-01T00:00:00Z,t). Query scan_start=2019-10-01T00:00:00Z. M-before and M-after Q and C are equal, including query_id. Population/source_state ordering is anchor order; Q/C row presentation order has no contract here.
