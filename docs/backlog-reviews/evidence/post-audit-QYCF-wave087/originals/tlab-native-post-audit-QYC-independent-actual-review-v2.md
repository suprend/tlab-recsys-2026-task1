# Independent Q/Y/C actual review V2 — PASS for this synthetic case

One separately authorized DuckDB 1.5.6 inspection process read all eight SHA-bound Parquet files and compared every column, SQL type and all 20 physical rows against gold independently derived from ten builder literals before the earlier PyArrow attempt. Every schema and row comparison passed. V1 remains immutable INCOMPLETE history (PyArrow absent, zero files decoded); V2 is a new allowance, not an automatic retry.

| Role | Q | Full Y | C | Coverage rows |
|---|---:|---:|---:|---:|
| train | 2 | 1 | 3 | 2 |
| selection | 3 | 3 | 3 | 3 |

Train Q users1/2 and selection Q users3/4/5 match eligibility `[t−48h,t)`. History diagnostics match all raw events within `[t−168h,t)`: counts1,1,2,1,1; distinct-items1,1,2,0,1; one active day, coverage1.0 and mature=true throughout. User4’s NULL-product event preserves its query and event count. Query hashes exactly match the source’s fixed ASCII serialization.

Full Y `[t,t+24h)` contains train(1,10) and selection(3,10),(3,99),(4,77), each raw_purchase_rows=1 and same_second_purchase=false. Targets10 have strict-past catalog/pair flags true; 99/77 have both false. The complete target horizons end at the role availability cutoffs 10-09/10-19 and are mature. Targets99/77 remain outside C. User4 has positive Y and empty C, with coverage candidate_count=0,target_count=1,retrieved_targets=0.

All C fields match past-only retrieval: train(1,10) recent, (1,20) popular, (2,20) both; selection(3,10),(3,20),(5,20) recent only. Distinct-buyer counts, nullable source ranks/timestamps, overlap deduplication and the recent tie ordering10 before20 match. Selection popularity is empty because early purchases fall outside seven days. No target was injected into C.

All coverage fields were exhaustively checked, including source counts, retrieved/catalog/repeat/new-pair targets and zero denominators. Train user2 and selection user5 retain zero first-three target counts with NULL final-six diagnostics; these differ correctly from user4’s positive unretrieved target. Actual schemas have VARCHAR query IDs, BIGINT keys/counts/ranks, TIMESTAMP instants, DOUBLE history coverage and BOOLEAN flags in exact contract order. Physical Parquet nullability metadata was not separately inspected.

Connection settings succeeded in order: threads1, memory_limit64MB, max_temp_directory_size0B, EXACT8 allowed_paths, enable_external_access=false, lock_configuration=true. Only eight parameterized SELECTs against those paths followed. Connection was in-memory and closed; source DB was only hashed, never opened by an engine. RLIMIT_CPU8/alarm10 were active; direct tool chunk696f51 exited0. Observed process prefixes were CPU0.261089s and elapsed0.272484708s; these are not claimed as exact final whole-process costs. No project/ML import, network, persistent DB, data write or WAL occurred.

All82 input SHA/bytes/modes and file set match before/after; all30 original inputs, including both genuine producer approvals, remain preserved. Independent static metadata review recomputed both collection and four run IDs, checked exact protocol/source/code/parent/artifact bindings, and confirmed both one-shard/one-attempt states remain waiting_for_shard_review with one pending item each. No F or shard acceptance exists. Root’s execution receipt and V1 provenance checks are pinned.

This is a practical exhaustive review of the finite synthetic case. It does not establish general leak-freedom or exercise duplicate purchases, exact-boundary events or sampling overflow. No approval or execution authority is granted; Root remains sole issuer. A report-authoring JavaScript syntax error occurred before command dispatch and was corrected without repeating inspection. Freeze/readback complete; stopped.
