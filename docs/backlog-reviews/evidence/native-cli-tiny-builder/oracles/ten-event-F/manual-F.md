# Ten-event manual F oracle, v1

This is an independent hand derivation **before F production for a disclosed fixture**. It is not a new blind-design FIRST. Inputs were the frozen builder's event/config literals, the selected manual Q/Y/C specification, and actual registry/formula source. No generated F, source database, model or score was read. No application import, SQL, test, calculation program, builder execution, fit or inference was run. The earlier nine-event FIRST and its pins/freeze remain unchanged.

## Literal fixture and clocks

All clocks below are October 2019 UTC; physical TIMESTAMP is naive UTC wall time. For every non-NULL product p, category_id=p, category_code=`synthetic.item`, brand=`fixture`, price=1.00. For NULL product, those four metadata fields are NULL. Every user_session is `fixture-u<user>`. These are synthetic metadata, not production metadata claims. The source schema is the frozen typed9 schema.

| Event | UTC time | Type | Product | User | Category |
|---|---|---|---:|---:|---:|
| 1 | 07 23:00 | view | 10 | 1 | 10 |
| 2 | 07 23:30 | purchase | 20 | 2 | 20 |
| 3 | 08 00:10 | purchase | 10 | 1 | 10 |
| 4 | 17 23:00 | view | 10 | 3 | 10 |
| 5 | 17 23:00 | view | 20 | 3 | 20 |
| 6 | 17 23:00 | view | NULL | 4 | NULL |
| 7 | 17 23:00 | view | 20 | 5 | 20 |
| 8 | 18 00:10 | purchase | 10 | 3 | 10 |
| 9 | 18 00:20 | purchase | 99 | 3 | 99 |
| 10 | 18 00:30 | purchase | 77 | 4 | 77 |

Base clock-48h policy retains source[Oct01,Nov01), 48-hour eligibility, 168-hour popular/recent windows, seed2026, and target[anchor,anchor+24h). Its disclosed changes are daily cap3; popular2/recent2/max_unique4; base budget9Q/36pairs. Train is[Oct08,Oct09), selection[Oct18,Oct19); label cutoffs equal their range ends. Both phases have shard_days1, caps3Q/12pairs and wall60s. Shared model timing is fit_data_cutoff=Oct09 00:00, available_at=Oct10 00:00, so train labels mature before model availability and validation anchor Oct18. Final holdout starts Oct26.

The symbolic query names q8u1, q8u2, q18u3, q18u4, q18u5 refer to SHA256 of the literal ASCII form `query|2026|<ISO-anchor>|<user>`. No query-ID digest was calculated here. Compare actual outputs by this identity, not presentation order; actual prepared groups use query-ID order.

| F row | Query | Anchor | User | Product |
|---|---|---|---:|---:|
| T1 | q8u1 | 08 00:00 | 1 | 10 |
| T2 | q8u1 | 08 00:00 | 1 | 20 |
| T3 | q8u2 | 08 00:00 | 2 | 20 |
| V1 | q18u3 | 18 00:00 | 3 | 10 |
| V2 | q18u3 | 18 00:00 | 3 | 20 |
| V3 | q18u5 | 18 00:00 | 5 | 20 |

There are exactly three train and three selection F rows. q18u4 has no C/F row; no dummy is permitted. Products99 and77 remain full-Y targets outside C.

## All 18 registry features

Indices are **registry order**, which differs from physical feature-column order. NULL means SQL NULL and later float32 NaN, never zero. Counts are raw event counts, except the named distinct counts.

| Registry index | Feature | T1 | T2 | T3 | V1 | V2 | V3 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | user_view_7d | 1 | 1 | 0 | 2 | 2 | 1 |
| 2 | user_cart_7d | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 | user_purchase_7d | 0 | 0 | 1 | 0 | 0 | 0 |
| 4 | user_distinct_viewed_items_7d | 1 | 1 | 0 | 2 | 2 | 1 |
| 5 | pair_view_7d | 1 | 0 | 0 | 1 | 1 | 1 |
| 6 | pair_cart_7d | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | pair_purchase_7d | 0 | 0 | 1 | 0 | 0 | 0 |
| 8 | pair_view_recency_seconds | 3600 | NULL | NULL | 3600 | 3600 | 3600 |
| 9 | pair_purchase_recency_seconds | NULL | NULL | 1800 | NULL | NULL | NULL |
| 10 | item_view_24h | 1 | 0 | 0 | 1 | 2 | 2 |
| 11 | item_purchase_24h | 0 | 1 | 1 | 0 | 0 | 0 |
| 12 | item_distinct_viewers_7d | 1 | 0 | 0 | 1 | 2 | 2 |
| 13 | user_category_view_7d | 1 | 0 | 0 | 1 | 1 | 1 |
| 14 | user_category_view_share_7d | 1 | 0 | NULL | 0.5 | 0.5 | 1 |
| 15 | user_category_view_recency_seconds | 3600 | NULL | NULL | 3600 | 3600 | 3600 |
| 16 | item_category_view_7d | 1 | 0 | 0 | 1 | 2 | 2 |
| 17 | category_view_7d | 1 | 0 | 0 | 1 | 2 | 2 |
| 18 | item_category_view_share_7d | 1 | NULL | NULL | 1 | 1 | 1 |

At train anchor, only events1–2 are past. At selection anchor, the 7-day count windows begin Oct11 00:00 and the 24-hour windows begin Oct17 00:00: only events4–7 contribute to these counts. Product20 has two views from distinct users3 and5, hence item/category counts2. Its two latest-timestamp rows both say category20, so category is known and unambiguous.

Recency and observed-age searches use full observed strict-past history, not the count lookback. The old purchases by users1/2 cannot create purchase recency for users3/5. All purchases after either anchor are excluded from F, including the eventual positive products. Category counters use each past event's historical category_id. Filled metadata on future products99/77 cannot create past catalog evidence.

Known category with no matching view gives count0. T2's user-category share is0/1=0. T3's user-category share is0/0=NULL. T2/T3 item-category shares are0/0=NULL. Missing recency is NULL. This fixture does **not** cover ambiguous or missing candidate-category metadata: all six C rows have known categories. The NULL-product eligibility event creates no candidate row.

## Context and retrieval fields

| Context field | T1 | T2 | T3 | V1 | V2 | V3 |
|---|---:|---:|---:|---:|---:|---:|
| candidate_category_id | 10 | 20 | 20 | 10 | 20 | 20 |
| candidate_category_ambiguous | FALSE | FALSE | FALSE | FALSE | FALSE | FALSE |
| candidate_category_missing | FALSE | FALSE | FALSE | FALSE | FALSE | FALSE |
| item_has_observed_history | TRUE | TRUE | TRUE | TRUE | TRUE | TRUE |
| user_has_observed_history | TRUE | TRUE | TRUE | TRUE | TRUE | TRUE |
| item_observed_age_seconds | 3600 | 1800 | 1800 | 867600 | 865800 | 865800 |
| user_observed_age_seconds | 3600 | 3600 | 1800 | 3600 | 3600 | 3600 |
| source_coverage_24h | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| source_coverage_168h | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

Product10 first observed Oct07 23:00; product20 first observed Oct07 23:30. Selection ages therefore retain ten days plus one hour / thirty minutes even though the original events are outside 7-day counts. Users3/5 first observed Oct17 23:00. q18u4 also has observed user history from its NULL-product view, but no F row on which to materialize user fields. Coverage means declared source-time overlap, not exposure or data density.

| Retrieval field | T1 | T2 | T3 | V1 | V2 | V3 |
|---|---|---|---|---|---|---|
| from_popular | FALSE | TRUE | TRUE | FALSE | FALSE | FALSE |
| from_recent | TRUE | FALSE | TRUE | TRUE | TRUE | TRUE |
| popularity_distinct_users | 0 | 1 | 1 | 0 | 0 | 0 |
| popular_source_rank | NULL | 1 | 1 | NULL | NULL | NULL |
| recent_source_rank | 1 | NULL | 1 | 1 | 2 | 1 |
| last_user_event_time | 07 23:00 | NULL | 07 23:30 | 17 23:00 | 17 23:00 | 17 23:00 |
| retrieval_last_event_age_seconds | 3600 | NULL | 1800 | 3600 | 3600 | 3600 |
| retrieval_last_event_missing | FALSE | TRUE | FALSE | FALSE | FALSE | FALSE |
| matrix y, separate from X | 1 | 0 | 0 | 1 | 0 | 0 |

Retrieval age/missing are added by prepare_dataset, not columns of the 45-column physical F. At train anchor, global popular source is{20}; at selection anchor it is empty because both old purchases precede Oct11. Same-time user3 recent ties resolve product10 before20. Fixed retrieval columns pass through F unchanged.

## NULL masks

These are the eight generated core-feature `_missing` columns; FALSE/TRUE become0/1 in prepared X and are themselves non-NULL.

| Generated flag | T1 | T2 | T3 | V1 | V2 | V3 |
|---|---:|---:|---:|---:|---:|---:|
| pair_view_recency_seconds_missing | FALSE | TRUE | TRUE | FALSE | FALSE | FALSE |
| pair_purchase_recency_seconds_missing | TRUE | TRUE | FALSE | TRUE | TRUE | TRUE |
| user_category_view_7d_missing | FALSE | FALSE | FALSE | FALSE | FALSE | FALSE |
| user_category_view_share_7d_missing | FALSE | FALSE | TRUE | FALSE | FALSE | FALSE |
| user_category_view_recency_seconds_missing | FALSE | TRUE | TRUE | FALSE | FALSE | FALSE |
| item_category_view_7d_missing | FALSE | FALSE | FALSE | FALSE | FALSE | FALSE |
| category_view_7d_missing | FALSE | FALSE | FALSE | FALSE | FALSE | FALSE |
| item_category_view_share_7d_missing | FALSE | TRUE | TRUE | FALSE | FALSE | FALSE |

| Row | NULL registry indices, 1-based | NaN prepared-X indices, 1-based |
|---|---|---|
| T1 | {9} | {4,20} |
| T2 | {8,9,15,18} | {5,19,20,25,31,40} |
| T3 | {8,14,15,18} | {19,25,30,31} |
| V1 | {9} | {4,20} |
| V2 | {9} | {4,20} |
| V3 | {9} | {4,20} |

For a future feature report, train core NULL counts are pair_view_recency_seconds2, pair_purchase_recency_seconds2, user_category_view_share_7d1, user_category_view_recency_seconds2, item_category_view_share_7d2; all other core NULL counts0. Selection has pair_purchase_recency_seconds3 and every other core NULL count0.

The physical F schema has45 columns. Prepared X excludes query_id,user_id,product_id,anchor,candidate_category_id,last_user_event_time and appends retrieval-age/missing, giving41 numeric columns. Its exact order for the masks above is:

| X index | Name | X index | Name |
|---:|---|---:|---|
| 1 | from_popular | 22 | item_purchase_24h |
| 2 | from_recent | 23 | item_distinct_viewers_7d |
| 3 | popularity_distinct_users | 24 | user_category_view_7d |
| 4 | popular_source_rank | 25 | user_category_view_recency_seconds |
| 5 | recent_source_rank | 26 | item_category_view_7d |
| 6 | candidate_category_ambiguous | 27 | category_view_7d |
| 7 | candidate_category_missing | 28 | source_coverage_24h |
| 8 | item_has_observed_history | 29 | source_coverage_168h |
| 9 | user_has_observed_history | 30 | user_category_view_share_7d |
| 10 | item_observed_age_seconds | 31 | item_category_view_share_7d |
| 11 | user_observed_age_seconds | 32 | pair_view_recency_seconds_missing |
| 12 | user_view_7d | 33 | pair_purchase_recency_seconds_missing |
| 13 | user_cart_7d | 34 | user_category_view_7d_missing |
| 14 | user_purchase_7d | 35 | user_category_view_share_7d_missing |
| 15 | user_distinct_viewed_items_7d | 36 | user_category_view_recency_seconds_missing |
| 16 | pair_view_7d | 37 | item_category_view_7d_missing |
| 17 | pair_cart_7d | 38 | category_view_7d_missing |
| 18 | pair_purchase_7d | 39 | item_category_view_share_7d_missing |
| 19 | pair_view_recency_seconds | 40 | retrieval_last_event_age_seconds |
| 20 | pair_purchase_recency_seconds | 41 | retrieval_last_event_missing |
| 21 | item_view_24h | | |

## Retained populations and denominators

| Query | Full Y | C | Mature | Empty Y | Empty C | Candidate y | Per-row weights |
|---|---|---|---|---|---|---|---|
| q8u1 | {10} | {10,20} | TRUE | FALSE | FALSE | 1,0 | .5,.5 |
| q8u2 | {} | {20} | TRUE | TRUE | FALSE | 0 | 1 |
| q18u3 | {10,99} | {10,20} | TRUE | FALSE | FALSE | 1,0 | .5,.5 |
| q18u4 | {77} | {} | TRUE | FALSE | TRUE | no row | no row |
| q18u5 | {} | {20} | TRUE | TRUE | FALSE | 0 | 1 |

Train accounting: Q2, full-Y rows1, candidate/F rows3, positive-fullY Q1, informative groups1, all-negative groups1, all-positive groups0, empty-C groups0, zero-gradient-pairwise groups1, retrieved positive rows1, row-weight sum2. Selection accounting: Q3, full-Y rows3, candidate/F rows3, positive-fullY Q2, informative groups1, all-negative groups1, all-positive groups0, empty-C groups1, zero-gradient-pairwise groups2, retrieved positive rows1, row-weight sum2. Every Q remains in prepared. Empty C creates no BCE row/weight; it remains a metric query.

Both complete matrices are3×41 float32; group/items/y are int32/int64/int8. All represented NULLs stay NaN and all other cells above are finite. label_is_mature lives in Q; it is not an F/X field. No candidate label or full-Y target becomes a feature.

At each future prefix1..8, let r be product10's rank among user3's two candidates after sorting(-raw_score,product_id). Define I=1+1/log2(3). Its full-Y NDCG@20 is D=(1/log2(r+1))/I because full Y has TWO targets, including missing product99. q18u4 contributes0 despite having no candidate. q18u5's empty-Y metric is undefined individually, excluded from conditional aggregation and assigned0 by all-query-zero aggregation.

Thus selection conditional macro NDCG=D/2, with positive-only queries{q18u3,q18u4}; all-query-zero NDCG=D/3, with all queries{q18u3,q18u4,q18u5}. Conditional recall is(1/2+0)/2=1/4; all-query-zero recall is(1/2)/3=1/6. A positive-only staged projection has2queries/2candidate rows; full-cohort save/reload parity must cover all3candidate rows, including q18u5, and retain q18u4's empty ranking. User and query macro denominators coincide here because each user has one query. On train, the corresponding positive-only and all-query-zero denominators are 1 and 2, respectively.

No native scores, ranking or selected tree are predeclared. A future independently checked complete curve selects the earliest tree within1e-12 of the GLOBAL maximum; flat is allowed. One future native fit≤8trees remains ungranted. Neither this document nor source inspection creates approvals, accepted F or CLI E2E evidence.

## Traceability

Source pins and exact read scopes are in source-pins.json. Primary formula anchors: [registry](/Users/mdpospelov/tlab-recsys-2026/configs/features/manual-18.json), [raw counts/recency/grain filtering](/Users/mdpospelov/tlab-recsys-2026/scripts/manual_features.py:114), [strict-past metadata and ages](/Users/mdpospelov/tlab-recsys-2026/scripts/manual_features.py:175), [conditional counts/ratios/missing](/Users/mdpospelov/tlab-recsys-2026/scripts/manual_features.py:203), [prepared names](/Users/mdpospelov/tlab-recsys-2026/scripts/train_baselines.py:188), [full-Y/NaN preparation](/Users/mdpospelov/tlab-recsys-2026/scripts/train_baselines.py:238), [query accounting](/Users/mdpospelov/tlab-recsys-2026/scripts/train_baselines.py:274), [full-target metric](/Users/mdpospelov/tlab-recsys-2026/scripts/ranking_metrics.py:114).
