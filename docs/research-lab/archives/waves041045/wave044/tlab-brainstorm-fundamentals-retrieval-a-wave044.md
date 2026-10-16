# Wave044 B FIRST — check constant-logit initialization

**Disposition/mechanism.** Zero new IDs: refine TLAB019/013, round007 and own041. Static strong/adaptive sources explicitly retain boost_from_average=False; adaptive changes iterations, not this choice.[1] Test one future alternative, True, for both B/W. Tagged CatBoost documentation defines loss-optimal constant initialization; its Logloss helper computes the logit of the weighted target mean.[2]

A common logit offset alone preserves candidate order, but changes subsequent BCE residuals/tree fitting. Thus initialization could partly explain long tree budgets or different B/W peak locations without additional features. This is a hypothesis, not an explanation established from current curves.

**Prediction.** With identical training labels/weights, both arms must receive the same initial constant. If initialization delay matters, True should reach comparable full-Y validation quality with an earlier selected prefix; the W−B contrast may also change. Lower training Logloss alone does not establish ranking benefit or calibration.

**Nearest finite UNRUN control.** First audit tagged initialization/weight flow against the same mature training-only weighted prior; any B/W discrepancy or validation-derived prior rejects the binding. No fixture/native check now. A later separately authorized sensitivity comparison needs two new full1200 True fits and≤2400 dependent prefix evaluations. Reuse accepted False controls only with exact source/Q/C/Y/weights/feature-order/non-treatment-recipe identity; otherwise defer. Both arms retain depth6/L2=30/lr=.05/CPU2/seed2026 and the same full-Y global-band/fewer-prefix selector. Train8–20/selection22–23 remains reused development; no25–31/final reuse.

**Benefit/cost/decision.** Test whether a basic manual-baseline setting affects the apparent automation benefit before expanding features. Pay source authentication/preparation, prior calculation, both fits, every prefix prediction/ranking, masks/fullY support, persistence/verification/memory/failures and repeated feedback, including any revisited control metrics. Full1200 fitting saves no training merely because selected models shrink. CPU affordability is unknown; no grant/reset/refill. No comparable-quality smaller model, or adverse ranking/Recall, leaves this deferred. No current change/prerequisite/publisher action.

[1] [Static frozen recipe](/Users/mdpospelov/tlab-recsys-2026/configs/reproduction/frozen-bw-oct2019.json).
[2] [CatBoost1.2.10 helper](https://raw.githubusercontent.com/catboost/catboost/v1.2.10/catboost/libs/metrics/optimal_const_for_loss.h).
