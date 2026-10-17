# Test/evidence coverage — blind FIRST

Frozen HEAD `c538de4097322715fccac494e2b2becc3279e8e1`; manifest SHA256 `7e2e871f148beac5b9fce3aa23970b370db0c8fdc9eac89958fb6342a4d2a41a`. Original paths below are relative to `/Users/mdpospelov/tlab-recsys-2026/`.

## Scope and findings

Static inventory covers all **79 test files: 57 unittest modules, 881 declared test methods, 16 oracle modules, 6 fixtures**. AST names/decorators/imports and hashes were inspected across Python files; this is not semantic review of every body. Targeted bodies/callers include source import, temporal/query/candidate generation, manual/program features, matrix loaders, development CLI/helper/selector, heldout source/prediction/metric oracles; exact modes/paths are in pins. Frozen instructions, README, development guides and backlog/index were inspected for contracts/status. No moving checkout or other FIRST reports read.

**Confirmed actionable P0–P3 defects: none established in this coverage audit.** Missing execution/independent coverage is not promoted to a production defect. An apparent missing `ROOT` patch cleanup in `test_model_data.py:21` was rejected after tracing nested `fixture.doCleanups` (`:19`) to `TrainingDataTests`’ registered `patch.stopall` (`test_train_baselines.py:156`).

## Compact coverage matrix

“Present” means executable assertions exist in source, not PASS in this audit.

| Critical invariant | Present discriminating coverage | Boundary |
|---|---|---|
| Typed9, exact bigint/Decimal/NULL/raw bag | `test_source_import.py:32–41` literal rows/schema; malformed header, CRC, truncation and range faults | Invented ≤4-row streams; not October incidence |
| Strict `<t`, endpoint/maturity and query sampling | `test_temporal_contract.py:114,140`; `test_anchor_pilot.py` separate oracle, label perturbation and peer tests | Calendar/source completeness is a fixture premise |
| Label-blind popular/recent/no-refill C | `test_candidate_pilot.py:57–109` direct list oracle and future suffix; `test_candidate_reachability.py:39–107` actual parser→Q→C | Reachability directly calls parser; no complete importer/F/trainer |
| B18 arithmetic/NULL/category peers | `test_manual_features.py:107–170` **literal all18 + separately checked Python oracle**; `:172,183,252` full-row, SQL and suffix checks | Strong synthetic semantics; not exhaustive real rows |
| Selected12, masks/empty typed F | `test_feature_programs.py:125–183` literal gold + row oracle, typed delta, peer/suffix/empty checks | Selected columns, not arbitrary future programs |
| B41/W44 keys/order/fullY/float32 | `test_model_data.py:48`; `test_program_model_data.py:48`; `test_reproduce_frozen_comparison.py:100–125`; heldout prediction literal matrix test `:47–53` | Historical-loader equality shares an implementation baseline; independent literals remain necessary |
| Objective mass, off-C and empty-C | `test_train_baselines.py:42–79` explicit weights/pairs/fullY; `test_development_training.py:186` actual accounting/selector on off-C groups | Off-C-only selector case cannot test a non-flat optimum |
| One fit/full ceiling/copy shrink/failure | `test_development_training.py:96–182`; CLI tests actual orchestration/helper with doubles | Actual native abort and ordinary CLI E2E remain separate |
| Heldout seals/mutations/all7 before Y | `test_heldout_execution.py`, `test_heldout_evaluation.py`, worker tests: late mutation, failed markers, omitted days/Q, authority and chronology faults | Many owner/worker tests use fake launchers/authentication; not process/native proof |
| FullY estimands/ties/paired users | `test_ranking_metrics.py:7–174`; independent `test_heldout_metric_audit.py` literal AP/NDCG, all200 draws and mutation tests | Synthetic conditional-vs-all-Q/user definitions do not establish uplift/transfer |

## Specific blind spots and evidence limits

* **Actual-route bypass:** `test_train_development.py:143–184` replaces `verify_collection`, `prepare_dataset`, environment, selector, ML modules and `load_runtime`. It checks CLI sequencing/persistence/exception handling, not accepted-data→actual Prepared→actual selector compatibility. This is explicitly disclosed at `:1–4`; calling it “native end-to-end PASS” would be false. Metadata gate tests likewise replace acceptance (`test_metadata_price_features.py:330`); their gate plumbing is not lineage proof.
* **Shared oracle component:** selected-source oracle calls producer `prepare_plan` (`tests/oracles/feature_program_audit.py:188`) and `_expected_schema` (`:221–224`). Its values are independently rederived (`:62–128`), and literal names/types are checked (`:57,107–115`), but exact physical order partly uses the producer’s own expected-order function. A common composition error can survive that particular gate. This is a bounded independence gap, not demonstrated wrong current F57.
* **Projection canary:** `test_timeseries_nonalias_canary.py:110–125` intentionally copies the two retrieval-age/missing expressions and avoids full loader/Y. Equality of the two histories proves that synthetic alias, not correct loader composition, a bank implementation or quality gain.
* **Native status:** only `test_development_training_native.py:7` has opt-in skip; its source forces identical validation features/flat prefixes. Guide `development-training-native-test.md:5–9` records acceptance of that same helper body and distinguishes older skipped discovery. Neither default skip nor 12 CLI + 1 metadata CODE methods proves ordinary native CLI, callback abort, native lock parity or non-flat selection. Prior failed attempt remains failed/consumed; no reuse.
* **Do not run discovery as CODE:** `test_train_baselines.py:81–103,231` contains unconditional real fits/callback/smoke execution. The 881-method count is not a safe native-free run list. Private extracted-function “110 scenarios” were not in this frozen source scope; no new execution claim is inferred.
* Synthetic NULL/duplicates/ties are robustness tests. Cross-dataset/time/platform robustness and effectiveness require distinct real-data/native evidence and future authorized budget; frozen final is already opened.

## Proposed bounded ordinary synthetic CODE checks — four, not executed

1. **Most discriminating: new actual-loader/selector seam fixture.** At most 8 Q, 16 C, 32 invented events; fullY includes mixed, off-C, empty-C and empty-Y. Keep actual `prepare_dataset`, accounting, selector and helper; replace only ML backend. Independently hand-write all41 ordered coordinates/NaN masks, keys, weights and three-prefix NDCG curve. Acceptance: exact transport + independent curve/winner + one fake fit. Reject: shared-helper-generated expected values, patched preparation/selector or omitted Q. No native/imported models/real data.
2. **New F57-order mutation canary.** Independently freeze ordered57 `(name,type)` tuple; swap two same-type columns across grain blocks and freshly describe/reseal. Accept ordinary correct output; reject mutant independently of producer `_expected_schema`. This tests the shared-order blind spot without paid oracle execution.
3. **New actual retrieval saturation fixture.** ≤262 invented raw events/two Q, real candidate generator, literal200 popular/20 recent including overlap and a cutoff tie. Check exact IDs/ranks/≤220/no-refill, then peer permutation and future suffix. Existing `test_heldout_source_audit.py:192–198` tests saturation on preaggregated counts, not this raw route.
4. **Existing stdlib-only `tests.test_environment_snapshot.EnvironmentSnapshot.test_actual_helper_kernel_and_cold_legacy_side_effects`.** Fresh child, actual extracted helper, dependency mismatch and cold Darwin forbidden-open witness; bounded3CPU/5wall child. Acceptance remains metadata-only, never native CLI evidence.

Checks1–3: TMP-only, no CatBoost/fit/model/data access; Root must issue concrete bounded engineering run, with measured cost currently UNKNOWN. Native non-flat/helper-abort/CLI E2E and real-data transfer are future separate operations. No new quality hypothesis/ID is justified by this static coverage pass; existing HYP-046 exact-alias/representation and continuous TLAB-014 families already contain the relevant questions. **No tests, project imports, SQL, ML, native operations or real-data analyses were run.**
