# FIRST — training matrices, weights, losses and support

Frozen HEAD `c538de4097322715fccac494e2b2becc3279e8e1`; shared manifest SHA256 `7e2e871f148beac5b9fce3aa23970b370db0c8fdc9eac89958fb6342a4d2a41a`. Read-only/static review; no peer FIRST/conclusions read.

## Confirmed finding

**P2 — Apply the existing strict collection gate in the new ordinary CLI.** Original `scripts/train_development.py:163–164` calls `b.verify_collection` for both inputs. Its feature-lineage path derives required dependencies from the supplied shard approval (`scripts/development_collection.py:311–318`), rather than independently deriving canonical Q/Y/C approval scope. Thus coordinated omission from that approval and the feature manifest can survive verification, even with correctly rehashed outer acceptance/seals. Expected: the new caller rejects an accepted bundle whose feature child does not bind mandatory Q/C dependencies before preparation/fit. Actual source path can accept it. Consequence: weaker mechanically verified training provenance; **not evidence that current production features or labels leaked**.

Concrete existing minimal witness: `tests/test_metadata_price_collection.py:29–51` removes anchor `queries` and candidate `candidates` paths from the shard approval and feature `input_hashes`, updates approval digest, feature run ID/report/seal/state and outer pins, then explicitly calls legacy `b.verify_collection` without expecting failure (line 50). The independent required-set derivation already exists in `scripts/metadata_price_collection.py:82–101`; it rejects this same bundle with `canonical14`. I verified these branches statically, not by running that test. 019 and 016 workers already use the supplement (`scripts/strong_baseline.py:353`, `scripts/feature_program_experiment.py:404–405`). The legacy gap is documented in the supplement's lines 62–66; inheriting it in the new ordinary caller remains actionable. Suggested repair scope: use an independent complete dependency gate in the ordinary caller and preserve all historical frozen/smoke bytes; include any newly imported dependency in caller pins.

No additional P0–P3 defect established in the inspected matrix/loss mathematics.

## Scope and traced paths

Exact 36 source/config/document paths are pinned separately; several large files were inspected only at the relevant functions/search results. This is not review of all 632 captured files.

* Ordinary CLI → external collection verification → phase/schema checks → `prepare_dataset` → `fit_development` → `select_best_tree` → copy/shrink/save/reload parity. The helper explicitly trusts its caller for lineage and chronology; direct helper calls are not a complete pipeline.
* Historical smoke → fixed 50-tree Logloss/PairLogit; historical 019/016 → strict collection gate → chunked `model_data`, optional append-only `program_model_data`, fixed training/scoring procedure. Public frozen replay and historical adaptive study use their own `prepare_matrix`/contracts; neither is the ordinary CLI. Their outcomes do not establish execution of the new caller.
* Inspected three collection modules' relevant phase/lineage/physical-cover boundaries, temporal primitives, matching tests, loss/model indexes, development-training/baseline documentation and hypothesis/index context. Original paths map to `/Users/mdpospelov/tlab-recsys-2026/` in the shared manifest.

## Supported observations and boundaries

Matrix labels join by `(query_id,product_id)`, not physical row position. Global Q selection is hash-based before target-dependent SQL; candidate rows sort by `(group_index,product_id)`. Full Y is maintained separately, so off-C positives never become inserted training rows and positive empty-C queries survive evaluation. Numeric NULL maps to float32 NaN; infinities after conversion reject. Raw query/user/product/category IDs are excluded from numeric features. In the inspected code no label-conditioned query or row truncation occurs: row/pair caps reject before allocation rather than truncate by target. Caps can still make a run unavailable; scientific quality of a 6000-query subset is unverified.

For every nonempty C-group, Logloss's actual native Pool receives row weight `1/|Cq|` (`train_baselines.py:285,373`; `development_training.py:59`). PairLogit retains only mixed groups, constructs every positive×negative pair, uses indices relative to retained rows and mass `1/(pn)` (`train_baselines.py:296–319,377–379`). Empty/all-negative/all-positive groups are counted and evaluated. This support difference is intentional and correctly disclosed; it prevents a loss-only interpretation of the smoke contrast. It is not an implementation defect.

Validated phases require mature right-open last target, fit cutoff equal to train label availability, positive compute gap, and ready-at no later than selection start (`development_collection.py:49–80`; `train_baselines.py:166–185`). Current target horizon is 24h; `clock-48h` denotes eligibility. No actual artifact timestamp/maturity or train/validation data was opened here.

Selector keeps every positive full-Y query, including empty C/off-C Y, evaluates every prefix with external full-Y NDCG and chooses earliest within the global 1e-12 band. Zero informative groups can legitimately yield a flat curve/first prefix; no additional signal is invented. Reused development labels and the already opened historical final cannot establish independent quality. Native CLI/callback behavior is an explicit unverified boundary.

## Quality hypotheses (no new IDs/admission)

**Refine existing TLAB-008/HYP035, already deduplicated in `docs/loss-selection/02-pairwise.md:44`: separate objective from training support.** Mechanism: BCE's all-negative-group gradients can improve candidate scoring while PairLogit discards them; an apparent objective gap may primarily be a support gap. Counterhypothesis: PairLogit's pairwise objective itself drives the gap. Prediction: informative-only, query-mass BCE moves materially toward PairLogit if support dominates. Nearest future check: keep exact frozen Q/C/X/Y/parameters, compare existing all-mature BCE/PairLogit with one explicitly allocated informative-only BCE, then report full-Y all-query/conditional metrics and support. Benefit: attribute the training mechanism before spending Task1 budget on a loss change. Cost UNKNOWN; no fit, gate, new ID or reservation is authorized here.

## Most discriminating independent check

First use a no-fit temporary synthetic bundle with the literal omission witness above, routed through the **actual new CLI verification stage**. Accept the intact bundle; reject both Q-only and C-only omitted/resealed variants before `prepare_dataset` or helper/model construction. Reject this finding if the actual ordinary route independently derives mandatory Q/C scope and already refuses both variants; legacy helper behavior alone is insufficient to reject it. Separately, under a new bounded engineering grant, compare literal expected keyed X/Y/weights with the Pool actually handed to native fit; fake/AST checks cannot prove that boundary.

Executed only text/search/hash inspection and stdlib AST parsing of 21 Python sources; no project/native imports, workers, tests, SQL, data/Parquet/model reads, predictions or fits. Source syntax is not runtime proof. Source hashes/readback are checked below by the pinned freeze; STOP after FIRST.
