# Native lifecycle — bounded independent SOURCE review

**Conditional SOURCE PASS for both narrow designs; execution/readiness UNRUN, adequacy UNKNOWN.** Not wave095; next07:30UTC unchanged. Existing b369 acceptance covers warm ordinary fit8/flat-prefix1; callback-abort and successful cold training remain unproved. CLOSED/SPENT76cac grants no further attempt.

## Scope and required evidence

**Cold negative entry.** Current train_development147–167 validates arguments/output absence, calls real load_runtime, then creates output/report and invokes train verification first. That verifier reaches Path.read_text on the absent acceptance. If startup succeeds within limits: one runtime load, one strict train-verifier, zero validation-verifier/Prepared/constructor/Pool/fit/scoring; failed/FileNotFoundError report with fit_attempt_count0, exact exception.filename, empty stdout, no recipe/model/scores. Failure before output/report creation is startup failure/inconclusive. Import side effects and unrestricted native I/O are not contained merely by Python observers.

This establishes fresh-process dependency loading and negative CLI entry only. [runpy3.12 documentation](https://docs.python.org/3.12/library/runpy.html) supports fresh module namespace, not process isolation; freeze run_name/argv/sys.path/cwd/interpreter/environment and reject preloaded backend/project modules. OS caches remain uncontrolled. Successful cold accepted-input→fit→selection/save/reload is separate.

**Callback abort.** Current development_training59–71 constructs the real Pool/callback, calls fit once, then raises callback.failure before selector/copy. train_baselines callback catches the injected TimeoutError, retains it and returns False. The proposal intentionally changes the instance guard during a real callback; label this instrumented fault injection, not observation-only or an unmodified shell execution. Preserve ordinary pre-fit guards, exact fit arguments and the original callback method; freeze wrapper identity/restoration and bind the already accepted tiny inputs without discovering another fixture.

[Tagged1.2.10 train_model318–457](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/libs/train_lib/train_model.cpp) orders training/errors before callback; [bridge1231–1248](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/python-package/catboost/_catboost.pyx) derives iteration from history length. Fresh history plus successful first iteration supports callback1/iteration1 conditionally. Invalid iteration or earlier failure can prevent reach. Exact public partial tree_count1 is diagnostic expectation, not proven by this trace; safely unavailable getters remain UNKNOWN.

Require original callback-local guard1, retained sentinel1, callback False/failure identity, helper rethrow identity, failed CLI report/fit_attempt_count1, nonzero child exit, zero selector/validation-prefix looks/copy/shrink/save/reload and no promotable artifacts. Native learn metrics still cost work. Diagnostic recipe/report remain failed evidence. Reuse V2 primary-error/stream restoration; telemetry/flush failures must not replace sentinel. Kill/cap breach is not graceful callback success.

## Resources and next slice

Cold15CPU/25wall,512MiB,1MiB outputs versus callback50CPU/65wall,aggregate1GiB,64MiB reads/4MiB outputs are **ungranted proposals**, not demonstrated containment. Include startup/preparation/hash reads, observer/getter work, failures, all descendants, TERM/KILL, reap and final receipt. No refill or reusable seconds.

Next bounded decision is which existing gap to exercise: zero-fit cold-entry refusal, or one separately authorized cold first-callback-abort fit. Neither closes full successful cold training. No new controller, issue, grant or mandatory gate follows.

## Actual pins and read extents

Proposal inputs, both fully read and hash-verified:

- Cold SHA256 a90755ea1de2631646c627ee7687e87f5654f334a249ccb3eaac4032aa56de72
- Callback SHA256 9fbe05d4b0dc6cd5feaf15e6223ffc6eac51a98592e4cc3d5c654f528baf5595

Canonical scripts/ source SHA256 (actual):

| File; read extent | SHA256 |
|---|---|
| train_development.py; full249 | 16248901e80d9f13d58c08261d1b108844452f6c459311d657790a511d9db968 |
| development_training.py; full91 | 9f7d9ab7c1f69fd0726d657791059b4a0c5270bf7a32da898602eaf84ccffcc9 |
| train_baselines.py;1–80,345–385 | b25dc30cc7265dddb3cbf910edff12cc4bcf220161c86c59a7d3fa33cf129bed |
| metadata_price_collection.py;1–105 | 59565643f58a3b34bb716c6cc071d7e1802d79aaf0b707e1537459b0a5377afa |
| protocol_manifest.py;60–73 | 0a8aa0fe4213226665d1f7ff61393dd7b7aacfe0df094c3f22a781982929ffc0 |

Also read safe b369 acceptance and V2 source review fully, callback-test source105–175; no tests run. Native excerpts289–557/1231–1248, runpy7–26; web-body/installed equivalence UNKNOWN. One source-only helper, no files. No source fetch failures; no imports/native/models/SQL/data/controller/Git/project/network writes. READY; STOP.
