# Next callback-abort slice — independent SOURCE proposal

**READY for Root review; UNRUN / adequacyUNKNOWN.** Existing engineering question, not095/newgate. Next grid07:30UTC unchanged. b369 Root acceptance covers warm one-fit8/flat-prefix1; callback-abort/cold-shell remain UNRUN. Grant76cac is CLOSED/SPENT, remaining attempts0. No helpers/current engineering proposals read, execution, imports, data/model access, controller, grant, issue or canonical edits.

**Recommended single attempt.** Fresh child interpreter, clean explicitly recorded environment/cwd/locked interpreter; no NumPy/CatBoost/DuckDB preimport or inherited live runtime. Bootstrap imports only stdlib and `train_development`; record backend modules absent before ordinary `load_runtime`. Install observation/injection only after that function returns. This covers cold startup/import/preparation→native-callback reach plus negative termination; it cannot establish successful complete cold training, selection/save/reload or every shell configuration.

Reuse the accepted tiny pair of3×41 Prepared inputs (246 cells; train Pool123), exactQ/C/fullY/order/types/weights and8-tree ceiling. No new fixture discovery. A forwarding wrapper around the actual `_BudgetCallback.after_iteration` replaces that instance's `check` only during the first real native callback: call its original guard, then raise one retained `TimeoutError('first-native-callback-abort')`. Delegate to the unchanged original method, record its result/failure identity, restore in finally. No replacement fit/model/Pool/helper implementation. This is instrumented CLI validation, not an entirely uninstrumented shell invocation. Pre-fit checks remain ordinary; a pre-callback failure consumes the attempt without proving callback-abort.

**Why this point.** [Tagged CatBoost1.2.10 train_model.cpp](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/libs/train_lib/train_model.cpp),400–457, calls custom AfterIteration after training/error calculation. [Python bridge](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/python-package/catboost/_catboost.pyx),1231–1248, forwards history length as iteration. No direct synthetic invocation counts as native reach.

**Finite expected cells.** One CLI/helper/native-fit attempt; first callback count1/iteration1; callback-local original guard called1 then sentinel raised1; callback.failure is sentinel and return=False; helper rethrows that exact object. Native wrapping may become its cause; it must not replace the primary. CLI report status=failed/fit_attempt_count=1. External selector calls0, validation-prefix/NDCG looks0, selected-copy/shrink0, model saves/reload/scoring0; complete/promotable artifacts0. A one-tree partial model may remain in RAM; record bounded is_fitted/tree_count only if safely obtainable, expect1, otherwise explicit UNKNOWN. Never select/save/promote it. Native internal learn-metric work is charged, not called a validation look.

Expected CLI child exits nonzero; parent may report the negative oracle passed only after sentinel/report/output/lifetime reconciliation. Retain diagnostic report/recipe, never relabel them complete. Preserve the sentinel across failed telemetry, formatting, flush/stream restoration; record secondary errors separately. Reuse V2 restoration order/primary handling, not V1. Missing expected sentinel, callback>1, full8 trees, success artifacts or unknown fit count fail this witness; no retry/refill.

**Alternatives/budget.** A zero-fit double can test forwarding/primary/report/cleanup branches, but cannot prove native callback reach or abort. One cold real-fit attempt can answer the combined narrow question above; an additional successful cold fit would be separate. Proposed inclusive50CPU/65wall: owner2+child45+reserve3CPU; TERM at60wall, KILL/reap by64, finalization by65. Child512MiB/parent128MiB, aggregate≤1GiB; authenticated physical reads≤64MiB, all outputs/logs≤4MiB, no spill/download. Startup, input hashes, preparation, callback, diagnostic getters, failures and cleanup all count. Cap breach/kill is failed/inconclusive, not graceful callback success; confirmed child exit/reap is mandatory. All limits' adequacyUNKNOWN; no new rights or approval question.

**Local SHA256/read extents** (canonical root `/Users/mdpospelov/tlab-recsys-2026`):

| Source | SHA256 | Read |
|---|---|---|
| scripts/development_training.py | 9f7d9ab7c1f69fd0726d657791059b4a0c5270bf7a32da898602eaf84ccffcc9 | full1–91 |
| scripts/train_development.py | 16248901e80d9f13d58c08261d1b108844452f6c459311d657790a511d9db968 | full1–249 |
| scripts/train_baselines.py | b25dc30cc7265dddb3cbf910edff12cc4bcf220161c86c59a7d3fa33cf129bed |345–380 |
| tests/test_development_training.py |547fac7bf2591ca831fa717e17017e39fe98994c1f87ab7b2110b9dc22ca3a23|105–164/targeted matches |
| tests/test_train_development.py |0cc21e8d8f6536d06f0e94cb554f4eec8907b9305dc8adde78d3d68ea0fe451b|exception matches only |
| post-audit-native-result.md |308c408a1b0f1a715492ed2a00cfc2a7cf13d13fda66f7c43d1d6db20ef61734|full; backlog-reviews |
| [V2 SOURCE review](/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/evidence/wave088-native-publication/originals/tlab-native-cli-post-audit-native-source-review-v2.md) |bdd434fd14e3e0a85d9b6eb17ba9e454ddf93c2de400feefdf9d5ed2c0d82221|full |
| [Root native final acceptance](/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/evidence/post-audit-native-result/originals/tlab-root-native-V2-final-actual-acceptance-v1.json) |b369364a4dd870851541daa5f1a07114cad671b5657da5ea4c0758c3e9199dab|full safe metadata |

Broad historical rg output truncated; not relied on. Adaptive selector read as declaration matches only. Official fit-page metadata and train.cpp no-match added no evidence; remote body hashes/installed equivalence UNKNOWN. No secondary-fault execution claimed. Root independently reviews this sole TMP proposal; STOP.
