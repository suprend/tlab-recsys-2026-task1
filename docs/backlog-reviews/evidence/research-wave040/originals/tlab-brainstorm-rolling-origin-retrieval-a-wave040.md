# Wave040 A FIRST — two retrospective rolling-origin diagnostics

**Status/mechanism.** Optional next TLAB013 candidate; zero new IDs. Freeze B41/W44 definitions, depth6/L2=30/lr=.05/CPU2/seed2026; refit each arm to1200 per fold, independently select its prefix1…1200 on inner full-Y conditional NDCG20, global maximum band1e−12/fewer trees. Outer outcomes never choose trees or features. Current study/report/015/018 are unchanged.

All dates below are October2019 UTC daily anchors; ranges are inclusive query dates. Each query's purchase labels span[d,d+24h), mature next midnight.[1]

| Diagnostic | Train Q; labels ready | Inner Q; labels ready | Outer Q; labels ready |
|---|---|---|---|
| A |8–12;13 00:00|14;15 00:00|16;17 00:00|
| B |8–15;16 00:00|17;18 00:00|19;20 00:00|

Full1200 model fitting must finish in gaps13→14/A and16→17/B; prefix selection/shrink must finish after inner maturity and before outer16/A or19/B. These are replay availability deadlines, not claims that2026 artifacts existed in2019. Record actual fit/selection completion separately. The frozen exports cover train8–20 and selection22–23; proposed folds use existing train days only.[2] No25–31.

**Strong control/prediction/benefit.** Within each fold, B/W share exact Q/C/fullY, train rows/weights, representation and independent inner selection rule. Filter existing keyed exports by query date; preserve original strict-past feature history/denominators, masks and complete C. Compare outer W−B, chosen prefix locations, support and retrieval misses. Consistent contrast signs/nearby peaks would support descriptive stability of these fixed representations; reversals or highly variable peaks weaken it. Shorter training spans and overlapping users/windows prevent treating folds as independent replications.

W and baseline tuning used22–23, later than both outer periods. Transporting W backward is post-selection diagnostics, not honest independent CV of automated feature search. Whole-procedure CV would additionally rerun source-safe feature/baseline selection inside each fold with its paid feedback/history; its extra fits/looks are unestimated and not granted. Never reuse a model trained through20 for earlier folds, even after shrinking.

**Nearest cheap UNRUN falsifier.** Calendar-only check: inner22 matures23 00:00; outer23 leaves no positive compute gap. Reject that pseudo-forward split. Also reject any proposed fold whose model/prefix availability misses its deadline; no fixture ran.

**Full cost/negative outcome.** Both diagnostics require4 additional1200-tree fits,≤4800 inner checkpoint evaluations,4 frozen outer model evaluations and2 paired contrasts, plus all authentication/preparation/Pool/staged prediction/sorting/memory/serialization/readback/failures. Existing exports do not make those costs free; no new harness or authority. Inner zero-positive support means no defined selector; outer zero-positive support means undefined conditional NDCG. Report consumed costs and inconclusive outcomes without extending dates/refilling. This is no current mandatory CV gate or new final-quality claim.

[1] [Frozen24h contract](/Users/mdpospelov/tlab-recsys-2026/configs/protocols/clock-48h.json).
[2] [Frozen train range](/Users/mdpospelov/tlab-recsys-2026/configs/development/train.json).
