# Actual F and collection semantic review v1

**No mismatch found in all six physical F rows: 108 registry values, 48 generated flags and every remaining key/context/retrieval cell.** Both 45-column schemas and both collection populations match the frozen disclosed ten-event manual oracle. This is review evidence; it issues no collection acceptance or execution grant.

The preproduction oracle remains historical and unchanged: [manual-F.md](/tmp/tlab-native-cli-ten-event-F-manual-oracle-v1/manual-F.md), SHA `57f5218f27f142dc6772cfe563f1bed7858806f8ef8661d1dbc004cf2107fb69`, frozen before F production for a disclosed fixture, not a blind ten-event FIRST. The original independent nine-event FIRST and its pins/freeze were also rehashed unchanged.

## Physical evidence and complete value comparison

Root's completed F export SHA is `273a421bdfa13302c9dcd0c3c6bdc698e9d3b375e4dc7b5a7bbddd29390be37e`. Its worker-result SHA `4c6d68f65548f6a2eb497943b7c464324ae9a2cdcce425637f431a09a6d34e19` matches the physical-production receipt. I independently hashed/statted the two exact F Parquets: train SHA `14b0b3588b9ef5ca62a4f2861ea90a7ec215ec1c530847f1fd929167150ef61f`,7506bytes,0644; selection SHA `7b568c0743a9efad2b611aa9b412ad79b4d5b08ad38c0f63dd75214c55a33979`,7435bytes,0644. Both have three exported physical rows.

All 270 physical cells were compared by query/product key, including NULL versus zero and BOOLEAN versus numeric types. Row labels follow the frozen manual: T1=q8u1/10,T2=q8u1/20,T3=q8u2/20,V1=q18u3/10,V2=q18u3/20,V3=q18u5/20. The export presents selection as V3,V1,V2; presentation order was not treated as group identity.

These **observed** 18-value vectors match the preproduction table in registry order. N=NULL.

| Row | Observed registry vector |
|---|---|
| T1 | 1,0,0,1,1,0,0,3600,N,1,0,1,1,1,3600,1,1,1 |
| T2 | 1,0,0,1,0,0,0,N,N,0,1,0,0,0,N,0,0,N |
| T3 | 0,0,1,0,0,0,1,N,1800,0,1,0,0,N,N,0,0,N |
| V1 | 2,0,0,2,1,0,0,3600,N,1,0,1,1,.5,3600,1,1,1 |
| V2 | 2,0,0,2,1,0,0,3600,N,2,0,2,1,.5,3600,2,2,1 |
| V3 | 1,0,0,1,1,0,0,3600,N,2,0,2,1,1,3600,2,2,1 |

All 48 generated `_missing` flags match. Their ordered fields are pair_view_recency_seconds, pair_purchase_recency_seconds, user_category_view_7d, user_category_view_share_7d, user_category_view_recency_seconds, item_category_view_7d, category_view_7d, item_category_view_share_7d, each with `_missing` appended. T1/V1/V2/V3 flag vectors are FALSE,TRUE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE; T2 is TRUE,TRUE,FALSE,FALSE,TRUE,FALSE,FALSE,TRUE; T3 is TRUE,FALSE,FALSE,TRUE,TRUE,FALSE,FALSE,TRUE.

| Row | Registry NULL indices | Physical F NULL column indices, 1-based |
|---|---|---|
| T1 | {9} | {6,26} |
| T2 | {8,9,15,18} | {7,8,25,26,31,37} |
| T3 | {8,14,15,18} | {25,31,36,37} |
| V1 | {9} | {6,26} |
| V2 | {9} | {6,26} |
| V3 | {9} | {6,26} |

Train producer missing counters are pair-view-recency2, pair-purchase-recency2, user-category-share1, user-category-recency2, item-category-share2 and all other core counters0. Selection has pair-purchase-recency3 and all other core counters0. These report counters equal the exported cells and the preproduction expectations.

| Row | Category ID | Item age seconds | User age seconds |
|---|---:|---:|---:|
| T1 | 10 | 3600 | 3600 |
| T2 | 20 | 1800 | 3600 |
| T3 | 20 | 1800 | 1800 |
| V1 | 10 | 867600 | 3600 |
| V2 | 20 | 865800 | 3600 |
| V3 | 20 | 865800 | 3600 |

All six candidate_category_ambiguous/missing fields are FALSE; item/user observed-history flags are TRUE; both source-coverage fields are1.0. Selection product20 has two historical views from users3/5, yielding counts2 and item/category shares1. Its latest two metadata rows agree on category20. Observed ages retain old first sightings outside the count lookback. Future purchases do not enter F. Undefined0/0 shares and absent recencies stay NULL, while known-key empty counts stay0.

Every original eight-column retrieval tuple is unchanged from the previously reviewed C rows, including T2's NULL recent rank/time, user2's popular/recent overlap, and user3's same-time recent ranks1/2. User/anchor fields match Q, and exact unique F keys equal exact C keys. Products99/77 are absent from F; empty-C user4 has no dummy row. Empty-Y user5 retains its real product20 feature row.

Both physical schemas have the same ordered45 names as their producer reports and aggregate feature_columns. No label_is_mature, y or derived retrieval-age column is in F. Using V=VARCHAR,I=BIGINT,B=BOOLEAN,T=TIMESTAMP,D=DOUBLE, the complete physical type vector is V,I,B,B,I,I,I,T,I,T,I,B,B,B,B,D,D,I,I,I,I,I,I,I,D,D,I,I,I,I,D,I,I,D,D,D,D,B,B,B,B,B,B,B,B. All 90 name/type entries across both exports match the formula declarations.

## Genuine shard lineage and aggregation

| Role | Collection ID | New F run ID |
|---|---|---|
| train | 48d6e5aad4fca88bf9c97d76979f09850ce6e3b17d50f708ed7712ef63555600 | 6dfda9cbe17c0d6502607d2bd89a5ba4879e3fcca11b4a667c6767d6bd658178 |
| selection | 7ebe0fe9085155d1e10830a41345e283432e4b3689d2282ce8ce7b3491f76885 | b22c06679c6001d814e412a89a2e6f157d35a912769885d34890545803719f66 |

Both F run IDs independently rehash from sorted compact JSON identity. Manifest/report/state IDs, output hashes and references agree; F refs are exactly{features,report} in the immutable F directory. Both code maps contain exactly the eight FEATURE_CODE pins, matching copied files and accepted producer bundle. Q/Y/C seals and their sixteen physical output/manifest/report hashes remain equal to the prior review. Plan hashes and model timing remain unchanged.

Each genuine Root shard approval has the exact five-field approval schema, approved=TRUE, matching anchor/candidate IDs and14 fingerprint entries. All14 entries were compared to the prior Q/Y/C closure and new F input map. The13 non-DB pins per approval were independently physically rehashed; the source DB pin is inherited from Root's accepted unchanged synthetic-source binding, without DB access here. The genuine approval hashes are train `9c97de173d934da4a11b14285939bb1012d0c7d1be6b98d6b40cb178186a68eb` and selection `8bbe49cb3dbee14ec96b7ddd2b0a44aee1028ed092eb7928921568d899219684`, matching state and F inputs; sizes3299/3331 and mode0600 match Root's inventory.

Each F manifest has exactly17 input pins: the14 accepted Q/Y/C entries plus exact shard approval, manual18 registry and label-independent full-selection specification. Selected-query max_queries=NULL; source candidate IDs match; reports selected_queries=2/3 and accepted_fingerprint_count=14. Registry and both selection-spec file hashes were checked physically. Reports show complete F, three feature rows,18core features, and daily pairs3/items2/users2 or3, including the empty-C query in the selection user population.

Both states now have two attempts, preserve original anchor/candidate attempts, add one F attempt/seal and are `complete_produced_unreviewed`. Aggregate reports contain one exact shard/day, refs equal the accepted Q/Y/C plus new F manifests, the full45-column schema and counts train Q2/Y1/C3/F3; selection Q3/Y3/C3/F3. The previously reviewed full target sets remain{10}, {}, {10,99}, {77}, {}. Empty C and empty Y therefore remain in the full query population; no target was inserted, dropped or converted to a feature. Model timing is train-label cutoff Oct09 < availability Oct10 ≤ selection anchor Oct18, selection-label cutoff Oct19 < final holdout Oct26.

## Boundary of the result

Actual physical F and collection relations now support the above semantic finding. **Prepared3×41 float32 X, derived retrieval-age/missing, native weights, staged scores/curve, selected tree and save/reload parity remain unproduced/unverified here.** Their earlier tables/formulas remain predictions. No source DB was independently scanned; its literal ten-event content is inherited from Root's accepted fixture. This disclosed fixture does not cover ambiguous/missing candidate categories, sampling truncation or exact target endpoints.

Only JSON/text reads, metadata/stat and hashes were used. No SQL, DB engine, Parquet body import, test, application/executable helper, feature producer, verifier, ML, fit, inference, approval, canonical/Git/network write or goal tool was used. Root alone owns genuine collection acceptance and any later read-only verifier. No native grant was consumed and no production-quality claim is made.
