# Hand-derived tiny CLI relations

This is a source-derived expected fixture, not execution evidence or a blind FIRST. See the contamination disclosure. All times are UTC; physical TIMESTAMP values are naive UTC wall clocks. Define q8u1, q8u2, q18u3, q18u4, q18u5 as SHA-256 of the literal ASCII strings `query|2026|2019-10-08T00:00:00Z|1`, `query|2026|2019-10-08T00:00:00Z|2`, `query|2026|2019-10-18T00:00:00Z|3`, `query|2026|2019-10-18T00:00:00Z|4`, `query|2026|2019-10-18T00:00:00Z|5`. Do not call production stable_key to manufacture the expected query population. Presentation order below is symbolic/user order; prepared group order is actual query-ID order and must be joined back to these identities.

The full typed9 event table has ten rows. Product/category keys are BIGINT, price is DECIMAL(12,2). For non-NULL products p, use category_id=p, category_code='synthetic.item', brand='fixture', price=1.00; for NULL product use NULL for those four metadata fields. user_session='fixture-u<user>' on every row. All are declared synthetic values, not production metadata/profile claims.

| Row | event_time | type | product | user |
|---|---|---|---:|---:|
| 1 | 2019-10-07 23:00:00 | view | 10 | 1 |
| 2 | 2019-10-07 23:30:00 | purchase | 20 | 2 |
| 3 | 2019-10-08 00:10:00 | purchase | 10 | 1 |
| 4 | 2019-10-17 23:00:00 | view | 10 | 3 |
| 5 | 2019-10-17 23:00:00 | view | 20 | 3 |
| 6 | 2019-10-17 23:00:00 | view | NULL | 4 |
| 7 | 2019-10-17 23:00:00 | view | 20 | 5 |
| 8 | 2019-10-18 00:10:00 | purchase | 10 | 3 |
| 9 | 2019-10-18 00:20:00 | purchase | 99 | 3 |
| 10 | 2019-10-18 00:30:00 | purchase | 77 | 4 |

All Q rows have history_active_days_7d=1, history_coverage_7d=1.0 and label_is_mature=TRUE derived by actual label code under the declared source/availability calendar. Last history timestamp is shown explicitly.

| Q | anchor | user | eligibility_events | history_events_7d | history_distinct_items_7d | last_history_time | full Y |
|---|---|---:|---:|---:|---:|---|---|
| q8u1 | 2019-10-08 00:00:00 | 1 | 1 | 1 | 1 | 2019-10-07 23:00:00 | {10} |
| q8u2 | 2019-10-08 00:00:00 | 2 | 1 | 1 | 1 | 2019-10-07 23:30:00 | {} |
| q18u3 | 2019-10-18 00:00:00 | 3 | 2 | 2 | 2 | 2019-10-17 23:00:00 | {10,99} |
| q18u4 | 2019-10-18 00:00:00 | 4 | 1 | 1 | 0 | 2019-10-17 23:00:00 | {77} |
| q18u5 | 2019-10-18 00:00:00 | 5 | 1 | 1 | 1 | 2019-10-17 23:00:00 | {} |

Y rows have raw_purchase_rows=1, same_second_purchase=FALSE. Full targets remain separate from C; 99 and 77 must never be inserted into C/F.

| Q | product | first_purchase_time | catalog_seen_before | pair_seen_before |
|---|---:|---|---|---|
| q8u1 | 10 | 2019-10-08 00:10:00 | TRUE | TRUE |
| q18u3 | 10 | 2019-10-18 00:10:00 | TRUE | TRUE |
| q18u3 | 99 | 2019-10-18 00:20:00 | FALSE | FALSE |
| q18u4 | 77 | 2019-10-18 00:30:00 | FALSE | FALSE |

| Q | product | popular | recent | popularity_distinct_users | popular_rank | recent_rank | last_user_event_time | binary matrix y |
|---|---:|---|---|---:|---:|---:|---|---:|
| q8u1 | 10 | FALSE | TRUE | 0 | NULL | 1 | 2019-10-07 23:00:00 | 1 |
| q8u1 | 20 | TRUE | FALSE | 1 | 1 | NULL | NULL | 0 |
| q8u2 | 20 | TRUE | TRUE | 1 | 1 | 1 | 2019-10-07 23:30:00 | 0 |
| q18u3 | 10 | FALSE | TRUE | 0 | NULL | 1 | 2019-10-17 23:00:00 | 1 |
| q18u3 | 20 | FALSE | TRUE | 0 | NULL | 2 | 2019-10-17 23:00:00 | 0 |
| q18u5 | 20 | FALSE | TRUE | 0 | NULL | 1 | 2019-10-17 23:00:00 | 0 |

q18u4 has exactly zero C/F rows and remains in Q, fullY and prepared. No dummy row is allowed. Same-time recent tie for user3 resolves product10 before20. F is exactly C, three rows per collection; the actual manual18 schema is 45 columns, yielding 41 numeric prepared features after exclusions plus retrieval-age/missing additions. Expected each X is 3×41 float32=492 bytes; cap4 bounds X alone to656 bytes, not process RSS. Prepared group/items/y dtypes are int32/int64/int8.

| Collection | Q | Y rows | C=F rows | positive fullY Q | empty-Y Q | empty-C Q | fullY outside C | informative groups | row weight sum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| train | 2 | 1 | 3 | 1 | 1 | 0 | 0 | 1 | 2.0 |
| selection | 3 | 3 | 3 | 2 | 1 | 1 | 2 | 1 | 2.0 |

For validation prefix k=1..8, sort user3's candidates by (-raw_score,product_id). If target10 has rank r in {1,2}, its NDCG is `(1/log2(r+1))/(1+1/log2(3))`; user4's empty-C positive NDCG is0. Conditional macro denominator is2, all-query-zero denominator is3; user5's empty Y contributes only to the latter denominator. Thus primary curve[k]=that user3 NDCG/2. Ideal DCG uses TWO full targets despite only one retrieved positive. Independently compute all eight values, then choose smallest k with value >= global_max-1e-12. Do not predeclare a native score/rank/selected tree. Require support fullY_positive_queries=2, candidate_rows=2, informative_candidate_groups=1 and full validation accounting Q=3/C=3. Save/reload parity must cover all three validation candidate rows, including user5, while retaining user4's empty ranking.
