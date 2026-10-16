# Wave060 — independent skeptic

Reviewed 2026-10-16 05:38:52 UTC, after Root's 05:34:23 three-FIRST readback. **Disposition: accept A's bounded audit; retain B with an interpretation amendment; accept C's analytical one-anchor witness with explicit fixture preconditions.** Zero new IDs, mandatory gates or grants. Root alone adopts. Exact read scopes, versions, hashes and freshness checks accompany this note.

**A — bounded acceptance.** The frozen compiler's lines 114–143 enforce declared counts/distincts/observed recencies and the upper-exclusive cutoff; lines 175–228 implement latest-global-past category resolution, coverage, shares and missingness; lines 242–244 check candidate identity. The generator's lines 135–148 reject declared B/retrieval signatures and enforce three physical additions. These support A's local statements, not exhaustive downstream lineage or semantic correctness. The caller checks schemas, invokes the helper once, persists and verifies selected/reloaded scores and rankings (train_development:163–221). Its cap is ≤6000 Q (62–66), whereas historical B used 26000 (experimental-report:31,61). Reusing parameters is not reproducing that control. The newer Root receipt establishes only the consumed eight-tree toy normal path; historical native-UNRUN prose in progress/development docs is stale for that scope. Ordinary CLI E2E and native callback-abort remain UNRUN. SELF/cooperative limits do not establish hard whole-tree containment.

**B — useful deferred sentinel, not calibration.** Four prospective fits and all prefix/arm looks must be charged; training support, full Y/off-C/zero-Y, weights and train population must match. Two noise seeds cannot estimate optimism frequency, produce a calibrated p-value, or validate historical adaptive search. Add this precise interpretation: the proposed development-positive/reserve-nonpositive pattern is *consistent with* selection optimism; it does not isolate optimism from altered optimization or regularization caused by unmatched noise geometry. Before any future allocation, specify noise law/scale, numeric representation, RNG assignment and label-reserved reporting population. Randomization itself being cheap does not make fits or reserve access free. Dates 25–31 are already opened and cannot become fresh confirmation.

[Boruta's publisher abstract](https://www.jstatsoft.org/article/view/v036i11) describes Random-Forest classification relevance against random probes, providing motivation only. The authors' [Model-X modeling](https://web.stanford.edu/group/candes/knockoffs/modeling.html) and [outline](https://web.stanford.edu/group/candes/knockoffs/outline.html) require iid observations/known covariate law, swap exchangeability, response conditional independence and fair statistics. None is established for these repeated-user temporal candidate rows or independently injected noise; no knockoff/FDR guarantee transfers.

**C — all 41 coordinates checked analytically.** Define A as 162 zeros followed by (1,0,1,1,0,1), B as 162 zeros followed by (1,1,1,0,0,1), with views at occupied hourly-bin midpoints. Use nonnull fixed u/i/c and a legal UTC-midnight T within the declared pilot range, with T−168h≥source_start and source_end≥T. This makes the implicit compiler preconditions explicit; for example T=2019-10-08T00:00Z satisfies clock48h. Fix nonnull query metadata. Both four-view histories have first/last times T−5.5h/T−0.5h; all views lie inside both 24h/168h windows. The actual manual18 registry, compiler:114–228, model schema:19–65 and loader:188–195,249–262 give:

| Coordinates | Same value in A/B |
|---|---|
| from_popular, from_recent, popularity_distinct_users, popular_source_rank, recent_source_rank | false,true,0,NULL,1 |
| candidate_category_ambiguous, candidate_category_missing, item_has_observed_history, user_has_observed_history | false,false,true,true |
| item_observed_age_seconds, user_observed_age_seconds |19800,19800|
| user_view_7d, pair_view_7d, item_view_24h, user_category_view_7d, item_category_view_7d, category_view_7d |4 each|
| user_cart_7d, user_purchase_7d, pair_cart_7d, pair_purchase_7d, item_purchase_24h |0 each|
| user_distinct_viewed_items_7d, item_distinct_viewers_7d |1 each|
| pair_view_recency_seconds, user_category_view_recency_seconds |1800 each|
| pair_purchase_recency_seconds |NULL|
| source_coverage_24h, source_coverage_168h; both category-view shares |1 each|
| pair_view_recency_seconds_missing; pair_purchase_recency_seconds_missing |false;true|
| user_category_view_7d_missing, user_category_view_share_7d_missing, user_category_view_recency_seconds_missing, item_category_view_7d_missing, category_view_7d_missing, item_category_view_share_7d_missing |false each|
| retrieval_last_event_age_seconds, retrieval_last_event_missing |1800,false|

Candidate source:38–107 and clock48h:35–49 give C={i}: recent rank 1, no popular candidates, purchase popularity 0, popular rank NULL. Category c is unchanged at the unique last timestamp. NULL recency becomes NaN with matching missingness, preserving model-vector equality.

All eight typed bundles also agree (feature_programs:110–146): L01 user 24h/L02 pair 24h/L03 item 168h action counts=(4,0,0); L04 user distinct(view 24h,cart 168h,purchase 168h)=(1,0,0); L05 item distinct(view 24h,cart 168h,purchase 24h)=(1,0,0). L06 pair/L07 user/L08 item observed-cart recencies are NULL with true missing flags; companions respectively item-cart count 24h, user-purchase distinct 24h and item-cart distinct 24h are 0. Thus W44 agrees too.

For [tagged tsfresh v0.21.2](https://raw.githubusercontent.com/blue-yonder/tsfresh/v0.21.2/tsfresh/feature_extraction/feature_calculators.py), lines 752–776 use strict mean-relative runs, 1140–1174 strict interior peaks, 1769–1807 whole-series centering and variance. Hand derivation gives:

| Scalar | A | B |
|---|---:|---:|
| peaks n1 / n2 |1 /0|0 /0|
| above / below mean run |2 /162|3 /162|
| autocorrelation lag1 |1637/6847|3401/6847|
| autocorrelation lag2 |3400/6806|1636/6806|

Here n=168, mean=1/42, variance=41/1764. Lag 1 raw products are 1/2; lag 2 are 2/1; truncated endpoint sums total 7 in each case. The centered numerator is P−7/42+(168−lag)/1764. Therefore four scalars and the vector are not deterministic functions of this B41/support representation. The other two scalars' nonaliasing, multi-anchor matrix parity, native implementation semantics and predictive utility remain unproved. No canary was run.

**Unchanged disposition.** Deduplicate into 014/016/019/013 and FB-05. Future utility must declare incumbent/contrast, Recall comparator/threshold/stage and complete physical closure: six cores plus masks exceed old 016's three-column arm. All experiments remain UNRUN/deferred; scientific allocations CLOSED, historical 6CPUh remainder UNKNOWN, sole 50CPU/65wall allowance consumed/CLOSED. Original 25Oct23:59 deadline/timezone uncertainty and next original 06:00UTC remain unchanged. No imports/tests/ML/Git/data access, peer contact, helpers, canonical or network writes occurred.
