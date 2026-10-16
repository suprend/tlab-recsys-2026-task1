# Actual tiny Q/Y/C semantic review v1

**Result: no semantic mismatch found in all eight physically bound Q/Y/C/coverage exports.** This is an independent review finding for these synthetic outputs, not a shard acceptance, collection acceptance, native grant, F result or CLI fit result. Root alone owns acceptance artifacts.

The physical export was read only after Root reported its completed export. Its SHA is `84e15f26619cc386537d254d7a867eec047ba17bd26bf49817ba9ada6d212bce`; its worker-result SHA is `068395eed0e8ef5c643c7b39ea5e545b6e01fe2e264f2073e64a1880ae5311fa`, matching the production receipt. I independently hashed and statted all eight source Parquets: each SHA/bytes/mode matches both the export and worker inventory. All are0644. I read JSON/text, inspected metadata and used SHA tools only; no DuckDB/source DB, SQL, application import, test, helper, F producer, verifier, model or inference was run.

## Identities and physical lineage

| Role | Collection ID | Anchor run ID | Candidate run ID |
|---|---|---|---|
| train | 48d6e5aad4fca88bf9c97d76979f09850ce6e3b17d50f708ed7712ef63555600 | 3080f06d922ef329b2fe372529b36a257d02b7270d436e6dcd257b5d42b13011 | d795c4ad5f7bff3decafa3d6bfe614311af7442d0d8c51180e5c019d2702a895 |
| selection | 7ebe0fe9085155d1e10830a41345e283432e4b3689d2282ce8ce7b3491f76885 | fdaa72c907c2898686922a7588a10eb3758e70bb89256467f3b339214c1a5c97 | 3ef5f715130c0d3c0481a779ffaeb49e19500fed1df9c4de0bd218e914773f19 |

Each ID was independently reproduced by hashing sorted compact JSON identity, without production helpers. Physical plan/state/manifest/report hashes match the worker's original inventory. State, directory, manifest and report IDs agree. Both states are `waiting_for_shard_review`, one exact shard each, containing anchor/candidate seals and no acceptance/features entry.

Anchor manifests have exactly the four mandatory code pins and one source input, `data/tiny-cli.duckdb`, SHA `49d5db82fcdf10a94097f612450419e2b573570c50db57d03a0efb8d71b12b49`. Candidate manifests have exactly the five mandatory code pins and source plus the exact upstream anchor run/report/Q/Y hashes. Artifact-ref sets are anchor={queries,labels,report}, candidate={candidates,query_coverage,report}; all point into their own immutable run directories. All four reports are complete with matching IDs. Copied code/lock/config hashes also match the accepted plan bundle.

Actual base/phase bodies match the disclosed ten-event calendar and caps. Train labels mature at Oct09 00:00; model availability Oct10 00:00 precedes selection anchor Oct18 00:00. Selection labels mature at Oct19 00:00. Both phases precede final holdout Oct26. The recorded typed9 source schema is TIMESTAMP,VARCHAR,BIGINT,BIGINT,VARCHAR,VARCHAR,DECIMAL(12,2),BIGINT,VARCHAR in the disclosed field order. Both anchor reports preserve ingest note `direct synthetic CLI fixture; no archive import`.

## Every Q, Y and C row

The five actual query IDs equal independently hashed literal `query|2026|<ISO-anchor>|<user>` strings. Full IDs are recorded in pins.json. Symbolic names below match the frozen ten-event manual oracle. All Q are unique mature user-days at UTC midnight; history_active_days_7d=1 and history_coverage_7d=1.0 throughout.

| Q | User | Anchor | Eligibility | History rows | Distinct items | Last history UTC | Observed full Y | Observed C |
|---|---:|---|---:|---:|---:|---|---|---|
| q8u1 | 1 | Oct08 00:00 | 1 | 1 | 1 | Oct07 23:00 | {10} | {10,20} |
| q8u2 | 2 | Oct08 00:00 | 1 | 1 | 1 | Oct07 23:30 | {} | {20} |
| q18u3 | 3 | Oct18 00:00 | 2 | 2 | 2 | Oct17 23:00 | {10,99} | {10,20} |
| q18u4 | 4 | Oct18 00:00 | 1 | 1 | 0 | Oct17 23:00 | {77} | {} |
| q18u5 | 5 | Oct18 00:00 | 1 | 1 | 1 | Oct17 23:00 | {} | {20} |

All four Y pairs are unique and refer to existing Q. Each raw_purchase_rows=1 and same_second_purchase=FALSE. Their first_purchase_time / catalog_seen_before / pair_seen_before are: q8u1/10 Oct08 00:10 TRUE/TRUE; q18u3/10 Oct18 00:10 TRUE/TRUE; q18u3/99 Oct18 00:20 FALSE/FALSE; q18u4/77 Oct18 00:30 FALSE/FALSE. No missing target is inserted into C.

| C pair | Popular | Recent | Popularity users | Popular rank | Recent rank | Last user event UTC |
|---|---|---|---:|---:|---:|---|
| q8u1/10 | FALSE | TRUE | 0 | NULL | 1 | Oct07 23:00 |
| q8u1/20 | TRUE | FALSE | 1 | 1 | NULL | NULL |
| q8u2/20 | TRUE | TRUE | 1 | 1 | 1 | Oct07 23:30 |
| q18u3/10 | FALSE | TRUE | 0 | NULL | 1 | Oct17 23:00 |
| q18u3/20 | FALSE | TRUE | 0 | NULL | 2 | Oct17 23:00 |
| q18u5/20 | FALSE | TRUE | 0 | NULL | 1 | Oct17 23:00 |

All six C pairs are unique, nonnull product keys, existing-Q joins and strict-past observed products. Train popular20/recent20 overlap is one deduplicated row for user2. User3's same-time recent tie resolves10 then20. Selection global popularity is empty: Oct07/08 purchases fall before the Oct11 lookback start. Null-product view retains user4's eligibility/history row while yielding neither recent item nor candidate. Future purchases affect only Y, not Q eligibility or C.

## Exact schemas and coverage values

Column order and types match the pinned source definitions for both phases: Q has10 columns, Y7, C8, coverage17. Q types are VARCHAR,BIGINT,TIMESTAMP,BIGINT,BIGINT,BIGINT,BIGINT,TIMESTAMP,DOUBLE,BOOLEAN. Y types are VARCHAR,BIGINT,TIMESTAMP,BIGINT,BOOLEAN,BOOLEAN,BOOLEAN. C types are VARCHAR,BIGINT,BOOLEAN,BOOLEAN,BIGINT,BIGINT,BIGINT,TIMESTAMP. Coverage starts VARCHAR,BIGINT,TIMESTAMP,BOOLEAN and then thirteen BIGINT counts. Every exported scalar, boolean, timestamp and NULL was compared; physical TIMESTAMP strings lack a timezone suffix as expected for naive UTC wall clocks.

Coverage vectors below list candidate_count,popular_count,recent_count,overlap_count,target_count,catalog_targets,retrieved_targets,popular_targets,recent_targets,repeat_targets,retrieved_repeat_targets,new_pair_targets,retrieved_new_pair_targets, in that exact order. Their query/user/anchor/maturity keys equal Q. N=NULL.

| Q | Observed and independently derived coverage vector |
|---|---|
| q8u1 | 2,1,1,0,1,1,1,0,1,1,1,0,0 |
| q8u2 | 1,1,1,1,0,0,0,N,N,N,N,N,N |
| q18u3 | 2,0,2,0,2,1,1,0,1,1,1,1,0 |
| q18u4 | 0,0,0,0,1,0,0,0,0,0,0,1,0 |
| q18u5 | 1,0,1,0,0,0,0,N,N,N,N,N,N |

For empty Y, target/catalog/retrieved totals coalesce to0 while the six optional outcome breakdowns remain NULL because no outcome row exists. This is correct, not an incomplete label. Empty-C positive user4 has a real outcome row: target1/new-pair1, other outcome counts0. Reports' source-state/daily aggregates match these rows: train popular keys/items1, recent pairs2, Q2/Y1/C3/coverage2, overlap1, candidate recall1; selection popular keys/items0, recent pairs3, Q3/Y3/C3/coverage3, overlap0, empty-C1, candidate recall0.25. No orphan, duplicate, target censoring or missing query is observed.

Selection positive-fullY denominator remains2, including user4's empty ranking; all-query-zero denominator remains3, including user5's empty Y. Retrieved target10 is one of user3's TWO full targets. Off-C targets99/77 remain in the target/ideal-DCG populations. All six expected future F keys agree with the frozen preproduction manual-F oracle, but no actual F/prepared matrix has been produced or examined here.

## Gate and limits of this review

I read the actual producer and shard gate source. Producer approval has exact fields version,approved,scope,collection_id,fingerprints; scope must be `reviewed_producers_and_phase_plan`. A genuine future Q/Y/C shard approval has exact fields version,approved,candidate_run_id,anchor_run_id,fingerprints, with approved=TRUE and actual content pins. It is never inferred from paths/current hashes. This Markdown, pins and freeze are review evidence only, not that approval format. No acceptance file was written and no gate was executed.

The source DB contents were not independently opened/re-exported here: source construction/unchanged DB binding is inherited from Root's accepted literal synthetic fixture and production receipt. I independently verified the eight physical Q/Y/C/coverage file hashes and all their exported rows. This fixture exercises overlap deduplication, a recent timestamp tie, positive off-C and empty-C queries, and empty Y; it does not exercise sampling truncation, exact target endpoints or ambiguous/missing candidate categories. The original nine-event FIRST was hash-verified unchanged. No native grant was consumed and no quality/production-coverage claim follows.
