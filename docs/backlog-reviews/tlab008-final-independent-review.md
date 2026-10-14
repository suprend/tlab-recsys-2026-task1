# TLAB-008 final independent CPU smoke review

**Verdict: CHANGES REQUESTED.** One P1 integrity finding remains in the collection gate. Real REES46 fits must remain closed pending a fix, regression checks, re-review, and separate coordinator approval. This review does not grant data acceptance or fit authorization.

Reviewed project: project repository. Review date: 2026-10-15. All project actions were read-only except ephemeral, automatically cleaned synthetic test fixtures outside the project. No production data, claims, accepted artifacts, source, dependencies, or Git state were modified. This report is the only retained output.

## Finding: P1 — collection verification does not enforce the child's required producer/input lineage

Location: `scripts/train_baselines.py:138–147` (the per-child manifest checks inside `verify_collection`).

The verifier requires the child's source/protocol to match and checks hashes for entries the child happens to declare. It does not require the child to declare the complete code set for its producer kind, the feature registry from the collection identity, or the accepted Q/Y/C approval lineage. As a result, a fresh, internally hashed seal can omit one of these required dependencies and still pass the training gate. The collection identity can truthfully contain the correct exact14 top-level execution bundle while its feature child is detached from that bundle. This is the remaining part of the requested source/registry/code/phase-to-child binding, not an objection to the correctly fixed top-level identity checks.

I reproduced three faults independently against the **actual synthetic017 lifecycle fixture** (no mocked collection hash):

| Deleted from one feature child manifest | `train_baselines.verify_collection` | Existing `development_collection.aggregate_collection` on the same plan/state |
|---|---|---|
| The phase's feature registry from `identity.input_hashes` | ACCEPTED | `Feature registry lineage mismatch` |
| `scripts/manual_features.py` from `identity.code_hashes` | ACCEPTED | `Unexpected producer code lineage: features` |
| The shard acceptance document from `identity.input_hashes` | ACCEPTED | `Feature output did not consume the exact accepted Q/Y/C lineage` |

For every case I recomputed the child run ID, updated the child's report run ID, updated state seals, and recomputed the external collection acceptance's physical hashes. No stale physical hash, missing acceptance pin, changed source, wrong protocol, or old collection ID was relied on. The unchanged complete collection report is deliberately the outer claim being checked. Its accepted pin proves its bytes, but the training verifier does not mechanically recheck the child facts that support the claim.

A caller still needs an external acceptance document and a separate exact fit approval; this is **not** a bypass of the fit-approval gate or an allegation about the sealed real017 data. It is a reproducible failure of the claimed mechanical lineage contract when accepting a newly resealed bundle, the same fault model as the new top-level binding regressions.

Required change: enforce the producer-kind-specific complete code set, feature registry binding, exact candidate→anchor Q/Y lineage, and feature→accepted Q/Y/C lineage at the training gate. Reuse/extract the existing read-only producer verifiers or implement equivalent checks. Merely verifying each declared hash cannot detect an omitted required dependency. Add regressions for omitted, swapped, and freshly resealed child lineage, then re-review the new source hash. The three reproductions above must reject before any fit claim/attempt.

## Exact reproduction

From the project root, run the following with `.venv/bin/python -B -` (all writes are fixture-local and cleaned in `finally`):

```python
import hashlib
from scripts import train_baselines as b
from scripts.protocol_manifest import load_run_manifest, sha256_file, canonical_json
from tests.test_train_baselines import CollectionAcceptanceTests

for fault in ('missing_feature_registry', 'missing_required_feature_code',
              'missing_QYC_approval_input'):
    case = CollectionAcceptanceTests(
        'test_exact_external_acceptance_accepts_then_missing_or_extra_scope_rejects')
    case.setUp()
    try:
        state = case.fixture.read_state()
        entry = state['shards'][0]
        seal = entry['features']
        runpath = case.root / seal['directory'] / 'run.json'
        reportpath = case.root / seal['directory'] / 'report.json'
        manifest = load_run_manifest(runpath)
        if fault == 'missing_feature_registry':
            removed = case.fixture.plan['identity']['phase']['feature_registry']
            del manifest['identity']['input_hashes'][removed]
        elif fault == 'missing_required_feature_code':
            del manifest['identity']['code_hashes']['scripts/manual_features.py']
        else:
            del manifest['identity']['input_hashes'][entry['acceptance']['path']]
        manifest['run_id'] = hashlib.sha256(
            canonical_json(manifest['identity']).encode()).hexdigest()
        b._atomic_json(runpath, manifest)
        report = b._read_json(reportpath)
        report['run_id'] = manifest['run_id']
        b._atomic_json(reportpath, report)
        seal['run_id'] = manifest['run_id']
        for path in [runpath, reportpath]:
            seal['fingerprints'][str(path.relative_to(case.root))] = sha256_file(path)
        b._atomic_json(case.fixture.directory / 'state.json', state)
        approval = case.approval
        approval['fingerprints'] = {
            name: sha256_file(case.root / name)
            for name in approval['fingerprints']}
        b._atomic_json(case.path, approval)
        b.verify_collection(case.path)
        print(fault, 'train verifier ACCEPTED')
        try:
            case.fixture.d.aggregate_collection(case.fixture.plan, state)
        except ValueError as error:
            print('producer aggregate REJECTED:', error)
    finally:
        case.doCleanups()
```

Observed output:

```text
missing_feature_registry train verifier ACCEPTED
producer aggregate REJECTED: Feature registry lineage mismatch
missing_required_feature_code train verifier ACCEPTED
producer aggregate REJECTED: Unexpected producer code lineage: features
missing_QYC_approval_input train verifier ACCEPTED
producer aggregate REJECTED: Feature output did not consume the exact accepted Q/Y/C lineage
```

## Checks passed and exact scope

I read the complete runner, its21 tests, smoke configuration, experiment documentation, and relevant collection/run-manifest/evaluator/deadline code. I ran:

- `.venv/bin/python -B -m unittest tests.test_train_baselines -v`: **21/21 PASS**, 1.509 seconds. Includes actual tiny CPU fits, synthetic collection production and acceptance, failed-first/global consumption, changed-output-root, config swap/snapshot, fresh top-level identity resealing, dependency mismatch, feature preparation and evaluator checks.
- `.venv/bin/python -B -m unittest tests.test_ranking_metrics -v`: **13/13 PASS**, 0.002 seconds. Full-Y denominators, empty-C misses, empty/censored handling, query/user macro and paired user bootstrap.
- Independent direct **tiny50-tree CPU fit and prediction for both Logloss and PairLogit**, with the frozen real smoke configuration. Both reached exactly50 trees, exposed `thread_count=2`, `use_best_model=False`, and produced9 finite scores. These toy fits have no REES46 quality interpretation.
- Independent callback fault for **both objectives**: guard failure after the first native iteration propagated as `TimeoutError`; an early checkpoint was not accepted.
- Independent pair-index/mass fault check with **two nonadjacent informative groups**, including `p=2,n=2` and skipped no-signal groups: six explicit positive→negative pairs, no cross-group pairs, each informative group total pair mass1.
- The three fresh-child-reseal faults reported above. These are independent failing acceptance expectations, not included in the21 passing repository tests.

Confirmed closed prior defects:

1. `artifacts/fit-claims/<run_id>.json` is project-global and created with `O_CREAT|O_EXCL`; it survives failure and prevents changed-output-root or failed-first free retries. Claim creation precedes preparation/model attempts. Retry rejection records0 new fit attempts.
2. `_config_snapshot` parses and hashes the same bytes; `prepare_fit_plan` compares that hash when building pins and rejects a mid-plan mutation. `run` rejects a mismatch with its initial parsed config and then uses the verified plan config. No fresh-hash rebasing of an old parsed configuration was found.
3. The collection's exact14 execution paths and identity source/registry/code/phase are now mechanically bound, including actual phase body, shard protocol exact cover, current physical hashes and child source/protocol. All five existing fresh-top-level-reseal fault cases pass. **The remaining child dependency omission described above is not covered by those five cases.**
4. Both CatBoost Pool constructors and both native prediction branches explicitly specify `thread_count=2`; fit params also specify2. The native fit callback checks cooperative deadline/RSS after each iteration, and surrounding stages check before/after. The documented cooperative resource limitation is accurate.
5. BCE retains every mature nonempty-C group (including all-negative/all-positive) with row weights `1/|Cq|`, each nonempty query mass1. PairLogit retains only groups with `p>0,n>0`, creates every `p*n` pair with `1/(p*n)` weight, and does not transfer row weights into the ranker Pool.
6. Preparation samples train Q by `(sha256(query_id),query_id)` before joining labels, preserves fullY separately, never appends missing positives or cleans future negatives, and retains emptyC/all-zero/outsideC cases for evaluation006. Tie ordering is score DESC/product ID ASC; fullY controls ideal DCG/Recall/AP denominators.
7. Raw query/user/product/category IDs and raw timestamps are excluded from numeric model inputs; retrieval time becomes strict-past age plus missing flag. Matrix values are float32, NULL→NaN, infinity is rejected. No fitted imputation, CTR/target encoding, or ordinal raw-ID conversion was found.
8. The frozen config declares50 trees. No `eval_set`, native OD configuration, or best-model selection is passed; `use_best_model=False`, and `tree_count_` is checked against the predeclared final iteration. Checkpoint maturity/availability and compute gap gates reject invalid phases.

## Limits

This is a code/integrity review of the frozen files and toy/synthetic execution, not a rerun of the full144-test suite, a new semantic acceptance of real017, an OS hard-resource guarantee, a model-quality result, or a strong-baseline tuning review. Real REES46 fits, production data, accepted artifacts and fit claims were not opened for mutation or training. No additional model design or unrelated research was performed.

## Frozen hashes and unchanged state

All four requested SHA-256 values matched **before and after** review:

```text
3d93145215cbf46072ec3a6b5127549dfb094a8fd86caad019db73c484887c0e  scripts/train_baselines.py
edceca797e27bdf574dc0bb10e462c5e9083ee8f20385ea7f65829cb0ee70d9e  tests/test_train_baselines.py
d8140e4581e6aa769af75f3638a697bb7224943ce1f6dcd1c5cd4588ed27c14a  configs/models/cpu-smoke.json
a054849000e29f30d50c4c46946658b92c8d01f99a72e8073f82a9db928cee0a  docs/experiments/boosting-baselines.md
```

`git status --short` was identical before/after: the requested four source/config/doc paths remained untracked (`?? configs/models/`, `?? docs/experiments/boosting-baselines.md`, `?? scripts/train_baselines.py`, `?? tests/test_train_baselines.py`); no new project files or modifications were introduced by this review.
