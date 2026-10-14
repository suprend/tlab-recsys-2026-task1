# TLAB-008 final independent targeted re-review

**Verdict: ACCEPT for the frozen CPU smoke runner code scope.** The prior P1 child-lineage finding is resolved. No new blocker was found in this targeted review. This is code acceptance for the already defined exactly-two-fit CPU smoke; actual fit approval remains the coordinator's separate explicit gate. It does not authorize tuning, metadata experiments, or a new fit budget.

Project: project repository. Date: 2026-10-15. The initial changes-requested report remains unchanged at [initial final review](tlab008-final-independent-review.md) with SHA-256 `7739da16de9775bfec56d7a170393f050ec82af84689812f77753e252233c230`.

## Resolution checked against the actual code

`verify_collection` retains the exact external required-pin derivation, physical hash verification, actual phase body, exact14 execution scope, top-level source/registry/code binding, and exact shard protocol cover. It now calls the existing immutable017 `_check_cached` for every anchor/candidate/features child, then `_verify_candidate_lineage` and `_verify_feature_lineage` for every shard. This makes the training gate enforce the mandatory producer-kind code bundle, complete physical seal, registry binding, candidate→independent Q/Y inputs and feature→accepted Q/Y/C inputs using the same established gate as producer aggregation.

I re-read the complete fixed runner and relevant017 implementations. The reused helpers are read-only and receive the same bound plan/protocol and budget callback. No new training, prediction, collection creation, or claim action is introduced by verification.

## Independent reproduction of all three prior faults

I reran the exact independent fault construction from the initial report, separately from the new repository regression test. Each case begins with a newly produced actual synthetic017 fixture and verifies the intact fixture first. Then one feature child dependency is omitted; child run ID, child report run ID, state seals and external acceptance hashes are freshly recomputed. The three prior false accepts now reject:

| Freshly resealed child mutation | Observed rejection |
|---|---|
| Remove phase feature registry from child `input_hashes` | `Feature registry lineage mismatch` |
| Remove `scripts/manual_features.py` from child `code_hashes` | `Unexpected producer code lineage: features` |
| Remove accepted Q/Y/C approval from child `input_hashes` | `Feature output did not consume the exact accepted Q/Y/C lineage` |

Thus rejection does not rely on an old physical hash or a malformed manifest digest. The original P1 is closed.

## Verification results

- Independent `.venv/bin/python -B -m unittest tests.test_train_baselines -v`: **22/22 PASS**, 1.986 seconds. Includes the new three-case fresh child regression, prior five top-level binding faults, actual tiny CPU fits, two-model toy export, global claim/failed-first/output-root retry guards, initial/snapshot config swap rejection, lock-version gate, weighting/pairs, full-Y evaluation, resource callback and explicit Pool/predict thread budgets.
- Independent original three fault constructions: **3/3 correctly rejected**, with the exact messages above. Intact actual synthetic fixtures accepted before mutation.
- Read-only `verify_collection` on both actual sealed017 collection approvals: **ACCEPTED**. Train:82 external pins,5 feature shards,9.561 seconds. Selection:30 external pins,1 feature shard,2.384 seconds. These calls verify immutable lineage and hashes; they do not fit, predict, claim, or rewrite artifacts.
- Both real collection acceptance files had unchanged bytes before/after verification:

```text
47b71f4ee8942c6b17508747f9f492e9b741707876934267e9b0d6cd31639903  artifacts/acceptance/tlab017-train-collection.json
45af326c2a71bbc0a12ba0753c0701dafc9e75d366150169a90aac164e51de7b  artifacts/acceptance/tlab017-selection-collection.json
```

## Previously accepted gates remain intact

Raw-code inspection and the22 passing tests confirm that the targeted fix preserved:

1. Project-global `O_CREAT|O_EXCL` consumption claims independent of output_root, retained across failed-first attempts; exact run/fingerprint approval before claiming; zero new attempts on retries.
2. Same-byte config parsing/hash snapshot, rejection of mid-plan config mutation and initial-parse/verified-plan mismatch, and use of the verified plan's config.
3. CPU2threads in fit parameters, both Pool constructors and both predict branches; iteration callback and surrounding cooperative deadline/RSS checks; failure audit and fixed final tree-count check.
4. Frozen config50trees, `use_best_model=False`, no `eval_set`, no native OD/best-checkpoint selection. The earlier independent tiny50tree fits and callback checks are documented in the initial review; the fix changes the collection verifier and the new scoped suite again executes tiny fits.
5. BCE support over all mature nonemptyC groups with per-query row mass1; PairLogit only informative `p>0,n>0` groups, all explicit `p*n` pairs with per-group mass1 and no imported row weights.
6. Label-independent train-Q bottom-hash selection, fullY/outsideC/emptyC retention through external evaluator006, deterministic score/product tie order, no future-negative cleaning or positive insertion.
7. Raw IDs excluded from numeric inputs; float32/NaN semantics, strict-past retrieval age/missing conversion, matrix/pair caps before allocation, checkpoint availability and compute-gap constraints.

## Frozen hashes and unchanged project state

All four requested SHA-256 values matched before and after this re-review:

```text
bdab8bbe0ed4863dd9922e436c38699a0c69e0d2846289ab9f5a63b44c52412a  scripts/train_baselines.py
65a713fc613dc37e9a9f27b31d70ad62673c08cdd5facfeb1e2cfe450a529190  tests/test_train_baselines.py
d8140e4581e6aa769af75f3638a697bb7224943ce1f6dcd1c5cd4588ed27c14a  configs/models/cpu-smoke.json
6857e0541d34de966bb4b4c5c2b43fb46ab31722e85447c459f777a75cba5888  docs/experiments/boosting-baselines.md
```

`git status --short` was identical before/after (only the existing untracked model config/runner/tests/doc paths). No project code,017 code, production data, accepted artifacts, dependencies, Git state or real fit claims were modified. Temporary synthetic fixtures were automatically cleaned. The initial review file is preserved byte-for-byte; this new report is the only additional retained output.

## Scope limits

Targeted final code/integrity acceptance; not a rerun of the coordinator's full145-test suite, new semantic data acceptance, strong-baseline tuning result or model-quality claim. No real REES46 fits or predictions were run. Cooperative resource checking remains a documented stage/iteration check rather than an OS hard kill. Coordinator approval must still bind the actual immutable experiment identity and exact fingerprints before spending the two real smoke attempts.
