# Wave097 A FIRST — exact category ranking before query fanout

First actual clock observation: **2026-10-17 08:44:15 UTC**, not a claimed process-start time. Scheduled due **09:00 UTC**; next **09:45 UTC**, unchanged 45-minute grid. Independent before reading any peer097 author/critic notes. Root is sole coordinator, canonical editor and Git publisher. Research-campaign/research applied; one internal read-only source reader also reviewed the toy test.

Task1 requires experimentally checked feature automation/alternative methods against a strong boosting control ([requirements](/Users/mdpospelov/tlab-recsys-2026/docs/task1-requirements.md)). Current actual category pilot remains Root-owned and its scientific result **UNKNOWN to this author**. Dispatch source `category_candidate_pilot.py` SHA **bcee5e0a071d7ea70a4a214171bf088705ae9de25e1847032eda23226d1eebe0** was observed unchanged. Final B .459825/W .464947 with CI crossing zero remains historical; seed2027 caller is SOURCE-PASS/unlaunched per dispatch. No running code changed.

## One refinement, no new ID

**HYP-046 × HYP-053, TLAB-004/016: materialize category top20 before query fanout.** Existing HYP-046 already covers exact shared execution; rounds002/033/073 and wave031 cover DAG/materialization identity, paid sinks and strong batched005 controls. This is a concrete candidate-retrieval execution refinement, not a new quality mechanism or another mandatory gate.

**Observed source/mechanism.** [Current source lines147–155](/Users/mdpospelov/tlab-recsys-2026/scripts/category_candidate_pilot.py:147) joins each selected query category to its whole membership and applies `row_number` per `(query_id,category_rank)` before cap20. Ranking keys are only `coalesce(buyers,0) DESC,product_id ASC`; for a fixed `(anchor,category)` they are query invariant. Under current unique Q/profile/membership/popularity keys, compute top20 once for each selected `(anchor,category)`, then join to query profiles preserving source rank, K1–K3 and priority. Keep full strict-past U membership and unknown/ambiguous bucket handling unchanged; this is not a candidate-restricted resolver.

**Counterhypothesis.** Raw-history/bucket work, Python insertion/bootstrap, sealing or hashing dominates total cost; shared top20 saves little overall or adds materialization overhead. Small category reuse could erase its advantage. Future query-specific exclusion/scoring would invalidate this factoring.

**Prediction.** The same six source columns are equal as a keyed multiset; complete round-robin positions/lists must subsequently remain exact. Pre-ranking logical cardinality changes from repeated category memberships across queries to memberships of distinct selected categories. Physical scanning and whole-run speed remain unknown. DuckDB1.5 [documents window buffering](https://duckdb.org/docs/current/sql/functions/window_functions); that motivates measurement, not a promised plan/speedup.

## Executed nearest primitive test

One permitted synthetic-only benchmark, existing venv, DuckDB **1.5.6**, Python3.12.14; no events/DB/Parquet/labels/models or actual report payloads read. Its post-import UTC observation was **08:46:24.323290**, finish observation08:46:24.483644. 600 Q,1641 profiles,30 categories,5808 membership rows; ties, absent/NULL buyers, thin category, absent profiles, NULL category and SQL BIGINTs at/above2^60. Predeclared AB/BA, no warmup/retry; B pays top20 build plus complete materialized consumer each time.

**Observed:** all four sinks32105 rows; bidirectional `EXCEPT ALL` differences **0**. A wall55.50/56.53ms, B5.49/5.43ms. Logical pre-ranking inputs317585 versus5807, **not engine rows-scanned**. Pre-final-JSON CPU .225799s / active wall .219959s; RSS96,649,216B. RLIMIT_CPU15s remains through exit; 25s alarm covered computation and close, cancelled before tiny JSON finalization; command returned EXIT0 within its first1s yield. DuckDB cap256MiB/1thread/0spill/0fits. Timings do not extrapolate to full scans/pilot throughput or quality. One outer note-writing SyntaxError occurred before benchmark creation/execution and was corrected; benchmark itself ran once.

Independent read-only review accepted algebra under stated invariants and this fixture's multiset equality; it identified untested multi-anchor, completely empty relations, malformed duplicates, downstream order/seals and Python transport. No production correctness claim follows from the toy equality alone.

## Decision and next bounded test

First inspect Root's already-paid stage evidence after the running pilot finishes. If category ranking is immaterial, defer. Do not optimize SQL/Python boundary on assumption: lines158–174 fetch/interleave/`executemany` lack separate stage attribution; whole-run accounting must include those and sealing/hash/bootstrap.

Prospective test, **not executed/granted here**: ≤45CPU/60wall/256MiB,1thread,0spill/0fits, synthetic only. Compare unchanged and factored implementations through existing14 canaries plus two-anchor changed-popularity, empty selection/membership and >20 boundary ties; require exact types/keys/source ranks and complete C0/C1/matched lists/positions. Any mismatch rejects rewrite. Only after equality, use balanced AB/BA with full paid sinks; ≥20% CPU reduction at ≤1.2×RSS is an optional HYP-046 screening rule, not a new goal. Otherwise reject/defer efficiency claim. Any actual source comparison needs Root ownership and its own finite budget; [profiling executes queries](https://duckdb.org/docs/current/dev/profiling), so no free EXPLAIN-ANALYZE scan.

Task1 benefit: a measured, semantics-preserving execution primitive can make automatic candidate/feature materialization more practical. It establishes neither recommendation-quality gain nor superiority of automated search. NEW0 / REFINE1 proposed; no scientific admission.
