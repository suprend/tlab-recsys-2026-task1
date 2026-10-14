# TLAB-007 synthetic implementation handoff — 15 October 2026

Status: **frozen, ready for independent read-only code review**. Production remains BLOCKED pending accepted004, coordinator fingerprint artifact and explicit go. No real Q/Y/C or source scans were executed by this worker. No model-quality claim or production report exists.

## Owned actual files

- `scripts/heuristic_baselines.py`:383 lines, SHA256 `db00b2375fed1083d4bf9b45ef4535793d36ffeaa537050a07e99c61dad13ee4`.
- `tests/test_heuristic_baselines.py`:398 lines, SHA256 `b68d294482765a9f04dc6a408a9bc52b4bf1a0d7697f50caf50c6a0f9b2837cf`.
- `docs/experiments/heuristic-baselines.md` deliberately not created: assignment permits it only after actual pilot.
- No Git staging/commits, dependency changes, raw data changes or other implementation edits. Two files remain untracked. `git diff --check` passed; explicit whitespace check covered both untracked files. Synthetic artifacts existed only in TemporaryDirectory fixtures and were cleaned up.

## Implemented semantics

Three pure fixed-C rankers: popularity distinct purchase users DESC/product ID ASC; existing recent-source rank ASC NULLS LAST then popularity/ID; max view timestamp over all candidate pairs in `[t−7d,t)` DESC NULLS LAST then popularity/ID. Recent-source-first does not claim full-history recency. Last-view includes candidates outside recent20, distinguishes view from purchase/cart, excludes every event at t and keeps null/old-history candidates.

Unique query/user-day/midnight/budget validation imports004; maturity is recomputed from protocol via001. Full distinct Y validation forbids orphan/duplicate/censored labels and contradictory catalog diagnoses. Production protocolv1 itself requires fully mature pilots; no valid censored pilot exists under this upstream validator. The ranking/evaluation seam nevertheless preserves censored Q and passes targets=None, separately tested. Every Q survives empty C/Y. Candidate membership is unchanged, and ordered all-C lists are exported including ranks past20.

Evaluator006 provides all four estimands, p(nonempty), mature/positive user and query counts. Report has full-Y retrieval ceiling (micro and positive-query macro), daily and overlapping query slices with original full Y, target-unit repeat/new-pair/catalog-cold micro recall at original ranks. Minimal history-support split means only observed candidate-pair view7d; no claim of uncomputed whole-history support. Pairwise NDCG/Recall bootstraps cover each four estimands, ≤1000 draws, show user_count/defined_draws/undefined_draws; no tiny-support promotion claim.

## Coordinator acceptance schema and production command

Required ignored internal acceptance JSON, **version1**, exact keys:

```json
{"version":1,"approved":true,"candidate_run_id":"...","anchor_run_id":"...","fingerprints":{"repo/relative/path":"64-character SHA256"}}
```

Pins are required for003/004 run.json/report.json, original003 Q/Y,004 C, source DuckDB and every reported upstream code/uv.lock/input fingerprint. Actual hashes are compared with both accepted pins and manifest declarations. Complete status/run lineage/protocol equality are required.004 must record the exact original independent003 Q/Y paths and hashes, not a same-byte copy elsewhere. Candidate artifact output hashes absent from upstream manifests are supplied by accepted pins. The scorer identity additionally hashes actual scorer/evaluator code, lock, protocol, full consumed pins, scorer spec and bootstrap settings.

After independent code acceptance and coordinator go only:

```bash
.venv/bin/python -m scripts.heuristic_baselines --candidate-run artifacts/candidate-pilot/<accepted004identity> --acceptance artifacts/<coordinator-acceptance>.json
```

No new human approval prompt is introduced; this is a coordinator technical gate. Cooperative persistent RunDeadline/StageLedger cover fingerprinting, loads, selected-anchor view scans, CPU rankings/evaluation, bootstrap stages and export. Hard caps:6000Q,1.32mC,1800s,2 threads,DuckDB2GB/spill2GB,RSS6GiB cooperative checks. Failure persists attempt/identified report with stages, accepted declarations, partial identity/counts where reached, wall/RSS/engine peak/spill, and no complete metric block. Timer starts on DB connection; fingerprint deadline checks before/after hashing persist between SQL calls. There is no OS-level kill or preemptive Python-sort interruption; an overlong individual CPU operation is detected at the next cooperative gate. No user×catalog join; view scans filter time and join selected fixed pairs per distinct anchor. All output identifiers remain ignored.

## Actual verification

Command `.venv/bin/python -m unittest discover -s tests -p test_heuristic_baselines.py -v`: **17 tests PASS,0.442s,exit0**. Earlier13-case run found macOS `/var` versus `/private/var` normalization in synthetic-root path guard; normalized resolution fixed it and the regression now passes. No failed check is presented as success.

Meaningful evidence: handgolden ties/microsecond ordering/exact-C; handfull-Y Recall1/3,NDCG0.469278726 with23C and positive beyond20/outsideC; independent randomized row-iteration oracle; lower/upper bounds; all-event recent versus views; old view/null; duplicate raw events/peer permutation/future suffix invariance; distinct-anchor windows; mature-empty/censored seam/zero-positive/empty-population handling; repeat/cold/query-versus-label units and retrieval ceiling; malformed candidates/labels/maturity; content/code/source/report tampering; missing pins; accepted-but-wrong lineage/status; exact003-Q identity; actual tiny DuckDB→Parquet→accepted-run full pipeline and ordered all-C export; early resource/provenance and late-stage error persistence. Synthetic runner checks actual stored artifact SHA, measured stage engine profile/RSS, row counts and output counts. Tests use tiny locally generated source files, not real dataset data.
