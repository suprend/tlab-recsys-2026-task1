# Wave094 independent skeptic

All three FIRST/pins/freeze sets were READY before review; actual hashes match their freezes. Source-only review, after original06:45UTC due; next07:30UTC unchanged. Proposed **NEW0 / REFINE3 / MERGE3 / REJECT_PROPOSALS0 / ADMIT0**; REFINE/MERGE count the same three proposals. No new mandatory task, gate or grant.

## A — retain routing refinement, narrow scope and accounting

**P3 clarification:** [A FIRST:19](/tmp/tlab-wave094-native-metric-FIRST.md:19) should call its six predicted evaluations **direct RFE calcLoss invocations**, not the total objective evaluations of two training procedures. Under clean individual one-step SHAP, select1of2, final=false, source gives three such calls and two feature-curve points per invocation. Training performs additional metric work whose count remains UNKNOWN. The ≤4-tree total comes from the separately fixed2-tree training cap.

The [v1.2.10 RFE source](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/libs/features_selection/recursive_features_elimination.cpp),641–682, constructs direct loss from ObjectiveMetric;535–570 forwards custom eval into training. [Options789–887](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/private/libs/options/catboost_options.cpp) maps Logloss to objective Logloss. This supports the direct SHAP criterion claim, not “custom metric never matters”: early stopping/best-model effects can alter trained scores.

ByTags SHAP also uses this loss, subtracting whole-tag contributions and dividing by tag cost; committed removal then evaluates each constituent feature. Its call counts therefore differ. LFC uses a separate model-objective/fallback-loss importance route ([util80–100](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/libs/fstr/util.cpp), [loss_change113–140](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/libs/fstr/loss_change_fstr.cpp)); PVC uses prediction effects and forces final retraining even when final=false. Do not flatten these into identical algorithms/counts.

[_MetricEval1458–1486](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/python-package/catboost/_catboost.pyx) supplies approximation/target/weight slices, not query/item/pool identity. Authenticated sidecar ordering remains an unverified dependency; array length alone is not general identity proof.

A's future test has4 training rows,8 evaluation candidate rows,5Q/5 fullY pairs, two invocations,2 deletion decisions and16 final evaluation scalars. The16-call/128-captured-scalar abort caps require actual reconciliation. Equality of captured scores cannot establish hidden-model identity. Keep the source finding under HYP-002/046 and TLAB-006/016/019; existing external016 is sufficient. No installed-binary or quality claim is admitted.

## B — retain mechanics/statistics separation; do not duplicate accepted coverage

I independently read the archived FakeModel source and current positive_layout→rankings→evaluate→_choose_curve seam. Historical coverage already includes nonflat/global-band, off-C/empty-C, integer ties, malformed stages and undefined cohorts. The new flat native result is Root-reported background, not an oracle inspected here; no further fit is implied.

Hand check: three fullY-positive Q remain, four candidate rows survive projection, hit IDCG=1+d. L gives b=d/[3(1+d)], T/H give c=1/[3(1+d)]; tie T ranks10 before20. Recall20=(1/2)/3=1/6. Thus B* chooses1, W*2. The scalar near-band curve selects2 because the first value lies outside the global1e−12 band. It is a metric-only case, with no claim that this fixture's raw scores realize it.

Selection matched-prefix contrast is0; selected contrast c−b>0. The invented second block keeps matched-prefix0 but yields b−c<0. Nine vectors×six serialized scores=54; nine×four projected rows=36, with six selection looks, three prespecified diagnostics and three additional near-band scalars. These remain hand expectations, not replay results.

[Cawley–Talbot2010 abstract](https://jmlr.org/papers/v11/cawley10a.html) supports finite-sample selection overfitting generally; it does not quantify this constructed reversal. Stable real gains and arbitrary score unrealizability remain counterhypotheses. Current prefix selection has no Recall floor; five-arm feature choice does. Score replay cannot validate native staged production/copy/shrink/save/reload/callback abort. Merge existing TLAB-014/019/016, HYP-002/141/FA01, wave064/065 coverage.

## C — retain measure-scoped verdicts and suppression order

Current exact-schema generator rejects this descriptor before AST handling; no binder bug is demonstrated. Round013/052 already require measure identity and per-request capability decisions.

Independent [Wikimedia documentation](https://meta.wikimedia.org/wiki/Research:Wikipedia_clickstream) reading confirms monthly mapped pairs, ≤10 suppression and four logical fields; footer oldid31171776. [README](https://dumps.wikimedia.org/other/clickstream/readme.html) declares family-level CC0. Physical release/schema/transform/completeness/availability/license binding remain UNKNOWN; failed oldid/release endpoints were not retried.

Hand check:6+6 on distinct mapped edges disappear before regrouping, giving published SUM0; regroup-first12 survives. Raw0+0 gives the same empty published selection. Complete published-bag SUM0 and unknown raw total therefore coexist without redefining complete empty event count0.

Ten verdicts are explicit: A rejects all five; proposed B conditionally accepts published SUM11 and SUM0, rejects24h/actors/raw absent→0. Missing acceptance dependencies produce NOT_READY. Three hypothetical weighted edges support two arithmetic paths; zero expanded events. The proposed role/binder remains unimplemented. Existing contracts might already express every distinction, making this a concrete witness rather than new infrastructure. Merge HYP-002/046/TLAB-005/016.

## Limits

All proposed experiments/tests UNRUN; adequacy UNKNOWN. A60CPU/90wallseconds/512MiB, B10CPU/20wallseconds/512MiB and C15minutes/10KiB are proposed ceilings, not allowances or demonstrated feasibility; preparation, verification and failures remain charged. Pins record actual read extents/hashes and one read-only source helper. No native/backend imports, models, fits, SQL, raw data, tests, downloads, Git or project/network writes. Current backlog's06:11 status is dated; newer native acceptance belongs to Root's separate actual review. Root alone decides adoption.
