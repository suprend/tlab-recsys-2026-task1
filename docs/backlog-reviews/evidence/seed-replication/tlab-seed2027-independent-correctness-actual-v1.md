# Independent ACTUAL seed2027 correctness review

**PASS within the authorized verification scope. The finite seed2027 criterion is FALSE.** Independently reconstructed selection data, native saved-model predictions, all2400 prefix metrics, earliest maxima, four estimands and persisted score/ranking parity agree with the completed producer. No correctness discrepancy was found. This negative development result does not establish final/generalization quality or justify selecting a third seed.

## Independently recomputed result

| Model | Selected trees | Conditional query NDCG@20 | Conditional query Recall@20 |
|---|---:|---:|---:|
| B41 | 98 | 0.45040127767495736 | 0.5919765166340509 |
| W44 | 134 | 0.43325580108319933 | 0.5489236790606653 |
| W−B | — | **−0.017145476591758024** | **−0.04305283757338563** |

Independent curves cover every prefix1…1200 for each full model. Maximum absolute difference from producer curves was2.22e−16 for B and1.11e−16 for W, below the frozen1e−12 tolerance. Earliest prefix within1e−12 of the global maximum is B98/W134. No patience/ceiling fallback was used in this verification.

| Estimand | B NDCG | W NDCG | B Recall | W Recall |
|---|---:|---:|---:|---:|
| Conditional query macro | .450401277675 | .433255801083 | .591976516634 | .548923679061 |
| All-query zero | .008219823318 | .007906918370 | .010803571429 | .010017857143 |
| Conditional user macro | .450401277675 | .433255801083 | .591976516634 | .548923679061 |
| All-user zero macro | .008230110956 | .007916814388 | .010817092795 | .010030395137 |

All four estimands' Recall, NDCG, AP and reciprocal rank plus population counts were recomputed by independent arithmetic and compared with producer values within1e−12; full precision and both curves are in `/tmp/tlab-seed2027-independent-actual/result.json`.

## What actually ran

A separate Source plan and independent source preflight preceded the single native attempt. A preflight-only metadata comparison was corrected before execution: the historical2026 verifier uses dictionary/anchor.isoformat query witnesses, whereas e62/current uses tuple/UTC-Z witnesses. The actual selection was checked against both formats. No failed native attempt or retry occurred.

One fresh supervised verifier ran in the existing Mac Python environment with two-thread settings, child CPU168/parent6, wait170wall, TERM2/KILL-reap3 and cooperative6GiB RSS. Original verifier tool session70123 completed exit0 (submit chunk a11563, terminal987671); child PID46090 was reaped with no primary/cleanup errors, signals or retries. Actual supervisor receipt reports4.705102wall seconds,6.030567child CPU seconds,0.036247parent CPU seconds and1,519,534,080bytes peak child RSS. The finite180CPU/180wall budget was comfortably respected. RSS checks remain cooperative rather than universal hard containment.

Exactly **0 fits,4 native model loads,4 direct full-selection predictions,2 positive-only staged streams and2400 dependent prefix checks** ran. These are independent review operations, separate from the original producer's6 full parity predictions/4,902,894 scores. The review added3,268,596 full-cohort direct score values and36,324,000 staged positive-row score values (15,135positive-query candidate rows×1200×2). No third seed or additional model fit/search was performed.

## Data, metadata and parity evidence

- The original terminal record `/tmp/tlab-root-seed2027-original-terminal-v1.json` and its pinned launcher receipt agree: session18199 original exit0, reaped, no errors/retries;2062.730529child CPU seconds,1073.310003wall seconds and5,968,969,728bytes peak RSS. This verifier did not attach to, replay or change that session. Its stdout/stderr are empty as recorded. The original saved request is byte-identical to the frozen request-v2 and matches the receipt's expected SHA.
- Authenticated accepted historical report SHA is `e62b1f47d6db808f6f5235f63a1b207970ac2f8487c09d9273902c4fbc864a9b`,52,763bytes. Only its exact Oct22/23 selection inventory was decoded:10 parquet files and2 manifests. Independent DuckDB selection-only SQL reconstructed Q/fullY/C and float32 B41/W44, without calling project preparation or metric functions.
- Reconstructed4000 mature unique Q,3995users,73positive fullY queries/users,96fullY targets,817,149candidate rows and15,135positive-query candidate rows. FullY includes off-C targets; every Q remains in evaluation, including empty target/candidate cases. C/base/extra key multisets were compared. Full identities (Q/fullY, group, items, labels, float32 X, B41 values/missing masks and feature order) exactly match e62 and seed2027 producer identities. The historical dictionary query witness and e62/current tuple witness both match reconstructed selection Q/fullY; historical array SHA/shape proofs also match. The retained identity-schema `max_copied_rows=4096` is original provenance metadata: this verifier hashed a whole selection B41 copy within its measured RSS, rather than claiming that original copy-size policy as its own execution behavior.
- Source/config closure hashes remain bound to the original request. Both arm recipes match the common frozen recipe with only seed2027/1200iterations changes; seals match. All four native saved models match producer byte witnesses, tree counts, ordered numeric feature schemas and complete effective parameter metadata. Model metadata representation allowances are the narrowly observed learning-rate/float32-serialized Bayesian values, not arbitrary tolerance.
- Each arm's persisted NPZ has exact group/item alignment. Full saved model at selected prefix and saved selected model each reproduce persisted scores with **maximum absolute difference0.0**, identical complete product-ID-tie-resolved ranking SHA and identical independently computed metrics. This checks persisted scores in addition to the original source-level RAM parity.
- All four produced train/selection identity dictionaries equal accepted e62 identities. All seed2026 array SHA/shape proofs, including training weights, agree with2027. **Training arrays were not decoded and training weights were not recovered from native models.** Train fullY/weight use and fresh-fit provenance are supported by authenticated report/source/receipt equality and inspected helper behavior, not independent native reconstruction of the training pool. Historical query witness serialization differs; old train Q hash was not falsely equated or recomputed without train bodies.
- Every consumed input was rehashed after native verification; all remained unchanged. Source-freeze hashes also remained unchanged. The complete original job contains7,912,461file bytes at postcheck. Canonical files and source inputs remained read-only.

## Comparison with the previous seed

| W−B NDCG@20 | Seed2026 | Seed2027 |
|---|---:|---:|
| Matched300 | +0.006092148943 | −0.012554918160 |
| Matched600 | +0.005039523805 | −0.010178199453 |
| Matched1200 | +0.008662984837 | −0.010178199453 |
| Separately selected prefixes | +0.005437964706 | −0.017145476592 |

Seed2026 selected B1189/W403; seed2027 selected B98/W134. Seed2026 selected Recall delta was+0.001956947162; seed2027 delta is−0.043052837573. Seed2026 JSON/curves were compared as accepted historical evidence, not replayed with extra native calls. The sign reversal is observed reused-development seed sensitivity for this fixed pair. Two seeds do not estimate a seed distribution or establish a robust positive effect. Matched-k diagnostics here concern NDCG, not a newly computed matched-k Recall curve.

## Review artifacts and boundaries

- Source, plan, counters, original verifier logs, receipt, full independent result and postcheck: `/tmp/tlab-seed2027-independent-actual/`.
- Fresh input/output/source byte pins: `/tmp/tlab-seed2027-independent-correctness-actual-v1-pins.json`.

A separate read-only helper independently reviewed source controls and historical metadata/arithmetic. Its initial direct-query-hash assumption was corrected during preflight using the actual old witness implementation; it executed no native operations. This coordinator verified actual worker exit, files and outputs rather than treating the helper's message as proof.

No raw database, train feature bodies or final25–31 inputs were opened; no Git/canonical changes, publication or messages to external parties occurred. The result remains historical d35cfb6 frozen-export replication with a fresh current consumer, not current raw-producer reproduction, CV or independent final quality evidence.
