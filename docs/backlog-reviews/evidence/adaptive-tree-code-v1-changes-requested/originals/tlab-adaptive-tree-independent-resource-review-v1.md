# Independent adaptive-tree resource/lifecycle review V1

Disposition: one supported P2. The complete frozen new producer, request, independent verifier, interface and synthetic test were reviewed. No fix, candidate execution, synthetic fixture, native import, data/model read or runtime approval was performed.

## Finding

**[P2] Reject the literal once-output alias before resolving it.**

Location: `/tmp/tlab-adaptive-tree-selection-study-v1.py:121–126` (especially lines121,123,126), SHA256 `a7c2a630dc289b50d279553a5079fb92484ce562fbb721f5858e716a9295e261`.

`output.resolve()` discards the supplied literal path before freshness is checked, and the request's fixed output path is resolved too. If the fixed `artifacts/reproduction/adaptive-tree-selection-1200-once` is an existing dangling symlink to an absent sibling under `artifacts/reproduction`, both resolved paths are equal, the containment/old-producer checks pass, and `mkdir(exist_ok=False)` creates the sibling. The existing literal once namespace therefore does not stop the attempt before `consumed.json` and up to two expensive fits. This defeats the exact fresh namespace contract and leaves artifacts in a different named location. The independent verifier's line72 compares its resolved output root with the literal fixed project/request path, so the resulting operation can then fail independent verification after the paid producer work.

Retain and reject an existing or symlink literal output before any resolution, directory creation or consumption. Preserve V1 and re-review the narrow repair. This trigger was established from the source path flow; no symlink fixture or candidate code was run.

## Other checked boundaries

The new CLI necessarily uses each arm's own complete1..1200 validation curve, global maximum and fewest-tree1e-12 band;1200 is the maximum fit size, not a fixed selected prefix. Both full native fits finish before validation starts. FullY-positive no-C/off-C queries remain in the metric denominator. The producer compares selected shrink/reload scores and all-candidate ranks, and the independent verifier derives its own curves/argmax/ranks/four estimands using pinned independent functions, four loads, two streams and four full predictions. No25–31 route occurs in this new study.

Request/source bytes, accepted historical report and matrix identities are bound. The public loader's SourceBinding rejects cached core modules and compiles its pinned core bytes. Export, model, score and curve byte checks and repins are paid within the respective module work. Producer failure preservation and verifier cleanup/repin paths retain the primary exception. AST parse and compile passed for the three new Python files; compiled objects were not executed.

The supplied module exposes a reusable selector whose omitted maximum means the model's full tree count, and its new CLI calls it for both arms. This review covers that adaptive route. It does not certify an unseen future caller or change the separately named historical frozen300 reproduction/training implementations.

## Resource and authority limits

The4200CPU/3600wall/12GiB/16GiB proposal remains an unissued engineering ceiling with unknown native feasibility: producer3500/2700, verifier600/800, shared tails100/100. The producer's3440/2640 cooperative Budget starts after bounded source/request handling, uses process CPU and cooperative RSS/spill checks, and cannot prove whole-lifetime containment. The verifier also requires its external check. The pending unchanged-V6 transport and Root's eventual full start/exit/reaping evidence remain necessary to support actual resource claims; module source alone proves none. This is not an execution grant, cost refill, scientific acceptance or approval of a repaired candidate.

## Frozen scope

Shared17-input freeze: `/tmp/tlab-adaptive-tree-code-review-20261015-v1/freeze.json`, SHA256 `d3949c9554903cc3ed815f148c2569137b08ea9f8a954848833ee87480b3ccb0`. All17 bounded snapshot hashes/lengths matched. New producer/request/verifier/test original pins were also current at review. Full new files plus relevant supporting old loader, ranking/model oracles, accepted-input receipt/matrix evidence and recipe were checked; no broad historical/census claim is made. Exact inputs and performed checks are recorded in the companion ledger.
