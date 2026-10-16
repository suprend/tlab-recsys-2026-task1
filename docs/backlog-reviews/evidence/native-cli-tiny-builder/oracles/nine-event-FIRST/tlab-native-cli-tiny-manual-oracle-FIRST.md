# Independent FIRST manual oracle

Source-only; no imports, tests, SQL, native calls, data/model/score reads. Peer proposals unread. Supplied context: native-helper 8-tree PASS; ordinary-CLI E2E UNRUN. This pass: 0 grants, 0 queue IDs. Original deadline: 25 October 23:59, timezone unknown.

The existing five-event fixture cannot provide positive validation after the required positive fit gap. Nine literals below cover binary training, empty-C validation, and a separate informative validation group with an off-C target. No acceptance is claimed.

All clocks are October 2019 UTC. Retain clock-48h policy, seed2026, except daily cap2, popular3/recent3/max_unique6. Train range[08,09), label cutoff09; model available10; validation range[17,18), label cutoff18. Thus train-label cutoff09 < model-time10 ≤ validation-anchor17. Both phases: shard_days1, budget2Q/12pairs/60s; source[Oct01,Nov01), final_holdout_start26. Targets[anchor,anchor+24h).

|Time|Action|Item|User|Category|
|---|---|---:|---:|---:|
|07 18:00|view|10|1|100|
|07 20:00|purchase|20|2|200|
|08 00:00|purchase|10|1|100|
|16 12:00|view|NULL|3|NULL|
|16 18:00|view|10|4|100|
|16 20:00|view|20|4|NULL|
|17 00:00|purchase|99|3|300|
|17 00:00|purchase|10|4|100|
|17 00:00|purchase|99|4|300|

Use typed9 schema; category_code/brand/price/user_session NULL. Query IDs are SHA256(`query|2026|<ISO-anchor>|<user>`); both eligible users survive cap2.

|Q key|Full Y|C|Candidate y|
|---|---|---|---|
|T1:08/u1|{10}|{10,20}|1,0|
|T2:08/u2|{}|{20}|0|
|V3:17/u3|{99}|{}|none|
|V4:17/u4|{10,99}|{10,20}|1,0|

All Q mature. Train Q2/Y1/C=F3; weights T1=.5,.5;T2=1. Validation Q2/Y3/C=F2; positive-fullY queries2, empty-C1, informative1. Product99 is cold and never inserted into C.

Vectors follow the [manual18 registry](/Users/mdpospelov/tlab-recsys-2026/configs/features/manual-18.json) order; N=NULL. Missing flags equal the listed null indices.

|Row|18-vector|Null indices|
|---|---|---|
|T1/10|1,0,0,1,1,0,0,21600,N,1,0,1,1,1,21600,1,1,1|9|
|T1/20|1,0,0,1,0,0,0,N,N,0,1,0,0,0,N,0,0,N|8,9,15,18|
|T2/20|0,0,1,0,0,0,1,N,14400,0,1,0,0,N,N,0,0,N|8,14,15,18|
|V4/10|2,0,0,2,1,0,0,21600,N,1,0,1,1,.5,21600,1,1,1|9|
|V4/20|2,0,0,2,1,0,0,14400,N,1,0,1,N,N,N,N,N,N|9,13,14,15,16,17,18|

Both coverage fields=1; observed-history flags=true; ambiguity=false. Category missing only V4/20. Item/user ages: T1/10=21600/21600,T1/20=14400/21600,T2/20=14400/14400,V4/10=799200/21600,V4/20=792000/21600. Extra numeric nulls: popular_rank for T1/10 and both V4 rows; recent_rank/retrieval_age for T1/20. Retrieval-missing only T1/20; other retrieval ages match pair-view recency except T2/20=14400.

Future only: one native fit≤8trees, depth2, learning_rate.1,l2=3,seed7,query_cap2,row_cap3; ordinary limits remain6000Q/1320000rows. Independently rank each staged prefix with item-ID ties. With I=1+1/log2(3), macro full-Y NDCG@20 is1/(2I) when10ranksfirst, otherwise1/(2log2(3)I). Empty-C contributes0; denominator2. Choose earliest prefix within1e-12 of global maximum; flat is permitted. Require full-prefix/selected/reloaded score differences≤1e-12 and identical rankings.

Admission requires actual independent producer/plan review, Q/Y/C acceptance, F semantic review, then exact-scope collection acceptance; fixture helpers simulate approvals. Future shadow project: pinned producers/configs and artifacts under actual module ROOT, without ROOT monkeypatching. Never alter production importer for ingest_metadata. If adapting its events-only DB, preserve original hash/schema, derive a separate fixture DB with honest metadata, seal derived hash externally, and use that same derived source for both collections. No self-referential DB hash.
