# Wave064 C FIRST: event time versus synthetic availability

**Mechanism.** No new mechanism or demonstrated defect: experimental-report §Data explicitly assumes availability by event_time; feature_programs.CONTEXT names `event_time_assumed`. Arrival clocks are absent. Strict event-time filtering cannot establish actual online readiness.

**Nearest finite experiment, future only (0 fits; UNRUN/ungranted).** Declare synthetic UTC midnight t, valid nominal keys/categories, complete seven-day source coverage, unsaturated current 2000-query/200-popular/20-recent caps. Six literal events have (event offset, availability offset): g purchases p (−2h,−2h); u views p (−2h,−2h); v views r (−1h,+1h); u views r (−1h,+1h); g purchases r (−30m,+1h); u purchases r (+1h,+25h). Independently specify exact expected tables for current event-time replay and a separately named hypothetical strict-availability contract; do not retrofit current protocol.

**Predictions.** Recomputed event-time eligibility is Q={g,u,v}, C_u={p,r}; availability eligibility is Q={g,u}, C_u={p}, using actual popular-purchase/recent union rules. Separately hold the original Q/C fixed as an explicitly supplied projection: pair-view-24h X(u,r) is 1 versus 0. That projection is not availability retrieval output. Appending old-event backfills changes recomputed event-time replay; a frozen as-of-t snapshot stays immutable. Appending the post-t purchase changes neither anchor Q/C nor X.

**Target maturity.** Declare synthetic global delivery bound L=24h and a trusted completion watermark, separately from event endpoints. At t+24h the purchase is unavailable and the horizon is not guaranteed mature; at t+48h fullY_u={r}, retained off-C under availability retrieval, with mature zero-Y g/v where eligible. This bound is invented, not measured from REES46.

**Benefit/counterhypothesis.** The witness separates eligibility, retrieval, fixed-C feature projection and label readiness without models or quality inference. If real arrivals were timely, this synthetic difference would not identify a practical failure; actual lag/completeness remain unknown.

**Dedupe/disposition.** Existing 022/040 and 036/043 already disclose clock/backfill boundaries; wave022 covers temporal adapter witnesses. Merge only optional specification refinement into TLAB013/014; preserve frozen017/019. Zero new valid gaps, IDs, gates, admissions or grants. Root alone decides adoption.
