# Prepared X41: independent manual oracle v1

This is a source-derived prediction frozen before any native CLI fit or actual Prepared output. It extends the disclosed ten-event pre-F oracle; it is not a new blind-design FIRST. The accepted physical F export was read as JSON, and `scripts/train_baselines.py` was read as source only. No loader, application import, SQL, DB/Parquet data reader, model, Pool, getter or calculation program was executed. No grant or acceptance is issued here.

The old manual-F already contained all needed values, names and masks. This finite extension supplies every one of the 246 numeric coordinates in exact future prepared-row order, including the validation group gap, with labels, weights and full-Y populations. Prior freezes remain unchanged.

## Contract and row order

The expectation assumes both training queries are retained (`max_queries=None` or 2..6000) and all three selection queries are retained (`max_queries=None`), with `max_rows>=3` and within ordinary loader limit 1320000. Query selection occurs before labels. The cap's SHA ordering chooses a subset only if a cap is binding; with these inputs every query survives. `group_index` then follows lexical query_id order, and candidate rows follow `(group_index,product_id)`.

| Symbol | query_id | User | Anchor UTC | Full Y | Group |
|---|---|---:|---|---|---:|
| q8u1 | 1d9fd54d0aa58b404f7f407c325875455ad30dcc0cb223a00f96f0fcb7e20485 | 1 | 2019-10-08 00:00 | {10} | train0 |
| q8u2 | 2202586615ed160a0bdb87ab9fa955841c0b881f5c5fc5502c3189dd756dfee0 | 2 | 2019-10-08 00:00 | {} | train1 |
| q18u5 | 78285de793154a24e8a3fa3059fca6e1782c32dd20895e635a06856d65eea327 | 5 | 2019-10-18 00:00 | {} | selection0 |
| q18u4 | 8c4f5ff1efa46eb0da0cf759f6f518c6b2ec3d0be4d20322b0dd9a6ac8efbfa7 | 4 | 2019-10-18 00:00 | {77} | selection1 |
| q18u3 | c1ad425bb5ea87de63c1bdf025e4f17ded9547d87d6cda6d329361c1cfc1f689 | 3 | 2019-10-18 00:00 | {10,99} | selection2 |

Query IDs/full-Y are inherited from the preceding accepted QYC and manual review, not recomputed from F. q18u4 has no candidate/F row; there is no dummy X row for group 1. Every retained query is mature. Shared clocks remain train-label cutoff Oct09 <= model availability Oct10 <= validation anchor Oct18.

| Prepared row position | Symbol | Query | Group | Product | y | Row weight |
|---:|---|---|---:|---:|---:|---:|
| train0 | T1 | q8u1 | 0 | 10 | 1 | 0.5 |
| train1 | T2 | q8u1 | 0 | 20 | 0 | 0.5 |
| train2 | T3 | q8u2 | 1 | 20 | 0 | 1 |
| selection0 | V3 | q18u5 | 0 | 20 | 0 | 1 |
| selection1 | V1 | q18u3 | 2 | 10 | 1 | 0.5 |
| selection2 | V2 | q18u3 | 2 | 20 | 0 | 0.5 |

Thus predicted train group/int32=[0,0,1], items/int64=[10,20,20], y/int8=[1,0,0], row_weights/float64=[0.5,0.5,1]. Predicted selection group/int32=[0,2,2], items/int64=[20,10,20], y/int8=[0,1,0], row_weights/float64=[1,0.5,0.5]. Selection weights [0.5,0.5,1] belong to symbolic V1,V2,V3 order, not the actual predicted prepared-row order.

## All 246 X coordinates

Each role's predicted X is 3x41, dtype float32, 492 numeric bytes. The table below displays their transposes: each feature row names an exact X column, and the three train/three selection columns are the ordered rows above. `NaN` denotes missing float32 data, not zero; no particular NaN payload bits are promised. Every finite integer is below 2^24 and 0.5 is binary exact, so all displayed finite values survive float32 conversion unchanged.

| X index, 1-based | Exact feature_names entry | Train T1 | Train T2 | Train T3 | Selection V3 | Selection V1 | Selection V2 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | from_popular | 0 | 1 | 1 | 0 | 0 | 0 |
| 2 | from_recent | 1 | 0 | 1 | 1 | 1 | 1 |
| 3 | popularity_distinct_users | 0 | 1 | 1 | 0 | 0 | 0 |
| 4 | popular_source_rank | NaN | 1 | 1 | NaN | NaN | NaN |
| 5 | recent_source_rank | 1 | NaN | 1 | 1 | 1 | 2 |
| 6 | candidate_category_ambiguous | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | candidate_category_missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | item_has_observed_history | 1 | 1 | 1 | 1 | 1 | 1 |
| 9 | user_has_observed_history | 1 | 1 | 1 | 1 | 1 | 1 |
| 10 | item_observed_age_seconds | 3600 | 1800 | 1800 | 865800 | 867600 | 865800 |
| 11 | user_observed_age_seconds | 3600 | 3600 | 1800 | 3600 | 3600 | 3600 |
| 12 | user_view_7d | 1 | 1 | 0 | 1 | 2 | 2 |
| 13 | user_cart_7d | 0 | 0 | 0 | 0 | 0 | 0 |
| 14 | user_purchase_7d | 0 | 0 | 1 | 0 | 0 | 0 |
| 15 | user_distinct_viewed_items_7d | 1 | 1 | 0 | 1 | 2 | 2 |
| 16 | pair_view_7d | 1 | 0 | 0 | 1 | 1 | 1 |
| 17 | pair_cart_7d | 0 | 0 | 0 | 0 | 0 | 0 |
| 18 | pair_purchase_7d | 0 | 0 | 1 | 0 | 0 | 0 |
| 19 | pair_view_recency_seconds | 3600 | NaN | NaN | 3600 | 3600 | 3600 |
| 20 | pair_purchase_recency_seconds | NaN | NaN | 1800 | NaN | NaN | NaN |
| 21 | item_view_24h | 1 | 0 | 0 | 2 | 1 | 2 |
| 22 | item_purchase_24h | 0 | 1 | 1 | 0 | 0 | 0 |
| 23 | item_distinct_viewers_7d | 1 | 0 | 0 | 2 | 1 | 2 |
| 24 | user_category_view_7d | 1 | 0 | 0 | 1 | 1 | 1 |
| 25 | user_category_view_recency_seconds | 3600 | NaN | NaN | 3600 | 3600 | 3600 |
| 26 | item_category_view_7d | 1 | 0 | 0 | 2 | 1 | 2 |
| 27 | category_view_7d | 1 | 0 | 0 | 2 | 1 | 2 |
| 28 | source_coverage_24h | 1 | 1 | 1 | 1 | 1 | 1 |
| 29 | source_coverage_168h | 1 | 1 | 1 | 1 | 1 | 1 |
| 30 | user_category_view_share_7d | 1 | 0 | NaN | 1 | 0.5 | 0.5 |
| 31 | item_category_view_share_7d | 1 | NaN | NaN | 1 | 1 | 1 |
| 32 | pair_view_recency_seconds_missing | 0 | 1 | 1 | 0 | 0 | 0 |
| 33 | pair_purchase_recency_seconds_missing | 1 | 1 | 0 | 1 | 1 | 1 |
| 34 | user_category_view_7d_missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 35 | user_category_view_share_7d_missing | 0 | 0 | 1 | 0 | 0 | 0 |
| 36 | user_category_view_recency_seconds_missing | 0 | 1 | 1 | 0 | 0 | 0 |
| 37 | item_category_view_7d_missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 38 | category_view_7d_missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 39 | item_category_view_share_7d_missing | 0 | 1 | 1 | 0 | 0 | 0 |
| 40 | retrieval_last_event_age_seconds | 3600 | NaN | 1800 | 3600 | 3600 | 3600 |
| 41 | retrieval_last_event_missing | 0 | 1 | 0 | 0 | 0 | 0 |

`numeric_feature_names` preserves the physical 45-column order after excluding query_id,user_id,product_id,anchor,candidate_category_id,last_user_event_time, then appends age/missing. Booleans cast to FLOAT as 0/1; SQL NULL numeric fields become float32 NaN through the masked-array conversion. Neither product IDs nor target labels enter X. The two retrieval fields are loader additions: for T2 the popular-only candidate has no last_user_event_time, so retrieval age remains NaN and missing=1 despite observed item history/age 1800. For T3, the strict-past purchase timestamp gives retrieval age 1800 and missing=0.

| Predicted matrix row | NaN X indices, 1-based |
|---|---|
| train0/T1 | {4,20} |
| train1/T2 | {5,19,20,25,31,40} |
| train2/T3 | {19,25,30,31} |
| selection0/V3 | {4,20} |
| selection1/V1 | {4,20} |
| selection2/V2 | {4,20} |

The eight core missing flags are nonmissing 0/1 coordinates 32..39. Retrieval missing is coordinate 41. Candidate metadata is known/unambiguous for every F row, so this oracle claims no missing/ambiguous-category coverage.

## Group accounting and full-Y metrics

| Expected accounting | Train, groups0..1 | Selection, groups0..2 |
|---|---|---|
| counts | [2,1] | [1,0,2] |
| candidate positives | [1,0] | [0,0,1] |
| candidate negatives | [1,1] | [1,0,1] |
| informative | [TRUE,FALSE] | [FALSE,FALSE,TRUE] |
| retained Q / candidate rows | 2 /3 | 3 /3 |
| nonempty / empty candidate groups | 2 /0 | 2 /1 |
| informative / all-negative / all-positive | 1 /1 /0 | 1 /1 /0 |
| positive-fullY Q / retrieved-positive rows | 1 /1 | 2 /1 |
| zero-gradient-pairwise groups | 1 | 2 |
| row-weight sum | 2 | 2 |

Weights are 1/candidate_count for each existing row. Empty-C q18u4 has no row or weight but remains a query with full Y={77}; empty-Y q18u5 retains its candidate and weight 1. A Logloss path would retain all 3 train rows. This oracle does not authorize a method or fit.

For a future prefix let r be product 10's rank among q18u3's two candidates after ordering(-raw_score,product_id); exact score ties place 10 before 20. With I=1+1/log2(3), define D=(1/log2(r+1))/I. The ideal denominator uses both full-Y items 10 and 99, even though 99 is absent from C. q18u4 contributes 0 to full-Y metrics despite an empty ranking. q18u5's individual empty-Y metric is undefined, excluded from the positive-only macro and assigned 0 by all-query-zero aggregation.

Therefore selection conditional macro NDCG@20=D/2 over positive-fullY queries q18u4,q18u3; all-query-zero macro NDCG@20=D/3 over all 3 Q. Recall@20 is 1/4 conditional and 1/6 all-query-zero. Full-Y products 77/99 remain targets. Train positive-only/all-query-zero denominators are 1 and 2 respectively. A positive-only selection projection contains 2 Q and 2 candidate rows; full-cohort save/reload parity must cover all 3 actual candidate rows plus q18u4's retained empty ranking.

No native scores, model rankings, nonflat curve, winning tree, Prepared object, native Pool/model, staged calculation or reload parity have been observed. These literal matrices, groups and metrics are manual expectations for a separately reviewed future <=8-tree test whose native grant remains unissued. Root owns any adoption/execution decision.

## Read trace

Physical F source: accepted export SHA 273a421bdfa13302c9dcd0c3c6bdc698e9d3b375e4dc7b5a7bbddd29390be37e, all 6 row arrays read. Loader source SHA bdab8bbe0ed4863dd9922e436c38699a0c69e0d2846289ab9f5a63b44c52412a: names 188-196, dataclass 198-205, preparation 208-271, accounting 274-293, rankings 323-340; read 1-420 as text. The prior manual-F SHA 57f5218f27f142dc6772cfe563f1bed7858806f8ef8661d1dbc004cf2107fb69 was read to preserve its disclosed chronology and compare all values. No future peer native proposal or generated Prepared result was read.
